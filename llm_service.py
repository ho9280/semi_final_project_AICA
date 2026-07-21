# %%
import os
import time

# OpenAI / LangChain 등 LLM 라이브러리 불러오기 시도 (미설치되어 있어도 에러 안 나도록 예외 처리)
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def summarize_complaint(
    category: str, raw_content: str, api_key: str = None
) -> str:
    """민원 카테고리와 원문을 받아 LLM 요약문(또는 비공개/Fallback 텍스트)을 반환하는 함수

    Args:
        category (str): 민원 카테고리 (예: '시설/환경', '기타(비공개)' 등)
        raw_content (str): 작성 원문 (최대 1,000자)
        api_key (str, optional): OpenAI API Key. 미전달 시 환경변수(OPENAI_API_KEY) 참조

    Returns:
        str: AI 요약 결과문
    """

    # 1. [최우선 예외 조건] 비공개 카테고리인 경우: API 호출 없이 0초 만에 멘트 고정 반환 (비용 0원)
    private_categories = ["기타", "기타(비공개)", "기타 (비공개 필수)"]
    if category in private_categories:
        print("[Log] '기타(비공개)' 카테고리 감지 -> LLM API 호출을 Skip합니다.")
        return "비공개 민원입니다."

    # 2. API Key 확인 (인자로 들어온 키 > 환경변수 키)
    effective_api_key = api_key or os.getenv("OPENAI_API_KEY")

    # 3. [2중 방어 1차] API Key가 미설정된 상태일 때
    if not effective_api_key or OpenAI is None:
        print(
            "[Warning] API Key가 설정되지 않았거나 openai 패키지가 없습니다. Fallback 텍스트를 반환합니다."
        )
        return "LLM 응답 지연으로 기본 요약문이 생성되었습니다."

    # 4. [정상 통신 및 2중 방어 2차] LLM API 호출 및 예외(try-except) 처리
    try:
        client = OpenAI(api_key=effective_api_key)

        prompt_system = (
            "당신은 학원/교육기관 민원 요약 전문가입니다. 아래 지침을 엄격히 준수하세요.\n"
            "1. 원문 내용에서 개인정보(이름, 전화번호, 이메일 등)가 있다면 반드시 '*' 문자로 마스킹 처리하세요.\n"
            "2. 민원의 핵심 핵심 불만 및 요청 사항을 100자 이내의 명확한 한 문장으로 요약하세요.\n"
            "3. 친절하고 중립적인 어조를 유지하세요."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 비용 효율성이 뛰어난 모델 사용
            messages=[
                {"role": "system", "content": prompt_system},
                {
                    "role": "user",
                    "content": f"[카테고리: {category}]\n[원문]: {raw_content}",
                },
            ],
            temperature=0.2,
            max_tokens=200,
            timeout=5.0,  # 5초 타임아웃 설정으로 무한 대기 방지
        )

        summary_result = response.choices[0].message.content.strip()
        return summary_result

    except Exception as e:
        # API 오류, 타임아웃, 네트워크 단절 등 발생 시 에러 로그 출력 후 Fallback 텍스트 반환
        print(f"[Error Log] LLM API 호출 중 예외 발생: {e}")
        return "LLM 응답 지연으로 기본 요약문이 생성되었습니다."