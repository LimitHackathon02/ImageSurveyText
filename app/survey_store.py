"""설문 세션 저장. 상태 확인과 변경은 한 SQLite 트랜잭션에서 처리합니다."""
import json
import time

from fastapi import HTTPException


BUSY_STATES = {"ANALYZING", "BUILDING_SURVEY", "GENERATING"}


class SurveyStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS survey_sessions (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE, fingerprint TEXT, payload TEXT
            )""")
        self.recover_interrupted()

    def create(self, session, request_key, fingerprint):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if request_key:
                row = db.execute("SELECT fingerprint,payload FROM survey_sessions WHERE request_key=?", (request_key,)).fetchone()
                if row:
                    if row[0] != fingerprint:
                        raise HTTPException(409, "같은 Idempotency-Key를 다른 이미지나 설정에 사용할 수 없습니다.")
                    return json.loads(row[1]), False
            db.execute("INSERT INTO survey_sessions VALUES(?,?,?,?)",
                       (session["session_id"], request_key, fingerprint, json.dumps(session, ensure_ascii=False)))
        return session, True

    def get(self, session_id):
        with self.store.connect() as db:
            row = db.execute("SELECT payload FROM survey_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "없는 설문 세션입니다.")
        return json.loads(row[0])

    def edit(self, session_id, change):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM survey_sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                raise HTTPException(404, "없는 설문 세션입니다.")
            session = json.loads(row[0])
            result = change(session)
            session["updated_at"] = time.time()
            db.execute("UPDATE survey_sessions SET payload=? WHERE id=?",
                       (json.dumps(session, ensure_ascii=False), session_id))
        return session, result

    def recover_interrupted(self):
        # 단일 서버 프로세스 전용. 재시작 때 진행 중이던 작업을 실패로 복구합니다.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for sid, payload in db.execute("SELECT id,payload FROM survey_sessions").fetchall():
                session = json.loads(payload)
                state = session["status"]
                if state not in BUSY_STATES:
                    continue
                failed = {"ANALYZING": "ANALYSIS_FAILED", "BUILDING_SURVEY": "SURVEY_FAILED", "GENERATING": "GENERATION_FAILED"}[state]
                session["status"] = failed
                session["error"] = {"stage": state, "message": "서버 재시작으로 작업이 중단되었습니다. 명시적으로 재시도하세요.", "status_code": 503}
                for photo in session.get("images", []):
                    if photo["status"] == "ANALYZING":
                        photo["status"] = "FAILED"
                        photo["error"] = session["error"]["message"]
                for generation in session["generations"]:
                    if generation["state"] == "GENERATING":
                        generation["state"] = "GENERATION_FAILED"
                session["updated_at"] = time.time()
                db.execute("UPDATE survey_sessions SET payload=? WHERE id=?", (json.dumps(session, ensure_ascii=False), sid))


def current_result(session):
    for generation in reversed(session["generations"]):
        if generation["answers_revision"] == session["answers_revision"] and generation.get("result"):
            return generation["result"]
    return None


def session_images(session):
    # 기존 한 장 세션도 조회·재시도할 수 있도록 저장된 해시로 복원합니다.
    if "images" in session:
        return session["images"]
    return [{"image_id": "img_1", "sha256": session["image_hash"], "analysis": session["analysis"],
             "status": "COMPLETED" if session["analysis"] else "PENDING", "error": None}]


def public_session(session):
    return {key: session[key] for key in (
        "session_id", "status", "created_at", "updated_at", "profile", "analysis", "survey",
        "survey_revision", "answers", "answers_revision", "mock", "calls", "error"
    )} | {
        "entry_date": session.get("entry_date"),
        "images": [{key: photo[key] for key in ("image_id", "status", "analysis", "error")}
                   for photo in session_images(session)],
        "image_count": len(session_images(session)),
        "result": current_result(session),
        "generation_history": [{key: g[key] for key in ("generation_id", "answers_revision", "rewrite_of", "state", "attempts")}
                               for g in session["generations"]],
    }
