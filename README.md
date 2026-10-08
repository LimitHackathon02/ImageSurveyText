# ImageSurveyText — 이미지·설문·텍스트 범용 템플릿

이미지 분석 → 객관식 설문 → 사용자 답변 → 맞춤 글 생성을 연결한 Python + FastAPI 백엔드입니다. 주제 변경은 `profiles/*.json`, 단계별 지시문 변경은 `survey_prompts.json`에서 합니다. 실행 시 다른 AI 서비스를 호출하지 않으며 HyperCLOVA X REST API만 사용합니다. 기본값은 외부 호출 없는 **모의 실행**입니다. 기존 일반 텍스트·이미지·문서 API도 함께 제공합니다.

공통 코드는 이미지 처리·설문 검증·답변 저장·글 생성·실패 복구를 담당하고, 최종 용도는 주제 설정과 프롬프트로 정합니다. 기본 실행은 `default`(사진 기반 맞춤 안내)입니다. 수정 순서는 [TOPIC_ADAPTATION_GUIDE.md](TOPIC_ADAPTATION_GUIDE.md)를 따르세요. 일기에 적용한 구현과 일기 전용 예제는 별도 저장소 [ImageSurveyText_Diary](https://github.com/LimitHackathon02/ImageSurveyText_Diary)에 보존했습니다.

| 꺼내 쓸 흐름 | API | 주제에 맞춰 수정할 파일 |
|---|---|---|
| 이미지 → 설문 → 텍스트 | `/api/image-surveys`와 답변·생성 API | `profiles/*.json`, `survey_prompts.json` |
| 텍스트·맥락 → 텍스트 | `/api/run`의 text, context, history | `tasks.json` |
| 이미지 → 텍스트·JSON | `/api/vision`의 file과 question | `tasks.json` |

질문 수·선택지 수·확인할 정보·출력 목차와 분량은 설정으로 바꿀 수 있습니다. 복수 선택·자유 입력·조건별 질문 분기처럼 흐름 자체가 달라지면 입력 모델과 처리 로직도 수정합니다.

사용자 설명상 대회는 사전 준비가 기본적으로 금지되어 있습니다. **이 프로젝트는 사전 학습·연결 연습용입니다. 코드·설정·가이드의 반입 및 제출물 재사용이 허용된다고 가정하지 않습니다.** 현장에서 직접 작성할 최소 흐름은 `FIELD_GUIDE.md`에 정리했습니다.

## 바로 실행

Python 3.11 이상이 필요합니다. 프로젝트 폴더에서 실행하세요.

```sh
sh scripts/start.sh
```

팀원이 새로 받는 경우에는 아래 순서로 실행합니다.

```sh
git clone https://github.com/LimitHackathon02/ImageSurveyText.git
cd ImageSurveyText
sh scripts/start.sh
```

`scripts/start.sh`가 `.venv`를 만들고, `requirements.txt`를 설치하고, `.env.example`을 `.env`로 복사합니다. 즉 README를 보고 위 명령을 실행하면 기본 모의 실행 환경은 자동으로 준비됩니다. API 키, 지급된 모델명, 팀별 CORS 주소는 각자 생성된 `.env`에 입력해야 하며 `.env` 파일은 저장소에 올리지 않습니다.

macOS/Linux와 Windows WSL에서는 위 명령을 실행합니다. Windows 기본 Python은 아래 PowerShell 명령으로 실행합니다. Python이 없거나 Python 3.11 미만이면 먼저 Python을 설치해야 합니다.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.lock.txt
Copy-Item .env.example .env  # 처음 한 번만: 기존 .env가 있으면 생략
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 **http://localhost:8000/docs**를 열면 프론트엔드 없이 API를 실행할 수 있습니다. `/api/run` → `Try it out`에서 아래 요청을 넣으세요.

```json
{"task":"summarize","text":"지민이 금요일까지 설문을 모으고 토요일에 발표 자료를 완성한다."}
```

`mock: true`는 연결 확인용 고정 예시입니다. 입력 요약·이미지 분석·답변 품질을 검증한 결과가 아닙니다. 모의 실행에서 `usage`는 0입니다.

## 이미지 → 설문 → 글 전체 실행

서버를 실행한 뒤 새 터미널에서 다음 명령으로 전체 흐름을 연습할 수 있습니다.

```sh
.venv/bin/python scripts/survey_demo.py
.venv/bin/python scripts/survey_demo.py --profile default --interactive
.venv/bin/python scripts/survey_demo.py --profile study --interactive
```

API와 CLI의 기본 profile은 `default`입니다. 모의 실행에서 이미지를 생략하면 연습용 빈 이미지를 사용합니다. 모의 설문과 글은 설정과 선택한 답변을 반영해 조립하지만 실제 사진을 이해하거나 AI가 글을 작성한 결과는 아닙니다. 실제 모드에서는 이미지 경로를 지정합니다. 여러 장이면 `--image`를 반복합니다.

```sh
.venv/bin/python scripts/survey_demo.py --image ./photo1.jpg --image ./photo2.jpg --profile default --interactive
```

Swagger의 **이미지 설문** 묶음에서 직접 호출해도 됩니다. Windows 기본 Python에서는 `.venv/bin/python` 대신 `.venv\Scripts\python`을 사용하세요.

| 순서 | API | 입력·결과 |
|---|---|---|
| 설정 조회 | `GET /api/survey-profiles` | 선택할 주제 ID와 설정 목록 |
| 1 | `POST /api/image-surveys` | multipart `images` 반복, `profile_id`, `entry_date` → 사진별 분석, `survey.questions`, `session_id` |
| 2 | `PUT /api/image-surveys/{session_id}/answers` | 설문 버전과 선택 ID → 답변 저장, `answers_revision` |
| 3 | `POST /api/image-surveys/{session_id}/generate` | 답변 버전 → `text`, 분량 상태, `generation_id` |
| 조회 | `GET /api/image-surveys/{session_id}` | 분석·설문·답변·현재 결과·생성 이력 |
| 복구 | `POST /api/image-surveys/{session_id}/retry` | 이미지 분석 또는 설문 생성 실패 단계 재시도 |

업로드 예시입니다. 주제를 추가했다면 `profile_id`를 새 설정의 ID로 바꾸세요.

```sh
curl -X POST http://localhost:8000/api/image-surveys \
  -F 'images=@./photo1.jpg' -F 'images=@./photo2.jpg' \
  -F 'profile_id=default'
```

기존 한 장 입력인 `image`도 지원하며 `images`와 함께 보내면 422입니다. `profile_id` 생략 기본값은 `default`입니다. 자료의 기준 날짜가 필요하면 선택 입력인 `entry_date`를 `YYYY-MM-DD` 형식으로 보내세요. 생략하면 `null`이며 서버가 날짜를 자동 부여하지 않습니다. 새 업로드는 새 세션입니다.

사진은 기본 최대 5장, 한 장 최대 10MB, 전체 최대 25MB입니다. profile의 `image.max_images`, `max_upload_mb`, `max_total_upload_mb`로 바꿉니다. 사진별 분석은 `images`에 저장되며 `analysis.images`는 사용 가능한 사진들, `analysis.excluded_images`는 제외한 사진과 이유입니다. 관찰 ID는 각 `image_id` 안에서 해석합니다. 업로드 순서는 사건의 시간 순서로 간주하지 않습니다.

1단계에서 사진 전체로 질문 목록을 한 번 생성합니다. 화면에서는 하나씩 보여 주면 됩니다. 캐시가 없는 정상 흐름의 실제 AI 호출은 **사진 N장 분석 N회 + 설문 1회 + 글 1회**입니다. 사진 3장이면 5회입니다. 답변 저장에는 AI를 호출하지 않습니다. 모든 사진이 사용 불가능하면 `NEEDS_IMAGE`이며 다른 사진으로 새 세션을 만드세요. 일부만 사용 가능하면 해당 사진들로 진행하고 제외 사유를 반환합니다.

답변 저장 요청 예시는 다음과 같습니다. 전체 답변 교체 방식이므로 부분 저장 시 기존 답변도 함께 보내세요. 필수 질문을 모두 답해야 글을 생성할 수 있습니다.

```json
{
  "survey_revision": 1,
  "answers": [
    {"question_id": "q_1", "option_id": "q_1_o_2"},
    {"question_id": "q_2", "option_id": "q_2_o_1"}
  ]
}
```

글 생성 요청은 `{"answers_revision": 1}`입니다. 실제 요청에는 답변 저장 응답의 버전을 사용하세요. 같은 답변 버전에 대해 다시 요청하면 생성 결과를 재사용하고 `reused: true`를 반환합니다. 이 경우 `usage`는 원본 생성 당시 사용량이며 새 호출이 발생하지 않습니다. 답변을 변경하면 버전이 올라가고 이전 결과는 현재 결과에서 제외됩니다.

`output.target_chars`는 공백·줄바꿈·제목을 포함한 `len(text)` 기준입니다. `default`는 1,500자 ±20%입니다. 길이는 모델 요청만으로 보장되지 않으므로 서버가 측정해 `COMPLETED` 또는 `NEEDS_REVIEW`를 반환합니다. 정보가 부족하면 사실성을 우선해 짧게 생성하고 검토 대상으로 표시할 수 있습니다. 글이 토큰 제한으로 잘리면 `GENERATION_FAILED`이며 완료 결과로 반환하지 않습니다.

완료된 원본 글을 한 번 재작성하려면 `{"answers_revision": 1, "rewrite_of": "원본 generation_id"}`를 보냅니다. 같은 재작성 요청은 재사용하며 재작성 결과를 다시 재작성하는 것은 거절합니다. 실패한 생성은 같은 요청으로 명시적으로 재시도할 수 있고 자동 재호출은 없습니다.

생성 요청 중에는 중복 생성·답변 수정을 409로 거절합니다. 세션 생성에 `Idempotency-Key` 헤더를 지정하고 재전송 시 같은 키·사진 순서·날짜를 유지하면 중복 세션을 방지합니다. 실패 응답의 `detail`에는 `session_id`와 실패 상태, 해당 사진이 있으면 `image_id`가 들어갑니다. `ANALYSIS_FAILED` 재시도에는 원래 사진 **전체를 같은 순서로** 다시 업로드합니다. 이미 성공한 분석은 재사용하고 실패·미처리 사진만 호출합니다. 원본 사진을 저장하지 않으므로 프론트엔드가 재시도용 파일을 유지해야 합니다. `SURVEY_FAILED`는 파일 없이 `/retry`를 호출합니다. 날짜·사진을 바꾸려면 새 세션을 만드세요.

SQLite에는 사진별 해시와 분석·세션·설문·답변·설정과 프롬프트 스냅샷·글·사용량과 선택 입력인 기준 날짜가 저장됩니다. 원본 이미지는 저장하지 않습니다. 서버 재시작 후 진행 중이던 작업은 실패 상태로 복구되며 완료된 사진 분석은 유지됩니다. 기존 한 장 세션도 조회·재시도할 수 있고, 당시 기록하지 않은 날짜는 `null`입니다. 기존 세션의 설정과 프롬프트 스냅샷은 유지되므로 범용 설정을 확인할 때는 새 세션을 만드세요. **단일 서버 프로세스**로 실행해야 하며 `--workers`나 중복 서버를 사용하면 시작 시 복구가 다른 서버의 작업에 영향을 줄 수 있습니다. MOCK_MODE를 전환하면 기존 세션을 이어 쓰지 말고 새 세션을 만드세요.

## 주제와 로직을 수정하는 위치

`profiles/default.json`은 사진 기반 맞춤 안내의 시작 예시(질문 5개, 글 1,500자), `profiles/study.json`은 설정 변경을 보여 주는 학습 예시(질문 3개, 선택지 4개, 글 1,200자)입니다. 모든 주제에서 여러 사진을 지원합니다. 새 JSON을 복사한 뒤 고유 `id`를 정하고 주제·대상·목적·이미지 초점·slots·출력 sections를 바꾸세요. 서버를 재시작하면 `/api/survey-profiles`에 표시됩니다. 새 세션의 `profile_id`로 선택하세요. 기존 세션은 저장한 설정 스냅샷을 사용합니다.

| 바꾸고 싶은 항목 | 수정 위치 |
|---|---|
| 주제·대상·글 목적 | profile의 `domain`, `audience`, `objective` |
| 이미지에서 볼 내용·업로드 한도·해상도 | profile의 `image` |
| 질문 수·선택지 수·확인할 항목 | profile의 `survey` |
| 글 분량·말투·섹션·출력 토큰 한도 | profile의 `output` |
| 이미지 분석·설문·글 생성 지시문 | `survey_prompts.json` |
| 응답 JSON과 설정 값의 허용 범위 | `app/survey_models.py` |
| 질문 품질 검사·모의 결과·글 조립 | `app/survey_tasks.py` |
| 답변 저장·상태 전이·재작성·호출 순서 | `app/survey.py` |
| SQLite 저장·원자적 상태 변경·재시작 복구 | `app/survey_store.py` |
| 이미지 전처리·HTTP API | `app/images.py`, `app/main.py` |

예를 들어 질문을 3개로 줄이려면 `question_count=3`으로 바꾸고 `slots`도 3개 이하로 줄입니다. 선택지 4개를 고정하려면 `min_options`와 `max_options`를 모두 4로 설정합니다. `sections`의 ID와 제목을 바꾸면 생성 지시·검사·최종 글에 반영됩니다. 설정의 `version`도 올려 변경을 추적하세요.

현재 지원 범위는 단일 선택형, 전체 설문 사전 생성, markdown, 글 한 번 생성(`single`)입니다. 복수 선택·자유 입력·답변에 따른 분기·섹션별 장문 생성은 요청 형식과 검증·흐름을 추가해야 합니다. 지원하지 않는 설정 값은 시작 시 오류로 알립니다. 서버에서 합친 설문 생성 입력은 최대 24,000자이며 이는 토큰 제한을 정확하게 계산한 값은 아닙니다.

## 실제 HyperCLOVA X 연결

1. `.env`에 지급받은 `CLOVA_API_KEY`를 입력합니다.
2. 주최 측 모델·API 주소와 `CLOVA_TEXT_MODEL`, `CLOVA_VISION_MODEL`, `CLOVA_BASE_URL`을 맞춥니다.
3. `MOCK_MODE=false`로 바꾼 뒤 서버를 종료하고 다시 실행합니다.
4. `/health`에서 `mock: false`, `api_key_configured: true`를 확인합니다. 이는 설정 확인이며 실제 연결 성공 여부는 `/api/run`에서 확인합니다.

일반 CLOVA Studio v3 REST 형식과 `Authorization: Bearer` 인증을 구현했습니다. 공식 문서는 [텍스트·이미지 API](https://api.ncloud-docs.com/docs/clovastudio-chatcompletionsv3), [API 개요](https://api.ncloud-docs.com/docs/ai-naver-clovastudio-summary)를 참고하세요. 기본 텍스트 모델은 `HCX-DASH-002`, 이미지 모델은 `HCX-005`입니다. **대회 전용 프록시, 구형 이중 키 인증, 추론 전용 모델은 API 형식이 다를 수 있어 `app/provider.py`와 요청 파라미터 확인이 필요합니다.** 모델 이름만 바꾸면 모든 API가 호환되는 것은 아닙니다.

## 기능

| API | 용도 | 주제가 바뀌면 바꿀 부분 |
|---|---|---|
| `GET /api/tasks` | 작업·예제·결과 형식 조회 | `tasks.json` |
| `POST /api/run` | 요약, 분류, 추출, 문장 변환, 계획, 채팅 | task, text, context |
| `POST /api/vision` | 이미지와 질문 분석 | 파일, question, task |
| `POST /api/documents` | 텍스트 자료 저장 | title, text |
| `POST /api/documents/upload` | UTF-8 TXT/MD 파일 저장 | file |
| `GET /api/documents` | 문서 ID 목록 | — |
| `DELETE /api/documents/{id}` | 문서 삭제 | 문서 ID |
| `POST /api/ask` | 검색된 문서 조각을 근거로 답변 생성 | question, document_ids |
| `GET /api/usage` | 호출 시도 수·누적 토큰·사용량 미확인 건 조회 | `.env` 한도 |

`/api/run`의 결과는 `output`에 들어갑니다. JSON 작업은 서버가 스키마를 검사한 뒤 반환합니다. 모델 자체의 Structured Outputs 기능에 의존하지 않는 방식이라 잘못된 JSON이면 502 오류가 날 수 있습니다. 조용히 재호출하거나 임의로 채워 넣지 않습니다.

`history`는 최대 8개, 각 2,000자입니다. 채팅에 사용하려면 `[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]` 형식으로 전달합니다. 대화는 서버가 자동 저장하지 않습니다. 주제를 바꾸면 history도 비우세요.

`/api/vision`은 10MB 이하 PNG/JPEG/WEBP/BMP 한 장을 지원합니다. 긴 변 최대 1,280px로 축소하고 JPEG로 변환하며 비율이 5:1을 넘으면 흰 여백을 추가합니다. 다중 이미지 설문은 `/api/image-surveys`의 profile 한도를 따릅니다. 원본 메타데이터는 전송하지 않습니다. 작은 글자의 인식 정확도는 축소로 낮아질 수 있습니다. 이미지 이해 결과는 전용 OCR의 정확도 보장이 아닙니다.

문서는 10만 자 이하, 전체 1,000개 조각까지 저장합니다. 검색은 한국어 문자 2-gram 유사도이며 **의미 검색·인터넷 검색을 하지 않습니다**. 동의어·짧은 질문에는 관련 자료를 놓칠 수 있습니다. 답변의 `citations`는 서버가 제공한 조각 ID인지 검사합니다. `sources`는 검색 후보이고, 그 중 `citations`에 든 항목이 모델이 사용했다고 표시한 근거입니다. 인용 ID 검사는 답변 사실성까지 보장하지 않습니다. PDF는 텍스트를 복사해서 `/api/documents`에 넣거나 필요한 페이지를 이미지로 분석하세요.

## 주제 공개 후 수정: 코드 대신 작업 설정

`tasks.json`에서 기존 작업을 복사해 작업 ID를 만들고 다음 항목을 바꾸세요.

- `description`: 팀원에게 보여줄 기능 설명
- `prompt`: 누구를 돕고 어떤 결과를 만들 것인지
- `schema`: 프론트엔드에서 쓸 JSON 필드와 필수 항목
- `mock_output`: 그 스키마에 맞는 연습용 응답
- `example_input`: 연습 입력
- `max_tokens`: 출력 길이, 1~4,096
- `temperature`: 0이면 동일 요청 캐시 사용 가능, 창작은 0.3~0.7 고려

수정 후 서버를 재시작합니다. 스키마나 mock_output이 잘못되면 시작 시 오류가 나므로 실제 토큰을 쓰기 전에 확인할 수 있습니다. 모든 작업은 동일한 `/api/run`과 `/api/vision`에서 사용할 수 있습니다. 이미지가 필요하면 `/api/vision`에 task를 전달하면 됩니다.

예: 교육 주제 → `extract`를 학습 개념 추출로 바꾸고 결과 필드를 `concepts`, `questions`로 변경. 생활 주제 → `image_analyze`를 안내문·분리배출·물품 사진 분석으로 변경. 행정 주제 → 문서 자료를 등록한 뒤 `/api/ask`로 신청 조건 설명. 실제 제도·시간·가격은 주최 측 또는 제공 자료로 채워야 합니다.

## 팀 프론트엔드 연결

`examples/frontend.js`를 복사해 사용하세요. CLOVA API 키는 서버 `.env`에만 저장합니다. 프론트엔드 주소는 `.env`의 `CORS_ORIGINS`에 추가합니다. 다른 기기에서 접근하려면 아래 명령으로 실행하고 `BASE`를 서버 컴퓨터의 LAN IP로 변경하세요.

이미지→설문→텍스트는 다음 함수 순서로 연결합니다. `files`는 `<input type="file" multiple>`의 `files`입니다. `profileId`를 선택한 주제로 바꾸세요. 기준 날짜가 필요하면 `createImageSurvey`의 네 번째 인자로 날짜를 전달합니다.

```js
import {createImageSurvey, saveSurveyAnswers, generateSurveyText} from "./frontend.js";

// 새 사진 묶음마다 새 키를 만들고, 업로드 재전송 시에는 같은 키를 유지하세요.
const requestKey = crypto.randomUUID();
const profileId = "default";
const session = await createImageSurvey(files, profileId, requestKey);
// session.survey.questions를 화면에 표시하고 사용자가 답할 때까지 기다립니다.
// selectedAnswers = [{question_id: "q_1", option_id: "q_1_o_2"}, ...]
const saved = await saveSurveyAnswers(session.session_id, session.survey_revision, selectedAnswers);
const result = await generateSurveyText(session.session_id, saved.answers_revision);
// result.text를 화면에 표시합니다.
```

`NEEDS_IMAGE`일 때는 설문을 표시하지 말고 다른 사진을 요청하세요. 일부 사진만 제외됐으면 `session.analysis.excluded_images`의 이유를 표시하세요. 실패한 분석은 `retryImageSurvey(sessionId, originalFiles)`, 설문 실패는 `retryImageSurvey(sessionId)`로 재시도합니다. 주제에 맞는 화면을 별도로 만들고, 수정본 저장이나 회원별 목록이 필요하면 해당 API와 데이터 모델을 추가하세요.

```sh
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

외부에 공유할 때는 `TEAM_API_KEY`를 설정하고 요청마다 `X-Team-Key`를 보냅니다. 이는 팀 단위 공유 키이며 사용자별 계정·데이터 격리는 없습니다. 모든 팀 요청은 같은 문서 저장소와 토큰 한도를 사용합니다. `.env`, `data/`, `.venv/`는 Git 제외 대상입니다.

## 토큰 관리와 검증 범위

`temperature=0`의 동일 요청은 기본 1시간 캐시합니다. 캐시 응답은 `cached: true`, 이번 호출의 `usage: 0`입니다. `use_cache: false`로 끌 수 있습니다. 모의 실행 캐시는 실제 실행 캐시와 분리되어 있습니다. 공급자가 반환한 입력·출력 토큰은 SQLite에 누적하며 서버 재시작 후에도 남습니다. 가격은 모델별로 달라 원화 비용은 임의 계산하지 않습니다.

`MAX_LIVE_CALLS`는 실패를 포함한 실제 호출 시도 횟수 제한입니다. `TOKEN_STOP_THRESHOLD`는 확인된 누적 토큰이 기준에 도달하면 다음 호출을 막습니다. **실제 결제 한도를 보장하는 장치는 아닙니다.** 마지막 한 번의 응답으로 기준을 초과할 수 있고 타임아웃·오류에서 사용량을 알 수 없으면 `unknown_usage_calls`에 표시합니다. 공급자 콘솔의 실제 사용량도 확인하세요. 자동 재시도는 없습니다.

해커톤 규모의 단일 서버·단일 프로세스를 기준으로 했습니다. `--workers`를 늘리면 프로세스 간 예산 확인과 중복 호출 방지가 보장되지 않습니다. 캐시에는 생성 결과, DB에는 입력한 문서와 토큰 사용량이 저장됩니다. 문서를 지워도 기존 생성 결과 캐시는 TTL까지 남을 수 있습니다.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

테스트는 모의 실행과 공급자 응답 대역으로 수행하므로 실제 API 권한·요금·모델 품질은 별도 실호출 확인 대상입니다. 설치 버전은 `requirements.lock.txt`에 기록합니다. 같은 버전으로 재설치하려면 `pip install -r requirements.lock.txt`를 사용하세요.

## 행사 전에 챙길 것

사전 준비 금지에 대한 사용자 설명을 기준으로, 코드 반입을 전제로 삼지 않습니다. 학습 자체도 허용 범위인지 행사 규정에 맞게 판단하세요. 허용된 연습 범위에서 API 연결 흐름을 익히고, 행사장에서 제공된 모델로 텍스트 1회·이미지 1회 실호출을 확인하면 오류를 일찍 발견할 수 있습니다. 최종 데모는 입력 → 분석 결과 → 사용자가 할 행동의 한 흐름으로 좁히세요.
