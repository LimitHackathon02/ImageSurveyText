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
export async function createImageSurvey(file, profileId = "default", requestKey = crypto.randomUUID()) {
  const form = new FormData();
  form.append("image", file);
  form.append("profile_id", profileId);
  return readResponse(await fetch(`${BASE}/api/image-surveys`, {
    method: "POST", headers: {"X-Team-Key": TEAM_KEY, "Idempotency-Key": requestKey}, body: form,
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
