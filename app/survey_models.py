"""API 입력과 주제 설정. 숫자·형식·지원 범위를 여기서 바꿉니다."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CallConfig(StrictModel):
    max_tokens: int = Field(ge=1, le=4096)
    temperature: float = Field(ge=0, le=1)


class ImageConfig(CallConfig):
    focus: str = Field(min_length=1, max_length=2000)
    max_images: int = Field(default=5, ge=1, le=10)
    max_upload_mb: int = Field(default=10, ge=1, le=20)
    max_total_upload_mb: int = Field(default=25, ge=1, le=100)
    resize_long_edge: int = Field(default=1280, ge=32, le=2240)


class SurveyConfig(CallConfig):
    question_count: int = Field(ge=1, le=12)
    min_options: int = Field(ge=2, le=8)
    max_options: int = Field(ge=2, le=8)
    question_max_chars: int = Field(ge=30, le=200)
    option_max_chars: int = Field(ge=15, le=100)
    slots: list[str] = Field(min_length=1, max_length=12)
    include_unknown_option: bool = True

    @model_validator(mode="after")
    def check_consistency(self):
        if self.min_options > self.max_options:
            raise ValueError("min_options는 max_options 이하여야 합니다.")
        if len(set(self.slots)) != len(self.slots) or any(not s.strip() or len(s) > 80 for s in self.slots):
            raise ValueError("slots는 80자 이하의 서로 다른 비어 있지 않은 이름이어야 합니다.")
        if self.question_count < len(self.slots):
            raise ValueError("question_count는 slots 개수 이상이어야 합니다.")
        return self


class SectionConfig(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    title: str = Field(min_length=1, max_length=100)


class OutputConfig(CallConfig):
    format: Literal["markdown"] = "markdown"
    tone: str = Field(min_length=1, max_length=1000)
    target_chars: int = Field(ge=300, le=6000)
    length_tolerance_ratio: float = Field(ge=0, lt=1)
    sections: list[SectionConfig] = Field(min_length=1, max_length=10)
    generation_mode: Literal["single"] = "single"

    @model_validator(mode="after")
    def unique_sections(self):
        if len({s.id for s in self.sections}) != len(self.sections):
            raise ValueError("섹션 ID가 중복되었습니다.")
        return self


class Profile(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    version: int = Field(ge=1)
    domain: str = Field(min_length=1, max_length=200)
    audience: str = Field(min_length=1, max_length=500)
    objective: str = Field(min_length=1, max_length=2000)
    image: ImageConfig
    survey: SurveyConfig
    output: OutputConfig


class Observation(StrictModel):
    id: str = Field(min_length=1, max_length=50)
    detail: str = Field(min_length=1, max_length=350)


class Interpretation(StrictModel):
    detail: str = Field(min_length=1, max_length=350)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class Analysis(StrictModel):
    summary: str = Field(min_length=1, max_length=1000)
    observations: list[Observation] = Field(max_length=12)
    visible_text: list[str] = Field(max_length=20)
    interpretations: list[Interpretation] = Field(max_length=8)
    uncertainties: list[str] = Field(max_length=12)
    usable: bool
    issue: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_evidence(self):
        ids = {o.id for o in self.observations}
        if len(ids) != len(self.observations):
            raise ValueError("관찰 ID가 중복되었습니다.")
        if any(set(i.evidence_ids) - ids for i in self.interpretations):
            raise ValueError("해석이 존재하지 않는 관찰 ID를 참조합니다.")
        if self.usable and not self.observations:
            raise ValueError("분석 가능한 이미지에는 관찰 정보가 필요합니다.")
        if not self.usable and not self.issue:
            raise ValueError("분석 불가 사유가 필요합니다.")
        if any(len(s) > 350 for s in self.visible_text + self.uncertainties):
            raise ValueError("분석 문장이 너무 깁니다.")
        return self


class OptionDraft(StrictModel):
    label: str = Field(min_length=1, max_length=100)
    is_unknown: bool


class QuestionDraft(StrictModel):
    slot: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=200)
    options: list[OptionDraft] = Field(min_length=2, max_length=8)


class SurveyDraft(StrictModel):
    questions: list[QuestionDraft] = Field(min_length=1, max_length=12)


class SectionDraft(StrictModel):
    id: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=10000)


class TextDraft(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    sections: list[SectionDraft] = Field(min_length=1, max_length=10)


class Answer(StrictModel):
    question_id: str = Field(min_length=1, max_length=50)
    option_id: str = Field(min_length=1, max_length=50)


class AnswersRequest(StrictModel):
    survey_revision: int = Field(ge=1)
    answers: list[Answer] = Field(max_length=12)


class GenerateRequest(StrictModel):
    answers_revision: int = Field(ge=1)
    rewrite_of: str | None = Field(default=None, min_length=1, max_length=50)
