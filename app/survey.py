"""이미지 → 설문 → 답변 → 글 흐름. 분기·재작성 정책은 이 파일에서 수정합니다."""
import asyncio
import hashlib
import json
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from .images import image_data_uri
from .survey_models import Analysis, SurveyDraft, TextDraft
from .survey_store import BUSY_STATES, SurveyStore, current_result, public_session, session_images
from .survey_tasks import (
    TaskFactory, assemble_text, decorate_survey, load_profiles, mock_analysis, mock_survey,
    mock_text, validate_analysis, validate_survey, validate_text,
)


# 이미지 분석·설문·답변 등을 합친 서버 입력 한도. 토큰 수와 같은 단위는 아닙니다.
MAX_INPUT_CHARS = 24000
KOREA_TIMEZONE = timezone(timedelta(hours=9))


class SurveyService:
    def __init__(self, engine):
        self.engine = engine
        self.profiles = load_profiles(engine.settings.profiles_path)
        self.factory = TaskFactory(engine.settings.survey_prompts_path)
        self.repo = SurveyStore(engine.store)

    def get_profile(self, profile_id):
        if profile_id not in self.profiles:
            raise HTTPException(404, "없는 profile_id입니다. GET /api/survey-profiles를 확인하세요.")
        return self.profiles[profile_id]

    def check_mode(self, session):
        if session["mock"] != self.engine.settings.mock:
            raise HTTPException(409, "세션 생성 당시와 MOCK_MODE가 다릅니다. 새 세션을 만드세요.")

    def prepare_image(self, raw, profile):
        limit = profile["image"]["max_upload_mb"] * 1024 * 1024
        if len(raw) > limit:
            raise HTTPException(413, f"이미지는 {profile['image']['max_upload_mb']}MB 이하로 업로드하세요.")
        return image_data_uri(raw, profile["image"]["resize_long_edge"])

    def prepare_images(self, raw, profile):
        # 내부 호출의 bytes와 기존 image 필드를 그대로 지원합니다.
        raws = [raw] if isinstance(raw, bytes) else list(raw)
        config = profile["image"]
        max_images = config.get("max_images", 1)
        if not 1 <= len(raws) <= max_images:
            raise HTTPException(422, f"사진은 1~{max_images}장 업로드하세요.")
        total_mb = config.get("max_total_upload_mb", config["max_upload_mb"] * max_images)
        if sum(len(item) for item in raws) > total_mb * 1024 * 1024:
            raise HTTPException(413, f"사진 전체 용량은 {total_mb}MB 이하로 업로드하세요.")
        images = [self.prepare_image(item, profile) for item in raws]
        return images, [hashlib.sha256(item).hexdigest() for item in raws]

    def get(self, session_id):
        return public_session(self.repo.get(session_id))

    async def create(self, raw, profile_id, request_key=None, entry_date=None):
        profile = self.get_profile(profile_id)
        images, hashes = self.prepare_images(raw, profile)
        if entry_date is None:
            entry_date = datetime.now(KOREA_TIMEZONE).date()
        try:
            entry_date = date.fromisoformat(entry_date) if isinstance(entry_date, str) else entry_date
            day = entry_date.isoformat()
        except (ValueError, AttributeError):
            raise HTTPException(422, "entry_date는 YYYY-MM-DD 형식의 날짜여야 합니다.") from None
        prompts = self.factory.snapshot()
        fingerprint = hashlib.sha256(json.dumps({"images": hashes, "entry_date": day, "profile": profile, "prompts": prompts,
                                                  "mock": self.engine.settings.mock}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        now = time.time()
        session = {"session_id": str(uuid.uuid4()), "status": "ANALYZING", "created_at": now, "updated_at": now,
                   "profile": profile, "prompts": prompts, "entry_date": day, "image_hash": hashes[0],
                   "images": [{"image_id": f"img_{index}", "sha256": value, "status": "PENDING", "analysis": None, "error": None}
                              for index, value in enumerate(hashes, 1)], "analysis": None, "survey": None,
                   "survey_revision": 0, "answers": [], "answers_revision": 0, "generations": [],
                   "mock": self.engine.settings.mock, "calls": [], "error": None}
        session, created = self.repo.create(session, request_key, fingerprint)
        if not created:
            if session["status"] in BUSY_STATES:
                raise HTTPException(409, {"message": "동일 요청을 처리 중입니다.", "session_id": session["session_id"]})
            return public_session(session)
        return await self._run_stages(session["session_id"], images)

    async def retry(self, session_id, raw=None):
        previous = self.repo.get(session_id)
        self.check_mode(previous)
        images = None
        if previous["status"] == "ANALYSIS_FAILED":
            if raw is None:
                raise HTTPException(422, "이미지 분석 재시도에는 원래 사진 전체가 필요합니다.")
            images, hashes = self.prepare_images(raw, previous["profile"])
            if hashes != [photo["sha256"] for photo in session_images(previous)]:
                raise HTTPException(409, "재시도에는 같은 사진 전체를 같은 순서로 보내세요. 다른 사진은 새 세션으로 만드세요.")
        elif previous["status"] == "SURVEY_FAILED":
            if raw is not None:
                raise HTTPException(422, "설문 생성 재시도에는 이미지를 보내지 마세요.")
        else:
            raise HTTPException(409, "분석·설문 생성 실패 상태만 재시도할 수 있습니다. 다른 이미지는 새 세션을 만드세요.")

        def reserve(session):
            if session["status"] != previous["status"]:
                raise HTTPException(409, "이미 처리 중이거나 상태가 바뀌었습니다.")
            session["images"] = session_images(session)
            session["status"] = "ANALYZING" if images else "BUILDING_SURVEY"
            session["error"] = None
        self.repo.edit(session_id, reserve)
        return await self._run_stages(session_id, images)

    async def _call(self, session, name, data, fixture, validator, image=None, image_id=None):
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > MAX_INPUT_CHARS:
            raise HTTPException(413, "AI에 전달할 자료가 너무 깁니다. 사진 수·질문 수·문구 길이·이미지 분석 정보를 줄이세요.")
        task = self.factory.task(name, session["profile"], session["prompts"], fixture)
        result = await self.engine.run(name, text, image=image, override=task, validate_output=validator,
                                       cache=name != "text_generation")
        metadata = {k: result[k] for k in ("model", "mock", "cached", "usage", "finish_reason")}
        if image_id:
            metadata["image_id"] = image_id
        self.repo.edit(session["session_id"], lambda saved: saved["calls"].append({"stage": name, **metadata}))
        return result

    async def _run_stages(self, session_id, images):
        try:
            session = self.repo.get(session_id)
            if session["status"] == "ANALYZING":
                for index, photo in enumerate(session["images"]):
                    if photo["analysis"] is not None:
                        continue
                    def start_photo(saved):
                        saved["images"][index].update(status="ANALYZING", error=None)
                    self.repo.edit(session_id, start_photo)
                    result = await self._call(session, "image_analysis", {"instruction": session["profile"]["image"]["focus"]},
                                              mock_analysis(), validate_analysis, image=images[index], image_id=photo["image_id"])
                    analysis = Analysis.model_validate(result["output"]).model_dump()
                    def save_photo(saved):
                        saved["images"][index].update(status="COMPLETED", analysis=analysis, error=None)
                    session, _ = self.repo.edit(session_id, save_photo)
                usable = [photo for photo in session["images"] if photo["analysis"]["usable"]]
                # 관찰 ID는 각 사진 안에서만 고유합니다. 중첩 구조로 출처를 유지합니다.
                analysis = {"summary": "\n".join(f"{photo['image_id']}: {photo['analysis']['summary']}" for photo in usable),
                            "usable": bool(usable), "issue": None if usable else "사용 가능한 일기·설문 자료가 없습니다. 다른 사진으로 새 세션을 만드세요.",
                            "images": [{"image_id": photo["image_id"], "analysis": photo["analysis"]} for photo in usable],
                            "excluded_images": [{"image_id": photo["image_id"], "issue": photo["analysis"]["issue"]}
                                                for photo in session["images"] if not photo["analysis"]["usable"]]}
                def save_analysis(saved):
                    saved["analysis"] = analysis
                    saved["status"] = "BUILDING_SURVEY" if analysis["usable"] else "NEEDS_IMAGE"
                session, _ = self.repo.edit(session_id, save_analysis)
                if not analysis["usable"]:
                    return public_session(session)
            profile = session["profile"]
            result = await self._call(session, "survey_generation", {"analysis": session["analysis"], "entry_date": session.get("entry_date")},
                                      mock_survey(profile), lambda data: validate_survey(data, profile))
            survey = decorate_survey(SurveyDraft.model_validate(result["output"]).model_dump())
            def save_survey(saved):
                saved["survey"] = survey
                saved["survey_revision"] += 1
                saved["answers"] = []
                saved["answers_revision"] = 0
                saved["status"] = "SURVEY_READY"
                saved["error"] = None
            session, _ = self.repo.edit(session_id, save_survey)
            return public_session(session)
        except BaseException as error:
            self._fail(session_id, error)
            self._raise_failure(session_id, error)

    def save_answers(self, session_id, request):
        def save(session):
            self.check_mode(session)
            if session["status"] in BUSY_STATES:
                raise HTTPException(409, "처리 중에는 답변을 변경할 수 없습니다.")
            if session["survey"] is None:
                raise HTTPException(409, "설문이 아직 준비되지 않았습니다.")
            if request.survey_revision != session["survey_revision"]:
                raise HTTPException(409, "이전 설문 버전의 답변입니다. 설문을 다시 조회하세요.")
            questions = {q["id"]: q for q in session["survey"]["questions"]}
            answers = {}
            for answer in request.answers:
                q = questions.get(answer.question_id)
                if answer.question_id in answers or not q or answer.option_id not in {o["id"] for o in q["options"]}:
                    raise HTTPException(422, "질문 ID 중복 또는 유효하지 않은 질문·선택지 ID입니다.")
                answers[answer.question_id] = answer.option_id
            canonical = [{"question_id": qid, "option_id": answers[qid]} for qid in questions if qid in answers]
            if canonical != session["answers"]:
                session["answers"] = canonical
                session["answers_revision"] += 1
                session["status"] = "READY_TO_GENERATE" if len(canonical) == len(questions) else "ANSWERING"
                session["error"] = None
        session, _ = self.repo.edit(session_id, save)
        return public_session(session)

    @staticmethod
    def resolve_answers(session):
        answers = {a["question_id"]: a["option_id"] for a in session["answers"]}
        return [{"question_id": q["id"], "slot": q["slot"], "question": q["question"],
                 "selected_option": next(o for o in q["options"] if o["id"] == answers[q["id"]])}
                for q in session["survey"]["questions"]]

    async def generate(self, session_id, request):
        def reserve(session):
            self.check_mode(session)
            if session["status"] in BUSY_STATES:
                raise HTTPException(409, "이미 처리 중입니다. 세션 상태를 조회하세요.")
            if request.answers_revision != session["answers_revision"]:
                raise HTTPException(409, "현재 답변 버전과 다릅니다. 세션을 다시 조회하세요.")
            if not session["survey"] or len(session["answers"]) != len(session["survey"]["questions"]):
                raise HTTPException(422, "모든 필수 질문에 답해야 글을 생성할 수 있습니다.")
            generations = [g for g in session["generations"] if g["answers_revision"] == request.answers_revision]
            if request.rewrite_of:
                parent = next((g for g in generations if g["generation_id"] == request.rewrite_of), None)
                if not parent or parent["rewrite_of"] is not None or not parent.get("result"):
                    raise HTTPException(422, "현재 답변 버전의 최초 생성 결과에 대해서만 1회 재작성할 수 있습니다.")
            elif current_result(session):
                return {"reused_result": current_result(session)}
            generation = next((g for g in generations if g["rewrite_of"] == request.rewrite_of), None)
            if generation and generation.get("result"):
                return {"reused_result": generation["result"]}
            if generation is None:
                generation = {"generation_id": str(uuid.uuid4()), "answers_revision": request.answers_revision,
                              "rewrite_of": request.rewrite_of, "state": "GENERATING", "attempts": 0, "result": None}
                session["generations"].append(generation)
            generation["attempts"] += 1
            generation["state"] = "GENERATING"
            session["status"] = "GENERATING"
            session["error"] = None
            return {"generation_id": generation["generation_id"]}

        session, reserved = self.repo.edit(session_id, reserve)
        if "reused_result" in reserved:
            return {**reserved["reused_result"], "reused": True}
        generation_id = reserved["generation_id"]
        try:
            profile = session["profile"]
            resolved = self.resolve_answers(session)
            data = {"analysis": session["analysis"], "answers": resolved, "entry_date": session.get("entry_date")}
            if request.rewrite_of:
                data["previous_result"] = next(g["result"] for g in session["generations"] if g["generation_id"] == request.rewrite_of)
            result = await self._call(session, "text_generation", data, mock_text(profile, resolved, session.get("entry_date")),
                                      lambda value: validate_text(value, profile))
            draft = TextDraft.model_validate(result["output"]).model_dump()
            sections = [{**section, "body": body["body"]} for section, body in zip(profile["output"]["sections"], draft["sections"])]
            text = assemble_text(draft["title"], sections)
            actual = len(text)
            target, tolerance = profile["output"]["target_chars"], profile["output"]["length_tolerance_ratio"]
            length_state = "within_range" if target * (1 - tolerance) <= actual <= target * (1 + tolerance) else ("too_short" if actual < target else "too_long")
            status = "COMPLETED" if length_state == "within_range" else "NEEDS_REVIEW"
            output = {"session_id": session_id, "entry_date": session.get("entry_date"), "answers_revision": request.answers_revision, "generation_id": generation_id,
                      "rewrite_of": request.rewrite_of, "title": draft["title"], "sections": sections, "text": text,
                      "length": {"target_chars": target, "actual_chars": actual, "status": length_state},
                      "status": status, "reused": False, **{k: result[k] for k in ("mock", "model", "usage", "finish_reason")}}
            def finish(saved):
                generation = next(g for g in saved["generations"] if g["generation_id"] == generation_id)
                generation["result"] = output
                generation["state"] = status
                saved["status"] = status
                saved["error"] = None
            self.repo.edit(session_id, finish)
            return output
        except BaseException as error:
            self._fail(session_id, error)
            self._raise_failure(session_id, error)

    def _fail(self, session_id, error):
        def fail(session):
            stage = session["status"]
            session["status"] = {"ANALYZING": "ANALYSIS_FAILED", "BUILDING_SURVEY": "SURVEY_FAILED",
                                 "GENERATING": "GENERATION_FAILED"}.get(stage, stage)
            message = error.detail if isinstance(error, HTTPException) else "작업이 중단되었습니다. 세션 상태를 확인하고 재시도하세요."
            session["error"] = {"stage": stage, "message": message, "status_code": getattr(error, "status_code", 502)}
            for photo in session.get("images", []):
                if photo["status"] == "ANALYZING":
                    photo.update(status="FAILED", error=message)
                    session["error"]["image_id"] = photo["image_id"]
            for generation in session["generations"]:
                if generation["state"] == "GENERATING":
                    generation["state"] = "GENERATION_FAILED"
        self.repo.edit(session_id, fail)

    def _raise_failure(self, session_id, error):
        if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            raise error
        session = self.repo.get(session_id)
        raise HTTPException(session["error"]["status_code"], {"message": session["error"]["message"],
                            "session_id": session_id, "status": session["status"],
                            **({"image_id": session["error"]["image_id"]} if "image_id" in session["error"] else {})}) from error
