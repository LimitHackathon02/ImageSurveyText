# 주제 공개 후 수정 가이드

대상: ImageSurveyText · 사용 예정: 2026-10-09 · 현재 구현 기준

내일의 기본 작업은 **주제별 설정을 바꾸고, 실제 사진과 답변으로 결과를 확인하는 것**이다. 이 문서는 바꿀 파일·변수·로직과 확인 순서를 정리한다. 현재 연결 흐름은 모의 실행과 공급자 응답 대역으로 검증했으며, 실제 HyperCLOVA X의 분석·설문·글 품질은 지급 API로 확인해야 한다.

## 1. 시간이 없으면 이 순서대로

1. 최종 결과를 한 문장으로 정한다: **“[사용자]가 [사진]과 [설문 답변]을 제공하면 [어떤 글]을 받아 [어떤 행동]을 할 수 있다.”**
2. `profiles/default.json`을 새 JSON으로 복사하고 주제·대상·글의 목적을 바꾼다.
3. 사진에서 볼 내용, 설문으로 알아낼 내용, 결과 글의 목차를 바꾼다.
4. `.env`에 지급 키·모델·주소를 설정한다. 우선 모의 실행으로 연결을 확인한다.
5. 서버를 재시작하고 **새 profile_id·새 세션**으로 실행한다.
6. 실제 모드에서 같은 사진에 서로 다른 답변을 골라 결과가 달라지는지 확인한다.

가장 먼저 읽고 수정할 파일은 `profiles/default.json`이다. 이미지→설문→답변→글의 호출 순서를 바꾸려면 `app/survey.py`를 읽는다.

## 2. 주제 공개 직후 팀과 정할 내용

다음 다섯 항목을 먼저 채운다. 이것이 프롬프트와 설정에 들어갈 내용이다.

| 항목 | 적을 내용 | 예: 교육 주제 |
|---|---|---|
| 사용자 | 누가 어떤 상황에서 쓰는가 | 노트 내용을 이해하고 싶은 학생 |
| 이미지 | 어떤 사진을 넣는가 | 교재 또는 필기 사진 |
| 이미지 분석 | 사진에서 무엇을 확인하는가 | 읽을 수 있는 개념·본문, 읽기 어려운 부분 |
| 설문 | 사진만으로 알 수 없는 무엇을 묻는가 | 학습 목표, 현재 이해 정도, 공부 시간 |
| 결과 | 어떤 글을 받아 무엇을 하는가 | 자신의 조건에 맞는 설명과 공부 순서로 학습 |

설문은 사진에서 보이는 것을 계속 되묻기보다 **사용자의 목적·선호·제약을 보충**해야 한다. 사진 분석과 설문 답변이 각각 최종 글의 어디에 반영되는지 설명할 수 있으면 기획이 명확해진다.

## 3. 반드시 바꿀 설정

아래의 경로는 profile JSON 안의 항목이다. 기본 파일을 직접 수정해도 되지만, 새 주제 파일을 만들어 기본 예시를 남기는 편이 비교하기 쉽다.

| 항목 | 바꾸는 이유 | 현재 기본값·수정 요령 |
|---|---|---|
| `id` | API에서 주제를 선택하는 이름 | `default` → `event_edu` 등 고유한 이름 |
| `version` | 설정 변경을 구분 | 시작은 1, 기존 내용을 바꾸면 증가 |
| `domain` | 적용 분야 | `생활 공간` → 공개 주제 |
| `audience` | 글을 읽을 사용자 | 대상과 상황을 구체적으로 작성 |
| `objective` | 최종 글의 목적 | 어떤 정보를 주고 어떤 행동을 돕는지 작성 |
| `image.focus` | 이미지에서 중점적으로 볼 내용 | 사진 종류에 맞는 관찰 항목 작성 |
| `survey.slots` | 설문으로 채울 정보 항목 | `goal` 등을 주제에 맞는 이름으로 교체 |
| `survey.question_count` | 질문 수 | slots 개수 이상이어야 함 |
| `output.sections` | 결과 글의 목차 | 섹션 ID·제목·배열 순서 변경 |
| `output.tone` | 독자에 맞는 말투 | 쉬운 설명, 학생 대상 설명 등 지정 |

`slots`는 모델이 알아야 할 정보의 종류다. 영어 이름뿐 아니라 `"학습 목표"`, `"현재 이해 정도"`처럼 한국어 이름도 사용할 수 있다. 중복 없이 의미가 분명한 이름을 쓴다. 실제 질문과 선택지의 문구는 CLOVA가 생성하며, `q_1`, `q_1_o_1` 등의 응답 ID는 서버가 부여한다.

## 4. 필요에 따라 조정할 숫자

| 변수 | 현재 기본값 | 현재 코드의 허용 범위·효과 |
|---|---|---|
| `survey.question_count` | 5 | 1~12, 필수 slots 개수 이상 |
| `survey.min_options` / `max_options` | 3 / 5 | 각각 2~8, min ≤ max |
| `survey.question_max_chars` | 100 | 30~200, 질문 문구 길이 제한 |
| `survey.option_max_chars` | 50 | 15~100, 선택지 문구 길이 제한 |
| `survey.include_unknown_option` | true | 각 질문에 모름·미정·해당 없음 선택지 요구 |
| `output.target_chars` | 1500 | 300~6000, 최종 글자 수 목표 |
| `output.length_tolerance_ratio` | 0.2 | 0 이상 1 미만, 0.2는 ±20% |
| 각 단계 `max_tokens` | 이미지 1024 / 설문 2048 / 글 3072 | 현재 코드에서 1~4096 |
| 각 단계 `temperature` | 이미지·설문 0 / 글 0.3 | 0~1, 높을수록 결과의 다양성이 커짐 |
| `image.max_upload_mb` | 10 | 1~20, 업로드 허용 용량 |
| `image.resize_long_edge` | 1280 | 32~2240, 전송 이미지의 긴 변 최대 길이 |

자주 할 수정은 다음과 같다.

- **질문을 3개로 줄이기:** `question_count=3`으로 바꾸고 slots도 3개 이하로 줄인다.
- **선택지를 항상 4개로 만들기:** `min_options=4`, `max_options=4`로 설정한다. 모름 선택지도 이 4개에 포함된다.
- **글을 약 2,500자로 늘리기:** `target_chars=2500`으로 바꾸고 실제 결과를 확인한다. 필요하면 글 생성 `max_tokens`도 조정한다.
- **사진 속 작은 글자 읽기:** `resize_long_edge`를 올려 확인한다. 전용 OCR처럼 정확한 인식을 보장하지는 않는다.
- **목차 바꾸기:** `sections`의 ID·제목·순서를 수정한다. 서버가 같은 순서로 조립하고 모델 결과의 ID도 검사한다.

`target_chars`와 `max_tokens`는 단위가 다르다. 길이를 늘리기 위해 max_tokens만 바꾸면 글의 목표 분량은 바뀌지 않는다. 분량은 제목·섹션 제목·본문·공백·줄바꿈을 모두 합친 `len(text)`로 계산한다. 1,500자 ±20%라면 1,200~1,800자가 완료 범위다.

## 5. 복사해서 수정할 완성 예시

교육 주제가 나왔다고 가정한 예시다. 실제 공개 주제에 맞춰 문구를 바꾼다. **아래 내용을 `profiles/event_edu.json`으로 직접 저장해야** `event_edu`를 선택할 수 있다.

```json
{
  "id": "event_edu",
  "version": 1,
  "domain": "교육",
  "audience": "필기나 교재의 내용을 이해하고 싶은 학생",
  "objective": "사진에서 확인한 학습 내용과 사용자 답변에 맞는 설명 및 공부 순서 작성",
  "image": {
    "focus": "실제로 읽을 수 있는 개념과 본문을 정리하고, 흐리거나 잘려 읽을 수 없는 부분을 표시한다.",
    "max_upload_mb": 10,
    "resize_long_edge": 1600,
    "max_tokens": 1536,
    "temperature": 0
  },
  "survey": {
    "question_count": 3,
    "min_options": 4,
    "max_options": 4,
    "question_max_chars": 100,
    "option_max_chars": 50,
    "slots": ["학습 목표", "현재 이해 정도", "공부 시간"],
    "include_unknown_option": true,
    "max_tokens": 1536,
    "temperature": 0
  },
  "output": {
    "format": "markdown",
    "tone": "학생이 이해하기 쉬운 친절하고 구체적인 한국어",
    "target_chars": 1500,
    "length_tolerance_ratio": 0.2,
    "sections": [
      {"id": "concepts", "title": "사진에서 확인한 학습 내용"},
      {"id": "explanation", "title": "내 이해 정도에 맞춘 설명"},
      {"id": "study_plan", "title": "주어진 시간에 할 공부"}
    ],
    "generation_mode": "single",
    "max_tokens": 3072,
    "temperature": 0.3
  }
}
```

JSON은 문자열에 큰따옴표를 쓰고 마지막 항목 뒤에는 쉼표를 넣지 않는다. 주석도 넣을 수 없다. profile의 `id`는 영문 소문자로 시작하고 영문 소문자·숫자·`_`·`-`만 사용한다. 섹션 ID는 영문 소문자로 시작하고 영문 소문자·숫자·`_`만 사용한다.

## 6. 프롬프트 수정은 언제 하는가

기본 지시문은 `survey_prompts.json`에 있다. 우선 profile을 바꾸고, 주제에 필요한 규칙이 더 있으면 다음 항목을 수정한다.

| 프롬프트 키 | 추가할 내용의 예 |
|---|---|
| `image_analysis` | 노트에서 실제 읽힌 개념만 관찰로 기록하고 읽히지 않은 내용을 보충하지 않기 |
| `survey_generation` | 학생의 이해 수준을 쉬운 선택지로 묻고 시험 점수를 임의로 요구하지 않기 |
| `text_generation` | 선택한 공부 시간에 맞는 순서를 쓰고 확인된 개념으로 설명 범위를 제한하기 |

각 지시문 뒤에 profile 전체가 자동으로 붙는다. 파일명이나 파일 위치만 적어서는 그 파일 내용을 AI가 읽지 않는다. 필요한 지시는 해당 문자열이나 profile 값에 직접 적는다.

**이 프롬프트 파일은 모든 profile에서 공유한다.** 여러 주제를 동시에 유지하려면 특정 주제의 지시는 가능한 한 해당 profile의 `focus`, `objective`, `tone`에 둔다. profile마다 완전히 다른 프롬프트 파일을 선택하는 기능은 현재 구현되어 있지 않다.

관찰·해석·불확실성 구분, 질문 수·선택지·slots 준수, 섹션 ID·순서 준수, JSON 출력 요구는 유지한다. 이를 지우면 모델의 결과와 서버 검사가 맞지 않을 수 있다.

## 7. 지급 API와 팀 연결 설정

실행 설정은 **`.env`**를 수정한다. `.env.example`만 바꾸면 이미 만들어진 `.env`에는 적용되지 않는다. `.env`의 키는 Git에 올리지 않는다.

터미널에 같은 이름의 환경변수를 이미 설정했다면 그 값이 `.env`보다 우선한다. 재시작했는데 모드나 설정이 그대로라면 실행 터미널의 환경변수도 확인한다.

| 환경변수 | 내일 확인할 내용 |
|---|---|
| `MOCK_MODE` | 연결 연습은 true, 실제 분석·생성은 false |
| `CLOVA_API_KEY` | 지급 API 키 |
| `CLOVA_BASE_URL` | 주최 측 안내의 API 기본 주소 |
| `CLOVA_VISION_MODEL` / `CLOVA_TEXT_MODEL` | 사용할 이미지·텍스트 모델과 권한 |
| `CLOVA_TIMEOUT_SECONDS` | 생성 응답을 기다리는 시간, 현재 60초 |
| `CORS_ORIGINS` | 팀 프론트엔드의 실제 주소, 쉼표로 구분 |
| `TEAM_API_KEY` | 사용하면 프론트엔드도 X-Team-Key 헤더 전송 |
| `MAX_LIVE_CALLS` / `TOKEN_STOP_THRESHOLD` | 지급량에 맞춘 호출 중단 기준 |

모델명·주소를 변경해도 인증 헤더나 응답 형식까지 자동 변환되지는 않는다. 대회 전용 프록시 등 일반 v3 REST 형식과 다르면 `app/provider.py`와 `app/engine.py`의 요청 파라미터도 확인한다. 누적 토큰 중단 기준은 실제 과금 상한을 보장하지 않으며 사용량 미확인 호출도 `/api/usage`에서 확인한다.

프론트엔드 담당자는 `examples/frontend.js`의 `BASE`, `TEAM_KEY`와 `createImageSurvey`에 전달하는 `profileId`를 맞춘다. `CORS_ORIGINS`는 브라우저 접근 허용 주소이며 서버를 다른 기기에서 접근 가능하게 여는 설정은 별도다.

## 8. 수정 후 실행·확인 순서

### A. 설정 문법과 코드 검사

실행 중인 서버를 종료하고 새 JSON을 저장한 뒤 실행한다. 첫 명령은 profile과 공통 프롬프트를 읽어 검사하며 외부 AI를 호출하지 않는다. 잘못된 profile 하나가 있으면 서버 시작도 실패하므로 임시로 만든 파일도 유효해야 한다.

```sh
.venv/bin/python -c 'from app.survey_tasks import load_profiles, TaskFactory; print(list(load_profiles("profiles"))); TaskFactory("survey_prompts.json")'
.venv/bin/python -m pytest -q
```

### B. 서버 재시작

실행 중인 서버를 종료한 뒤 시작한다. `profiles`, 프롬프트, `.env`는 시작 시 읽으므로 저장만 해서는 실행 중인 서버에 반영되지 않는다. 서버는 한 프로세스로 실행한다.

```sh
sh scripts/start.sh
```

### C. 모의 실행으로 연결 확인

`.env`가 `MOCK_MODE=true`인 상태에서 새 터미널로 실행한다. `event_edu`는 앞의 예시를 저장했을 때 사용하는 ID이며 다른 이름을 정했다면 명령도 바꾼다.

```sh
.venv/bin/python scripts/survey_demo.py --profile event_edu --interactive
```

### D. 실제 사진으로 품질 확인

`.env`에 지급 API를 설정하고 `MOCK_MODE=false`로 바꾼 뒤 서버를 재시작한다. 새 세션에서 실제 사진을 사용한다.

```sh
.venv/bin/python scripts/survey_demo.py --image ./photo.jpg --profile event_edu --interactive
```

모의 글은 목표 분량에 맞춰 예시 문장을 조립하므로 실제 글 품질을 확인하는 용도로 사용하지 않는다. 실제 모드의 정상 흐름은 기본 3회 호출이다. 분석·설문 캐시나 이미 생성한 결과 재사용으로 실제 추가 호출 수는 줄어들 수 있다.

**설정을 바꾼 뒤에는 새 세션을 만든다.** 기존 세션은 설정·프롬프트 스냅샷을 저장하고, 같은 답변 버전의 생성 요청은 기존 결과를 반환한다. 변경된 설정을 검사하려고 기존 세션에서 `/retry`만 누르면 의도와 다른 결과를 볼 수 있다. 새 업로드에는 새 Idempotency-Key를 사용한다.

위 명령은 macOS/Linux/WSL 기준이다. Windows 기본 Python에서는 `.venv/bin/python` 대신 `.venv\Scripts\python`을 쓰고, 서버 실행은 README의 PowerShell 명령을 따른다.

## 9. 코드까지 수정해야 하는 변경

아래는 profile만 바꿔서 지원되는 기능이 아니다. 시간과 필요성을 따져 선택한다.

| 변경 요청 | 읽고 바꿀 위치 | 함께 확인할 부분 |
|---|---|---|
| 복수 선택 또는 자유 입력 | `survey_models.py`, `survey_tasks.py`, `survey.py` | 설문 형식, 답변 검증, 선택 문구 복원, 프론트엔드 |
| 이전 답변에 따른 질문 분기 | `survey.py`, `survey_tasks.py`, `survey_store.py` | 질문 생성 시점, 설문 버전, 기존 답변 무효화 |
| 필수·선택 질문 혼합 | `decorate_survey`, `save_answers`, `generate`, `resolve_answers` | 현재는 모든 질문 필수이며 질문 수로 완료 판단 |
| 이미지 분석 JSON에 필드 추가 | `Analysis`, `validate_analysis`, `mock_analysis`, 이미지 프롬프트 | 추가 필드의 형식·근거·후속 단계 사용 |
| 사용자가 분석 내용을 수정 | `main.py`, `survey.py`, `survey_store.py` | 수정 API, 설문 재생성, 기존 답변·글 무효화 |
| 6,000자 초과 목표·장문 분할 | `OutputConfig`, `survey.py`, `survey_tasks.py` | 토큰 상한, 섹션별 생성, 중복 내용, 실패 구간 복구 |
| HTML 등 다른 결과 형식 | `OutputConfig`, `assemble_text`, `generate` | 글 조립 방식, 글자 수 계산, 프론트엔드 표시 |
| 모델이나 API 프로토콜 변경 | `settings.py`, `provider.py`, `engine.py` | 헤더·주소·요청 필드·응답 파싱·모델 한도 |

현재 `generation_mode`는 `single`, `format`은 `markdown`만 허용한다. 숫자 제한이나 Literal 값을 풀기만 해서는 새 기능이 구현되지 않는다. **입력 형식 → 검사 → AI에 보낼 자료 → 결과 형식**까지 함께 고친다.

`app/survey.py`의 `MAX_INPUT_CHARS=24000`은 합친 입력 문자열 길이 제한이다. 질문 수나 분석 정보를 크게 늘려 한도에 걸리면 자료를 먼저 줄인다. 이 숫자는 토큰 계산 결과가 아니므로 숫자만 키워 모델 입력 한도를 해결할 수는 없다.

## 10. 오류가 나오면 확인할 곳

| 현상 | 먼저 확인할 것 | 처리 |
|---|---|---|
| 서버가 시작되지 않음 | profile JSON, 중복 id, 질문 수·slots, 지원하지 않는 설정 값 | 터미널의 설정 오류 수정 |
| 설정을 바꿨는데 결과가 같음 | 서버 재시작, profile_id, 이전 세션, 모의 실행 여부 | 새 세션·새 업로드 키로 확인 |
| 파일은 있는데 profile을 못 찾음 | 파일이 PROFILES_PATH 바로 아래의 `.json`인지, 내부 id가 맞는지 | `/api/survey-profiles` 조회 |
| 이미지 업로드 413/422 | 용량, 형식, 최소 크기 | 지원 사진으로 다시 업로드 |
| `NEEDS_IMAGE` | analysis의 issue | 다른 사진으로 새 세션 생성 |
| 분석 결과 형식 502 | 관찰 ID·해석 근거·usable·불가 사유, 출력 잘림 | 이미지 프롬프트·토큰 한도 확인 |
| 설문 결과 형식 502 | 질문 수·선택지·slots·모름 선택지·문구 길이 | 설정과 프롬프트를 함께 확인 |
| 답변 저장·생성 422 | 필수 질문 누락, 다른 질문의 선택지 ID | 저장된 설문 기준으로 전체 답변 전송 |
| 409 | 생성 진행 중, 답변/설문 버전 불일치, 모의·실제 모드 혼용 | 현재 세션 조회, 필요하면 새 세션 |
| `NEEDS_REVIEW` | length.actual_chars와 target_chars | 목표·토큰 조정 후 새 세션 또는 원본 결과 1회 재작성 |
| `GENERATION_FAILED` | 섹션 ID·순서, JSON 형식, 토큰 잘림 | 원인을 수정해 새 세션으로 검사 |
| CLOVA HTTP 401/403 | API 키·모델 권한 | 지급 정보 확인, 키는 서버 .env에만 입력 |
| CLOVA HTTP 429 또는 자체 한도 429 | 공급자 호출 제한, `/api/usage` | 공급자 제한 또는 서버 호출 한도 확인 |
| 504 | 공급자 지연·네트워크·타임아웃 | 무조건 반복 호출하지 말고 실패 상태와 사용량 확인 |
| 브라우저만 호출 실패 | BASE, CORS_ORIGINS, X-Team-Key, 서버 접근 주소 | 프론트엔드와 서버 설정 맞추기 |

기존 설정 그대로 일시적인 실패만 복구할 때는 `ANALYSIS_FAILED`에 원래 이미지를 넣어 `/retry`, `SURVEY_FAILED`에는 파일 없이 `/retry`를 호출한다. `GENERATION_FAILED`는 같은 답변 버전으로 `/generate`를 명시적으로 다시 호출한다.

## 11. 시연 전 완료 확인

- [ ] 실제 대상 사용자·사진·설문 목적·최종 글의 용도를 한 문장으로 설명할 수 있다.
- [ ] 선택한 profile의 질문 수와 선택지 수가 화면에 반영된다.
- [ ] 같은 사진에 다른 답변을 선택하면 글 내용이 그 답변을 반영해 달라진다.
- [ ] 사진 속 관찰과 추측을 구분하고, 읽히지 않은 정보를 사실처럼 보충하지 않는다.
- [ ] 필수 답변을 모두 저장한 뒤 글을 생성한다.
- [ ] 완료·분량 검토 필요·생성 실패 상태를 화면에서 구분한다.
- [ ] 프론트엔드의 주소·profileId·팀 키와 백엔드 설정이 맞는다.
- [ ] 시연이 실제 모드인지 모의 예시인지 명확하게 표시한다.

기본 주제 적응은 profile의 **대상·목적·이미지 초점·slots·목차** 변경으로 시작한다. 그다음 실제 입력에서 발견된 문제를 기준으로 프롬프트와 수치를 조정한다.
