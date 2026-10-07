"""실행 중인 서버에 이미지→설문→답변→글 요청을 순서대로 보내는 예제."""
import argparse
import io
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from PIL import Image


def read_response(response):
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"서버가 JSON 대신 HTTP {response.status_code}를 반환했습니다.") from None
    if not response.is_success:
        raise RuntimeError(json.dumps(data.get("detail", data), ensure_ascii=False))
    return data


def main():
    parser = argparse.ArgumentParser(description="이미지 설문 API 전체 흐름 실습")
    parser.add_argument("--image", action="append", help="사진 경로. 여러 장이면 --image를 반복. 모의 실행에서는 생략 가능")
    parser.add_argument("--profile", default="diary", help="profiles JSON에 정의한 ID, 기본 diary")
    parser.add_argument("--date", help="일기 날짜 YYYY-MM-DD. 생략하면 서버의 한국 날짜 사용")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--interactive", action="store_true", help="질문마다 번호로 답변 선택")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    with httpx.Client(base_url=args.url.rstrip("/"), timeout=600,
                      headers={"X-Team-Key": os.getenv("TEAM_API_KEY", "")}) as client:
        health = read_response(client.get("/health"))
        if args.image:
            files = [("images", (Path(path).name, Path(path).read_bytes())) for path in args.image]
        else:
            if not health["mock"]:
                raise RuntimeError("실제 AI 모드에서는 --image로 분석할 사진을 지정하세요.")
            buffer = io.BytesIO()
            Image.new("RGB", (100, 100), "white").save(buffer, "PNG")
            files = [("images", ("mock.png", buffer.getvalue()))]
        data = {"profile_id": args.profile}
        if args.date:
            data["entry_date"] = args.date
        print(f"1. 사진 {len(files)}장 분석과 전체 설문 생성", flush=True)
        session = read_response(client.post("/api/image-surveys", files=files, data=data))
        print(f"session_id: {session['session_id']} / 상태: {session['status']}")
        print(f"기록 날짜: {session['entry_date']} / 사진: {session['image_count']}장")
        print(json.dumps(session["analysis"], ensure_ascii=False, indent=2))
        if session["status"] != "SURVEY_READY":
            raise RuntimeError("설문이 준비되지 않았습니다. 분석 사유와 세션 상태를 확인하세요.")
        selections = []
        for question in session["survey"]["questions"]:
            print(f"\n{question['question']}")
            for number, option in enumerate(question["options"], 1):
                print(f"  {number}. {option['label']}")
            index = 0
            if args.interactive:
                while True:
                    try:
                        index = int(input("선택 번호: ")) - 1
                        if 0 <= index < len(question["options"]):
                            break
                    except ValueError:
                        pass
                    print("표시된 선택지 번호를 입력하세요.")
            selections.append({"question_id": question["id"], "option_id": question["options"][index]["id"]})
        print("\n2. 답변 저장 (자동 모드는 각 질문의 첫 선택지)", flush=True)
        session = read_response(client.put(f"/api/image-surveys/{session['session_id']}/answers",
                                            json={"survey_revision": session["survey_revision"], "answers": selections}))
        print("3. 답변을 바탕으로 글 생성", flush=True)
        result = read_response(client.post(f"/api/image-surveys/{session['session_id']}/generate",
                                          json={"answers_revision": session["answers_revision"]}))
        print(result["text"])
        print(json.dumps({key: result[key] for key in ("mock", "status", "length", "generation_id", "usage")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, httpx.RequestError, OSError) as error:
        print(f"실행 실패: {error}", file=sys.stderr)
        sys.exit(1)
