"""프롬프트·JSON 검사·모의 결과. 흐름 변경은 survey.py, 주제 변경은 profiles/."""
import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from .survey_models import Analysis, Profile, SurveyDraft, TextDraft


def load_profiles(path):
    profiles = {}
    for file in sorted(Path(path).glob("*.json")):
        profile = Profile.model_validate_json(file.read_text(encoding="utf-8"))
        if profile.id in profiles:
            raise ValueError(f"중복 profile ID: {profile.id}")
        profiles[profile.id] = profile.model_dump()
    if not profiles:
        raise ValueError(f"주제 설정 JSON이 없습니다: {path}")
    return profiles


def validate_analysis(data):
    try:
        Analysis.model_validate(data)
    except ValidationError:
        raise HTTPException(502, "AI 이미지 분석의 관찰·근거·문장 형식이 유효하지 않습니다.") from None


def validate_survey(data, profile):
    try:
        draft = SurveyDraft.model_validate(data)
        config = profile["survey"]
        questions = draft.questions
        if len(questions) != config["question_count"]:
            raise ValueError()
        slots = {q.slot for q in questions}
        if slots != set(config["slots"]):
            raise ValueError()
        if len({q.question for q in questions}) != len(questions):
            raise ValueError()
        for q in questions:
            if len(q.question) > config["question_max_chars"] or not config["min_options"] <= len(q.options) <= config["max_options"]:
                raise ValueError()
            if any(len(o.label) > config["option_max_chars"] for o in q.options):
                raise ValueError()
            if len({o.label for o in q.options}) != len(q.options):
                raise ValueError()
            if config["include_unknown_option"] and not any(o.is_unknown for o in q.options):
                raise ValueError()
    except (ValidationError, ValueError):
        raise HTTPException(502, "AI 설문의 질문 수·선택지·필수 항목이 주제 설정과 맞지 않습니다.") from None


def validate_text(data, profile):
    try:
        draft = TextDraft.model_validate(data)
        if [s.id for s in draft.sections] != [s["id"] for s in profile["output"]["sections"]]:
            raise ValueError()
    except (ValidationError, ValueError):
        raise HTTPException(502, "AI 글의 섹션 ID·순서·본문이 지정한 형식과 다릅니다.") from None


def decorate_survey(data):
    questions = []
    for index, q in enumerate(data["questions"], 1):
        qid = f"q_{index}"
        questions.append({"id": qid, "slot": q["slot"], "question": q["question"], "type": "single_choice", "required": True,
                          "options": [{"id": f"{qid}_o_{i}", **option} for i, option in enumerate(q["options"], 1)]})
    return {"questions": questions}


def assemble_text(title, sections):
    return title + "".join(f"\n\n## {s['title']}\n{s['body']}" for s in sections)


def mock_analysis():
    return {"summary": "[MOCK] 업로드 연결 확인용 예시이며 실제 사진을 분석하지 않았습니다.",
            "observations": [{"id": "obs_1", "detail": "[MOCK] 실제 관찰 결과가 아닌 연습 데이터입니다."}],
            "visible_text": [], "interpretations": [], "uncertainties": ["실제 이미지 내용은 확인하지 않았습니다."],
            "usable": True, "issue": None}


def mock_survey(profile):
    config = profile["survey"]
    labels = {"goal": "목표", "current_situation": "현재 상황", "preference": "선호", "constraints": "제약", "priority": "우선순위",
              "main_memory": "가장 기억에 남은 순간", "companionship": "주로 함께한 사람", "emotion": "하루의 감정", "personal_meaning": "남기고 싶은 의미"}
    diary_options = {"main_memory": ["작은 일상의 순간", "새로운 경험", "함께한 시간"],
                     "companionship": ["혼자", "친구·동료", "가족·연인"],
                     "emotion": ["편안했어요", "설렜어요", "피곤했어요"],
                     "personal_meaning": ["작은 즐거움", "새롭게 느낀 점", "함께한 시간의 의미"]}
    questions = []
    for index in range(config["question_count"]):
        slot = config["slots"][index % len(config["slots"])]
        count = config["min_options"]
        options = [{"label": f"예시 선택 {n + 1}", "is_unknown": False} for n in range(count)]
        if slot in diary_options:
            for option, label in zip(options, diary_options[slot]):
                option["label"] = label[:config["option_max_chars"]]
        if config["include_unknown_option"]:
            options[-1] = {"label": "기억 안 남·쓰지 않음" if slot in diary_options else "아직 정하지 않았어요", "is_unknown": True}
        question = f"[MOCK {index + 1}] {labels.get(slot, slot)} 선택?"[:config["question_max_chars"]]
        questions.append({"slot": slot, "question": question, "options": options})
    return {"questions": questions}


def mock_text(profile, resolved_answers, entry_date=None):
    title = f"[MOCK] {profile['domain']} 응답 기반 글"[:200]
    if entry_date:
        title = f"{entry_date} {title}"[:200]
    headings = profile["output"]["sections"]
    answers = "; ".join(f"{a['slot']}: {a['selected_option']['label']}" for a in resolved_answers)
    unit = f"[MOCK] 실제 AI 생성이 아닌 연결 연습용 문장입니다. 선택한 답변은 {answers}입니다.\n"
    overhead = len(assemble_text(title, [{**s, "body": ""} for s in headings]))
    budget = max(len(headings), profile["output"]["target_chars"] - overhead)
    sections = []
    for i, section in enumerate(headings):
        size = budget // len(headings) + (1 if i < budget % len(headings) else 0)
        body = (unit * (size // len(unit) + 1))[:size].strip()
        sections.append({"id": section["id"], "body": body or "[MOCK]"})
    return {"title": title, "sections": sections}


class TaskFactory:
    def __init__(self, path):
        self.prompts = json.loads(Path(path).read_text(encoding="utf-8"))
        for name in ("image_analysis", "survey_generation", "text_generation"):
            if not isinstance(self.prompts.get(name), str) or not self.prompts[name].strip():
                raise ValueError(f"설문 프롬프트가 필요합니다: {name}")

    def snapshot(self):
        return dict(self.prompts)

    def task(self, name, profile, prompts, fixture):
        stage = {"image_analysis": "image", "survey_generation": "survey", "text_generation": "output"}[name]
        model = {"image_analysis": Analysis, "survey_generation": SurveyDraft, "text_generation": TextDraft}[name]
        schema = model.model_json_schema()
        if name == "survey_generation":
            config = profile["survey"]
            schema["properties"]["questions"].update(minItems=config["question_count"], maxItems=config["question_count"])
            qprops = schema["$defs"]["QuestionDraft"]["properties"]
            qprops["slot"]["enum"] = config["slots"]
            qprops["question"]["maxLength"] = config["question_max_chars"]
            qprops["options"].update(minItems=config["min_options"], maxItems=config["max_options"])
            schema["$defs"]["OptionDraft"]["properties"]["label"]["maxLength"] = config["option_max_chars"]
        if name == "text_generation":
            sections = profile["output"]["sections"]
            schema["properties"]["sections"].update(minItems=len(sections), maxItems=len(sections))
            schema["$defs"]["SectionDraft"]["properties"]["id"]["enum"] = [s["id"] for s in sections]
        return {"prompt": prompts[name] + "\n주제별 설정:\n" + json.dumps(profile, ensure_ascii=False),
                "schema": schema, "max_tokens": profile[stage]["max_tokens"],
                "temperature": profile[stage]["temperature"], "mock_output": fixture}
