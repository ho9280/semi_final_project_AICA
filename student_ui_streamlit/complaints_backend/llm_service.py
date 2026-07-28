import os
from pathlib import Path

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# .env 파일 로드
#
# llm_service.py가 프로젝트의 app 폴더 안에 있다고 가정:
# 프로젝트루트/app/llm_service.py
# 프로젝트루트/.env
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


FALLBACK_SUMMARY = "LLM 응답 지연으로 기본 요약문이 생성되었습니다."
PRIVATE_SUMMARY = "비공개 민원입니다."


def summarize_complaint(
    category: str,
    raw_content: str,
    api_key: str | None = None,
) -> str:
    """
    민원 카테고리와 원문을 받아 AI 요약문을 반환한다.

    - 비공개 민원은 LLM을 호출하지 않는다.
    - 이름, 전화번호, 이메일 등 개인정보를 마스킹한다.
    - 100자 이내 한 문장으로 요약한다.
    - API 오류 발생 시 fallback 문구를 반환한다.
    """

    normalized_category = category.strip()

    # DB/UI에서 사용되는 비공개 카테고리 표기 차이까지 대응
    private_categories = {
        "비공개 - 기타",
        "비공개-기타",
        "기타(비공개)",
    }

    if normalized_category in private_categories:
        print(
            "[Complaint LLM] 비공개 카테고리 감지 "
            "→ LLM API 호출 생략"
        )
        return PRIVATE_SUMMARY

    # 함수 인자로 전달된 키가 있으면 우선 사용
    effective_api_key = api_key or os.getenv("OPENAI_API_KEY")

    if OpenAI is None:
        print(
            "[Complaint LLM Error] "
            "openai 패키지가 설치되어 있지 않습니다."
        )
        return FALLBACK_SUMMARY

    if not effective_api_key:
        print(
            "[Complaint LLM Error] "
            "OPENAI_API_KEY를 불러오지 못했습니다."
        )
        print(f"[Complaint LLM] 확인한 .env 경로: {ENV_PATH}")
        return FALLBACK_SUMMARY

    try:
        # 5초는 첫 API 호출에서 짧을 수 있으므로 20초로 조정
        client = OpenAI(
            api_key=effective_api_key,
            timeout=20.0,
            max_retries=1,
        )

        system_prompt = (
            "당신은 교육기관 민원 요약 담당자입니다.\n"
            "다음 지침을 반드시 준수하세요.\n"
            "1. 이름, 전화번호, 이메일 등 개인정보는 "
            "'*' 문자로 마스킹하세요.\n"
            "2. 민원의 핵심 불편사항과 요청사항을 "
            "100자 이내 한 문장으로 요약하세요.\n"
            "3. 친절하고 중립적인 어조를 사용하세요.\n"
            "4. 원문에 없는 내용을 추가하거나 추측하지 마세요.\n"
            "5. 요약문만 출력하세요."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        f"[카테고리]\n{normalized_category}\n\n"
                        f"[민원 원문]\n{raw_content}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=120,
        )

        summary_result = (
            response.choices[0].message.content or ""
        ).strip()

        if not summary_result:
            raise ValueError("LLM이 빈 요약문을 반환했습니다.")

        # 혹시 100자를 초과해도 서버에서 한 번 더 제한
        return summary_result[:100]

    except Exception as error:
        # 사용자 화면에는 fallback 문구만 표시하고,
        # 실제 원인은 FastAPI 터미널에서 확인
        print(
            "[Complaint LLM Error] "
            f"{type(error).__name__}: {error}"
        )
        return FALLBACK_SUMMARY