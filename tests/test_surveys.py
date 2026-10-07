import asyncio
import copy
import io
import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.main import create_app
from app.settings import Settings
from app.survey_models import AnswersRequest, GenerateRequest, Profile
from app.survey_tasks import mock_analysis, mock_survey, mock_text


def photo(color="white"):
    output = io.BytesIO()
    Image.new("RGB", (100, 80), color).save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database=str(tmp_path / "surveys.sqlite3")))


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


def create(client, profile="default", headers=None):
    response = client.post("/api/image-surveys", files={"image": ("photo.png", photo(), "image/png")},
                           data={"profile_id": profile}, headers=headers or {})
    assert response.status_code == 201, response.text
    return response.json()


def answers(session, option=0):
    return {"survey_revision": session["survey_revision"], "answers": [
        {"question_id": q["id"], "option_id": q["options"][option]["id"]} for q in session["survey"]["questions"]]}


def submit(client, session, option=0):
    response = client.put(f"/api/image-surveys/{session['session_id']}/answers", json=answers(session, option))
    assert response.status_code == 200, response.text
    return response.json()


def generate(client, session, rewrite_of=None):
    body = {"answers_revision": session["answers_revision"]}
    if rewrite_of:
        body["rewrite_of"] = rewrite_of
    return client.post(f"/api/image-surveys/{session['session_id']}/generate", json=body)


def live_stub(app, monkeypatch, modifier=None):
    engine = app.state.engine
    engine.settings.mock = False
    engine.settings.api_key = "fake-key-never-sent"
    calls = []
    async def complete(payload, model):
        profile = app.state.surveys.profiles["default"]
        content = payload["messages"][-1]["content"]
        input_text = content[0]["text"] if isinstance(content, list) else content
        data = json.loads(json.loads(input_text)["input"])
        if isinstance(content, list):
            stage, output = "analysis", mock_analysis()
        elif "answers" in data:
            stage, output = "text", mock_text(profile, data["answers"])
        else:
            stage, output = "survey", mock_survey(profile)
        calls.append({"stage": stage, "data": data, "model": model, "payload": payload})
        finish = "stop"
        if modifier:
            output, finish = modifier(stage, output)
        return {"message": {"content": json.dumps(output, ensure_ascii=False)}, "finishReason": finish,
                "usage": {"promptTokens": 10, "completionTokens": 5}}
    monkeypatch.setattr(engine.provider, "complete", complete)
    return calls


def test_full_mock_flow_and_generation_reuse(client):
    session = create(client)
    assert session["status"] == "SURVEY_READY"
    assert session["mock"] and "MOCK" in session["analysis"]["summary"]
    assert len(session["survey"]["questions"]) == 5
    assert len(session["calls"]) == 2
    session = submit(client, session)
    assert session["status"] == "READY_TO_GENERATE" and session["answers_revision"] == 1
    result = generate(client, session).json()
    assert result["status"] == "COMPLETED" and result["mock"]
    assert len(result["text"]) == result["length"]["actual_chars"]
    assert 1200 <= result["length"]["actual_chars"] <= 1800
    duplicate = generate(client, session).json()
    assert duplicate["generation_id"] == result["generation_id"] and duplicate["reused"]
    saved = client.get(f"/api/image-surveys/{session['session_id']}").json()
    assert len(saved["calls"]) == 3 and saved["result"]["generation_id"] == result["generation_id"]
    assert client.get("/api/usage").json()["live_call_attempts"] == 0


def test_answers_change_invalidates_result_and_noop_does_not(client):
    session = submit(client, create(client))
    first = generate(client, session).json()
    same = submit(client, session)
    assert same["answers_revision"] == session["answers_revision"]
    assert same["result"]["generation_id"] == first["generation_id"]
    changed = submit(client, session, 1)
    assert changed["answers_revision"] == 2 and changed["result"] is None
    assert changed["status"] == "READY_TO_GENERATE"
    assert generate(client, session).status_code == 409
    second = generate(client, changed).json()
    assert second["generation_id"] != first["generation_id"]
    assert second["text"] != first["text"]
    assert "예시 선택 2" in second["text"]
    assert generate(client, changed, first["generation_id"]).status_code == 422


def test_partial_answers_replacement_and_validation(client):
    session = create(client)
    path = f"/api/image-surveys/{session['session_id']}/answers"
    request = answers(session)
    request["answers"] = request["answers"][:1]
    partial = client.put(path, json=request).json()
    assert partial["status"] == "ANSWERING"
    assert generate(client, partial).status_code == 422
    duplicate = copy.deepcopy(request)
    duplicate["answers"] *= 2
    assert client.put(path, json=duplicate).status_code == 422
    invalid = copy.deepcopy(request)
    invalid["answers"][0]["option_id"] = "q_2_o_1"
    assert client.put(path, json=invalid).status_code == 422
    assert client.put(path, json={"survey_revision": 2, "answers": []}).status_code == 409
    assert client.put(path, json={"survey_revision": 1, "answers": [], "extra": "forbidden"}).status_code == 422
    empty = client.put(path, json={"survey_revision": 1, "answers": []}).json()
    assert empty["answers"] == [] and empty["result"] is None


def test_profiles_configuration_and_snapshot(client, app):
    profile_ids = {p["id"] for p in client.get("/api/survey-profiles").json()}
    assert profile_ids == {"default", "study"}
    session = create(client, "study")
    assert len(session["survey"]["questions"]) == 3
    assert all(len(q["options"]) == 4 for q in session["survey"]["questions"])
    app.state.surveys.profiles["study"]["output"]["target_chars"] = 4000
    session = submit(client, session)
    result = generate(client, session).json()
    assert result["length"]["target_chars"] == 1200
    assert [s["id"] for s in result["sections"]] == ["concepts", "study_plan", "practice"]


@pytest.mark.parametrize("change", [
    {"question_count": 2}, {"min_options": 6, "max_options": 3}, {"slots": ["goal", "goal"]},
])
def test_profile_rejects_inconsistent_survey(app, change):
    profile = copy.deepcopy(app.state.surveys.profiles["default"])
    profile["survey"].update(change)
    with pytest.raises(ValidationError):
        Profile.model_validate(profile)


def test_unsupported_modes_and_formats(app):
    profile = copy.deepcopy(app.state.surveys.profiles["default"])
    profile["output"]["generation_mode"] = "per_section"
    with pytest.raises(ValidationError):
        Profile.model_validate(profile)
    profile["output"]["generation_mode"] = "single"
    profile["output"]["format"] = "html"
    with pytest.raises(ValidationError):
        Profile.model_validate(profile)


def test_idempotency_key_prevents_duplicate_session(client):
    first = create(client, headers={"Idempotency-Key": "image-1"})
    second = create(client, headers={"Idempotency-Key": "image-1"})
    assert first["session_id"] == second["session_id"]
    assert len(second["calls"]) == 2
    assert client.post("/api/image-surveys", files={"image": ("other.png", photo("black"))},
                       headers={"Idempotency-Key": "image-1"}).status_code == 409


def test_invalid_image_profile_and_auth(client, tmp_path):
    assert client.post("/api/image-surveys", files={"image": ("bad.png", b"bad")}).status_code == 422
    assert client.post("/api/image-surveys", files={"image": ("photo.png", photo())}, data={"profile_id": "../../.env"}).status_code == 404
    protected = create_app(Settings(database=str(tmp_path / "protected.sqlite3"), team_key="secret"))
    with TestClient(protected) as secured:
        assert secured.get("/api/survey-profiles").status_code == 401
        assert secured.post("/api/image-surveys", files={"image": ("photo.png", photo())}).status_code == 401
        preflight = secured.options("/api/image-surveys/id/answers", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "PUT", "Access-Control-Request-Headers": "Idempotency-Key,X-Team-Key"})
        assert preflight.status_code == 200


def test_provider_three_calls_and_resolved_answer_text(app, client, monkeypatch):
    calls = live_stub(app, monkeypatch)
    session = submit(client, create(client), 1)
    assert generate(client, session).status_code == 200
    assert [c["stage"] for c in calls] == ["analysis", "survey", "text"]
    assert calls[0]["model"] == "HCX-005"
    assert calls[1]["model"] == calls[2]["model"] == "HCX-DASH-002"
    for answer in calls[-1]["data"]["answers"]:
        assert answer["question"] and answer["selected_option"]["label"] == "예시 선택 2"
    assert client.get("/api/usage").json()["total_tokens"] == 45
    assert generate(client, session).json()["reused"]
    assert len(calls) == 3


def test_unusable_image_stops_survey_call(app, client, monkeypatch):
    def unusable(stage, output):
        if stage == "analysis":
            output.update(usable=False, issue="이미지의 글자가 읽히지 않습니다.", observations=[])
        return output, "stop"
    calls = live_stub(app, monkeypatch, unusable)
    session = create(client)
    assert session["status"] == "NEEDS_IMAGE" and session["survey"] is None
    assert len(calls) == 1


def test_invalid_analysis_evidence_requires_original_image_retry(app, client, monkeypatch):
    invalid = True
    def broken(stage, output):
        if stage == "analysis" and invalid:
            output["interpretations"] = [{"detail": "임의 해석", "evidence_ids": ["missing"]}]
        return output, "stop"
    calls = live_stub(app, monkeypatch, broken)
    failed = client.post("/api/image-surveys", files={"image": ("photo.png", photo())})
    assert failed.status_code == 502
    sid = failed.json()["detail"]["session_id"]
    assert failed.json()["detail"]["status"] == "ANALYSIS_FAILED"
    assert client.post(f"/api/image-surveys/{sid}/retry").status_code == 422
    assert client.post(f"/api/image-surveys/{sid}/retry", files={"image": ("different.png", photo("black"))}).status_code == 409
    invalid = False
    retried = client.post(f"/api/image-surveys/{sid}/retry", files={"image": ("photo.png", photo())})
    assert retried.status_code == 200 and retried.json()["status"] == "SURVEY_READY"
    assert [c["stage"] for c in calls] == ["analysis", "analysis", "survey"]


def test_profile_image_limit_and_resize_are_applied(app, client, monkeypatch):
    profile = app.state.surveys.profiles["default"]
    profile["image"].update(max_upload_mb=1, resize_long_edge=64)
    assert client.post("/api/image-surveys", files={"image": ("large.png", b"a" * (1024 * 1024 + 1))}).status_code == 413
    calls = live_stub(app, monkeypatch)
    create(client)
    uri = calls[0]["payload"]["messages"][-1]["content"][1]["dataUri"]["data"]
    import base64
    with Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))) as prepared:
        assert max(prepared.size) == 64


def test_invalid_output_section_order_records_failure(app, client, monkeypatch):
    def reverse(stage, output):
        if stage == "text":
            output["sections"].reverse()
        return output, "stop"
    calls = live_stub(app, monkeypatch, reverse)
    session = submit(client, create(client))
    assert generate(client, session).status_code == 502
    saved = client.get(f"/api/image-surveys/{session['session_id']}").json()
    assert saved["status"] == "GENERATION_FAILED" and saved["result"] is None
    assert len(calls) == 3 and client.get("/api/usage").json()["total_tokens"] == 45


def test_invalid_survey_not_cached_and_retry_skips_analysis(app, client, monkeypatch):
    fail = True
    def invalid(stage, output):
        if stage == "survey" and fail:
            output["questions"][1]["slot"] = "goal"  # 형식은 유효하지만 필수 slot 누락
        return output, "stop"
    calls = live_stub(app, monkeypatch, invalid)
    response = client.post("/api/image-surveys", files={"image": ("photo.png", photo())})
    assert response.status_code == 502
    sid = response.json()["detail"]["session_id"]
    assert client.get(f"/api/image-surveys/{sid}").json()["status"] == "SURVEY_FAILED"
    fail = False
    retried = client.post(f"/api/image-surveys/{sid}/retry")
    assert retried.status_code == 200 and retried.json()["status"] == "SURVEY_READY"
    assert [c["stage"] for c in calls] == ["analysis", "survey", "survey"]
    assert client.get("/api/usage").json()["total_tokens"] == 45


def test_short_text_and_one_rewrite(app, client, monkeypatch):
    def short(stage, output):
        if stage == "text":
            for section in output["sections"]:
                section["body"] = "짧은 글"
        return output, "stop"
    calls = live_stub(app, monkeypatch, short)
    session = submit(client, create(client))
    original = generate(client, session).json()
    assert original["status"] == "NEEDS_REVIEW" and original["length"]["status"] == "too_short"
    rewrite = generate(client, session, original["generation_id"]).json()
    assert rewrite["generation_id"] != original["generation_id"]
    assert "previous_result" in calls[-1]["data"]
    assert generate(client, session, original["generation_id"]).json()["reused"]
    assert generate(client, session, rewrite["generation_id"]).status_code == 422
    assert len(calls) == 4


def test_truncation_records_failure_and_explicit_retry(app, client, monkeypatch):
    truncate = True
    def truncated(stage, output):
        return output, "length" if stage == "text" and truncate else "stop"
    calls = live_stub(app, monkeypatch, truncated)
    session = submit(client, create(client))
    response = generate(client, session)
    assert response.status_code == 502
    saved = client.get(f"/api/image-surveys/{session['session_id']}").json()
    assert saved["status"] == "GENERATION_FAILED" and saved["result"] is None
    truncate = False
    assert generate(client, session).status_code == 200
    saved = client.get(f"/api/image-surveys/{session['session_id']}").json()
    assert saved["generation_history"][0]["attempts"] == 2
    assert len(calls) == 4


def test_restart_preserves_result_and_recovers_interrupted(app, client):
    session = submit(client, create(client))
    result = generate(client, session).json()
    service = app.state.surveys
    other = create(client)
    service.repo.edit(other["session_id"], lambda s: s.update(status="BUILDING_SURVEY"))
    restarted = create_app(app.state.engine.settings)
    with TestClient(restarted) as second:
        saved = second.get(f"/api/image-surveys/{session['session_id']}").json()
        assert saved["result"]["generation_id"] == result["generation_id"]
        interrupted = second.get(f"/api/image-surveys/{other['session_id']}").json()
        assert interrupted["status"] == "SURVEY_FAILED"
        assert second.post(f"/api/image-surveys/{other['session_id']}/retry").json()["status"] == "SURVEY_READY"


def test_mode_change_rejects_mock_session_in_live_mode(app, client):
    session = submit(client, create(client))
    app.state.engine.settings.mock = False
    assert generate(client, session).status_code == 409


def test_concurrent_generate_and_answers_are_rejected(app):
    async def scenario():
        service = app.state.surveys
        session = await service.create(photo(), "default")
        session = service.save_answers(session["session_id"], AnswersRequest.model_validate(answers(session)))
        engine = app.state.engine
        engine.settings.mock = False
        engine.settings.api_key = "fake-key"
        service.repo.edit(session["session_id"], lambda s: s.update(mock=False))
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def complete(payload, model):
            calls.append(payload)
            started.set()
            await release.wait()
            output = mock_text(session["profile"], service.resolve_answers(service.repo.get(session["session_id"])))
            return {"message": {"content": json.dumps(output)}, "finishReason": "stop", "usage": {"promptTokens": 10, "completionTokens": 5}}
        engine.provider.complete = complete
        request = GenerateRequest(answers_revision=session["answers_revision"])
        pending = asyncio.create_task(service.generate(session["session_id"], request))
        await asyncio.wait_for(started.wait(), timeout=2)
        try:
            with pytest.raises(HTTPException) as duplicate:
                await service.generate(session["session_id"], request)
            assert duplicate.value.status_code == 409
            with pytest.raises(HTTPException) as edit:
                service.save_answers(session["session_id"], AnswersRequest.model_validate(answers(session, 1)))
            assert edit.value.status_code == 409
        finally:
            release.set()
        result = await pending
        assert result["status"] == "COMPLETED" and len(calls) == 1
    asyncio.run(scenario())


def test_cancelled_generation_unlocks_session(app):
    async def scenario():
        service = app.state.surveys
        session = await service.create(photo(), "default")
        session = service.save_answers(session["session_id"], AnswersRequest.model_validate(answers(session)))
        app.state.engine.settings.mock = False
        app.state.engine.settings.api_key = "fake-key"
        service.repo.edit(session["session_id"], lambda s: s.update(mock=False))
        started = asyncio.Event()
        async def complete(payload, model):
            started.set()
            await asyncio.Event().wait()
        app.state.engine.provider.complete = complete
        task = asyncio.create_task(service.generate(session["session_id"], GenerateRequest(answers_revision=session["answers_revision"])))
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        saved = service.get(session["session_id"])
        assert saved["status"] == "GENERATION_FAILED"
        assert saved["generation_history"][0]["state"] == "GENERATION_FAILED"
        updated = service.save_answers(session["session_id"], AnswersRequest.model_validate(answers(session, 1)))
        assert updated["status"] == "READY_TO_GENERATE"
        assert app.state.engine.store.usage()["unknown_usage_calls"] == 1
    asyncio.run(scenario())
