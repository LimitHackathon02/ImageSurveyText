// 기존 프론트엔드에 복사해서 사용하세요. CLOVA_API_KEY는 서버 .env에만 둡니다.
const BASE = "http://localhost:8000";
const TEAM_KEY = ""; // 서버 TEAM_API_KEY를 설정했다면 같은 팀 키 입력

async function readResponse(response) {
  const body = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(body.detail ?? body));
  return body;
}

export async function runTask(task, text, context = "") {
  return readResponse(await fetch(`${BASE}/api/run`, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Team-Key": TEAM_KEY},
    body: JSON.stringify({task, text, context}),
  }));
}

export async function analyzeImage(file, question) {
  const form = new FormData();
  form.append("file", file);
  form.append("question", question);
  return readResponse(await fetch(`${BASE}/api/vision`, {
    method: "POST", headers: {"X-Team-Key": TEAM_KEY}, body: form,
  }));
}

export async function addDocument(title, text) {
  return readResponse(await fetch(`${BASE}/api/documents`, {
    method: "POST", headers: {"Content-Type": "application/json", "X-Team-Key": TEAM_KEY},
    body: JSON.stringify({title, text}),
  }));
}

export async function askDocument(question, documentIds = []) {
  return readResponse(await fetch(`${BASE}/api/ask`, {
    method: "POST", headers: {"Content-Type": "application/json", "X-Team-Key": TEAM_KEY},
    body: JSON.stringify({question, document_ids: documentIds}),
  }));
}

// 같은 업로드를 재전송할 때 requestKey도 재사용하면 세션 중복 생성을 막습니다.
export async function createImageSurvey(files, profileId = "default", requestKey = crypto.randomUUID(), entryDate = null) {
  const form = new FormData();
  // File 한 장, File 배열, input.files의 FileList를 모두 받습니다.
  const photos = files instanceof File ? [files] : Array.from(files);
  for (const photo of photos) form.append("images", photo);
  form.append("profile_id", profileId);
  if (entryDate) form.append("entry_date", entryDate);
  return readResponse(await fetch(`${BASE}/api/image-surveys`, {
    method: "POST", headers: {"X-Team-Key": TEAM_KEY, "Idempotency-Key": requestKey}, body: form,
  }));
}

// entryDate는 날짜 선택 input의 YYYY-MM-DD 값입니다.
export async function createDiarySurvey(files, entryDate, requestKey = crypto.randomUUID()) {
  if (!entryDate) throw new Error("일기 날짜를 선택하세요.");
  return createImageSurvey(files, "diary", requestKey, entryDate);
}

// ANALYSIS_FAILED: 처음 올린 사진 전체를 같은 순서로 전달합니다.
// SURVEY_FAILED: files 없이 호출합니다. 성공한 분석은 다시 호출하지 않습니다.
export async function retryImageSurvey(sessionId, files = null) {
  const form = new FormData();
  if (files) {
    const photos = files instanceof File ? [files] : Array.from(files);
    for (const photo of photos) form.append("images", photo);
  }
  return readResponse(await fetch(`${BASE}/api/image-surveys/${sessionId}/retry`, {
    method: "POST", headers: {"X-Team-Key": TEAM_KEY}, body: form,
  }));
}

export async function getImageSurvey(sessionId) {
  return readResponse(await fetch(`${BASE}/api/image-surveys/${sessionId}`, {
    headers: {"X-Team-Key": TEAM_KEY},
  }));
}

// answers: [{question_id: "q_1", option_id: "q_1_o_2"}, ...]
// 부분 저장도 가능하지만 생략한 기존 답변은 제거됩니다.
export async function saveSurveyAnswers(sessionId, surveyRevision, answers) {
  return readResponse(await fetch(`${BASE}/api/image-surveys/${sessionId}/answers`, {
    method: "PUT", headers: {"Content-Type": "application/json", "X-Team-Key": TEAM_KEY},
    body: JSON.stringify({survey_revision: surveyRevision, answers}),
  }));
}

export async function generateSurveyText(sessionId, answersRevision, rewriteOf = null) {
  return readResponse(await fetch(`${BASE}/api/image-surveys/${sessionId}/generate`, {
    method: "POST", headers: {"Content-Type": "application/json", "X-Team-Key": TEAM_KEY},
    body: JSON.stringify({answers_revision: answersRevision, rewrite_of: rewriteOf}),
  }));
}
