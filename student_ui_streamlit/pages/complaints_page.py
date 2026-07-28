import requests
import streamlit as st

from html import escape


# =========================================================
# 기본 설정
# =========================================================

API_BASE_URL = "http://127.0.0.1:8000/api/complaints"

# 로그인 기능 연결 전 임시 사용자 ID
CURRENT_USER_ID = 1

CATEGORIES = [
    "시설/환경",
    "학습 장비",
    "수업/학습",
    "청결",
    "개선 방안",
    "비공개-기타",
]


st.set_page_config(
    page_title="민원 신청",
    page_icon="📝",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# =========================================================
# 모바일 UI CSS
# =========================================================
st.markdown(
    """
    <style>
    .block-container {
        max-width: 430px;
        padding-top: 16px;
        padding-left: 16px;
        padding-right: 16px;
        padding-bottom: 90px;
    }

    .stApp {
        background-color: #F7F9FC;
    }

    [data-testid="stSidebar"] {
        display: none;
    }

    [data-testid="collapsedControl"] {
        display: none;
    }

    #MainMenu {
        visibility: hidden;
    }

    header {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    /* 일반 버튼 */
    div[data-testid="stButton"] > button {
        width: 100%;
        min-height: 44px;
        border-radius: 12px;
        background-color: white;
        border: 1px solid #E4E9EF;
        color: #3B4A5A;
        font-size: 14px;
        font-weight: 600;
        box-shadow: none;
    }

    div[data-testid="stButton"] > button:hover {
        border-color: #3291D9;
        color: #2E8CD9;
    }

    div[data-testid="stButton"] > button:disabled {
        background-color: #F1F4F8;
        border-color: #E4E9EF;
        color: #8A9099;
    }

    /* 민원 제출 버튼 */
    div[data-testid="stFormSubmitButton"] > button {
        width: 100%;
        min-height: 44px;
        border-radius: 12px;
        background-color: #3291D9;
        border: none;
        color: white;
        font-size: 14px;
        font-weight: 700;
    }

    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #287FC0;
        color: white;
    }

    /* 상단 헤더 */
    .complaint-header {
        background: linear-gradient(
            135deg,
            #58A9E6 0%,
            #3291D9 100%
        );
        border-radius: 22px;
        padding: 24px 20px;
        margin-top: 12px;
        margin-bottom: 22px;
        color: white;
    }

    .complaint-header-title {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 7px;
    }

    .complaint-header-subtitle {
        font-size: 13px;
        line-height: 1.6;
        color: rgba(255, 255, 255, 0.92);
    }

    /* 섹션 제목 */
    .section-title {
        font-size: 20px;
        font-weight: 700;
        color: #202124;
        margin-top: 24px;
        margin-bottom: 12px;
    }

    /* 이용 안내 */
    .guide-card {
        background-color: #EEF6FD;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 20px;
        color: #4E5968;
        font-size: 13px;
        line-height: 1.7;
    }

    .guide-card strong {
        color: #202124;
    }

    /* 입력 요소 */
    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextArea"] label,
    div[data-testid="stTextInput"] label {
        color: #202124;
        font-size: 14px;
        font-weight: 600;
    }

    div[data-baseweb="select"] > div,
    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea {
        background-color: #F1F4F8;
        border-radius: 12px;
    }

    div[data-testid="stTextArea"] textarea {
        min-height: 160px;
    }

    /* 민원 작성 폼 */
    div[data-testid="stForm"] {
        background-color: white;
        border: 1px solid #EEF1F5;
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
    }

    /* 민원 게시판 카드 */
    .complaint-card {
        background-color: white;
        border: 1px solid #EEF1F5;
        border-radius: 18px;
        padding: 17px;
        margin-top: 14px;
        margin-bottom: 8px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
    }

    .complaint-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }

    .complaint-number {
        font-size: 13px;
        font-weight: 700;
        color: #2E8CD9;
    }

    .complaint-category {
        display: inline-block;
        background-color: #EEF6FD;
        color: #2E8CD9;
        font-size: 11px;
        font-weight: 700;
        border-radius: 999px;
        padding: 5px 9px;
    }

    .complaint-summary {
        color: #202124;
        font-size: 15px;
        font-weight: 600;
        line-height: 1.65;
        margin-bottom: 13px;
        overflow-wrap: anywhere;
        word-break: keep-all;
    }

    .complaint-meta {
        color: #7A808A;
        font-size: 12px;
        line-height: 1.8;
    }

    .status-badge {
        display: inline-block;
        border-radius: 999px;
        padding: 4px 9px;
        font-size: 11px;
        font-weight: 700;
        background-color: #F1F4F8;
        color: #4E5968;
    }

    div[data-testid="stAlert"] {
        border-radius: 14px;
        font-size: 13px;
    }

    hr {
        border: none;
        border-top: 1px solid #E8ECF1;
        margin-top: 26px;
        margin-bottom: 26px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# API 요청 함수
# =========================================================
def request_summary(category: str, raw_content: str) -> str:
    """민원 내용을 FastAPI 요약 API로 보내 AI 요약문 반환"""

    if category == "비공개-기타":
        return "비공개 민원입니다."

    response = requests.post(
        f"{API_BASE_URL}/summarize",
        json={
            "category": category,
            "raw_content": raw_content,
        },
        timeout=10,
    )

    response.raise_for_status()
    result = response.json()

    return result.get(
        "summary",
        "AI 요약을 진행하지 않은 민원입니다.",
    )


def create_complaint(
    user_id: int,
    category: str,
    raw_content: str,
    summary: str,
    photo_url: str | None,
) -> dict:
    """민원을 DB에 등록"""

    response = requests.post(
        API_BASE_URL,
        json={
            "user_id": user_id,
            "category": category,
            "raw_content": raw_content,
            "summary": summary,
            "photo_url": photo_url,
        },
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


def load_complaints(category: str = "전체") -> list:
    """공개 민원 목록 조회"""

    params = {
        "category": category,
        "current_user_id": CURRENT_USER_ID,
    }

    response = requests.get(
        API_BASE_URL,
        params=params,
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


def like_complaint(complaint_id: int) -> dict:
    """민원 공감 요청"""

    response = requests.post(
        f"{API_BASE_URL}/{complaint_id}/like",
        json={
            "user_id": CURRENT_USER_ID,
        },
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


# =========================================================
# 메인 이동 버튼
# =========================================================
if st.button("← 메인으로", key="back_to_main"):
    st.switch_page("student_app.py")


# =========================================================
# 상단 헤더
# =========================================================
st.markdown(
    """
    <div class="complaint-header">
        <div class="complaint-header-title">📝 민원 신청</div>
        <div class="complaint-header-subtitle">
            불편사항과 개선 요청을 작성하고 처리 상태를 확인해 보세요
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 민원 안내
# =========================================================
st.markdown(
    """
    <div class="guide-card">
        <strong>💡 민원 작성 안내</strong><br>
        민원 원문은 운영진만 확인할 수 있으며,<br>
        게시판에는 AI 요약문과 처리 상태만 공개됩니다.<br>
        비공개 민원은 내용 대신 비공개 안내문이 표시됩니다.
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 민원 작성 영역
# =========================================================
st.markdown(
    '<div class="section-title">새 민원 작성</div>',
    unsafe_allow_html=True,
)

with st.form(
    "complaint_form",
    clear_on_submit=True,
):
    category = st.selectbox(
        "카테고리",
        CATEGORIES,
    )

    raw_content = st.text_area(
        "민원 내용",
        placeholder="불편사항이나 개선 요청을 작성해 주세요.",
        max_chars=1000,
        height=180,
    )

    st.caption(f"{len(raw_content)}/1000자")

    photo_url = st.text_input(
        "사진 URL",
        placeholder=(
            "사진 링크가 있다면 입력해 주세요. "
            "선택 사항입니다."
        ),
    )

    submitted = st.form_submit_button(
        "민원 제출",
        use_container_width=True,
    )


# =========================================================
# 민원 제출 처리
# =========================================================
if submitted:
    cleaned_content = raw_content.strip()
    cleaned_photo_url = photo_url.strip() or None

    if not cleaned_content:
        st.warning("민원 내용을 입력해 주세요.")

    elif len(cleaned_content) > 1000:
        st.warning(
            "민원 내용은 최대 1,000자까지 입력할 수 있습니다."
        )

    else:
        try:
            with st.spinner("민원 내용을 처리하고 있습니다."):
                summary = request_summary(
                    category=category,
                    raw_content=cleaned_content,
                )

                result = create_complaint(
                    user_id=CURRENT_USER_ID,
                    category=category,
                    raw_content=cleaned_content,
                    summary=summary,
                    photo_url=cleaned_photo_url,
                )

            st.success(
                result.get(
                    "message",
                    "민원이 정상적으로 접수되었습니다.",
                )
            )

            st.rerun()

        except requests.exceptions.ConnectionError:
            st.error(
                "민원 서버에 연결할 수 없습니다. "
                "FastAPI 서버가 실행 중인지 확인해 주세요."
            )

        except requests.exceptions.Timeout:
            st.error(
                "민원 서버 응답 시간이 초과되었습니다."
            )

        except requests.exceptions.HTTPError as error:
            try:
                detail = error.response.json().get("detail")
            except Exception:
                detail = None

            st.error(
                detail
                or f"민원 등록 중 오류가 발생했습니다: {error}"
            )

        except Exception as error:
            st.error(
                f"예상하지 못한 오류가 발생했습니다: {error}"
            )


st.divider()


# =========================================================
# 민원 게시판
# =========================================================
st.markdown(
    '<div class="section-title">민원 게시판</div>',
    unsafe_allow_html=True,
)

filter_category = st.selectbox(
    "카테고리 필터",
    ["전체"] + CATEGORIES,
    key="complaint_filter",
)


try:
    complaints = load_complaints(filter_category)

    if not complaints:
        st.info("등록된 민원이 없습니다.")

    for complaint in complaints:
        complaint_id = complaint.get("id")
        complaint_category = complaint.get(
            "category",
            "카테고리 없음",
        )
        summary = complaint.get(
            "summary",
            "요약 내용 없음",
        )
        status = complaint.get(
            "status",
            "접수",
        )
        like_count = complaint.get(
            "like_count",
            0,
        )
        created_at = complaint.get(
            "created_at",
            "",
        )
        is_liked = bool(
            complaint.get(
                "is_liked_by_me",
                False,
            )
        )

        # API 문자열을 HTML에 안전하게 출력
        safe_complaint_id = escape(str(complaint_id))
        safe_category = escape(str(complaint_category))
        safe_summary = escape(str(summary))
        safe_status = escape(str(status))
        safe_created_at = escape(str(created_at))

        created_at_html = (
            f"<br>등록일: {safe_created_at}"
            if created_at
            else ""
        )

        # HTML 들여쓰기 문제 방지를 위해 한 줄 문자열로 생성
        complaint_card_html = (
            '<div class="complaint-card">'
            '<div class="complaint-card-header">'
            f'<div class="complaint-number">'
            f'No. {safe_complaint_id}'
            f'</div>'
            f'<div class="complaint-category">'
            f'{safe_category}'
            f'</div>'
            '</div>'
            f'<div class="complaint-summary">'
            f'{safe_summary}'
            f'</div>'
            '<div class="complaint-meta">'
            f'<span class="status-badge">'
            f'{safe_status}'
            f'</span>'
            f'{created_at_html}'
            '</div>'
            '</div>'
        )

        st.markdown(
            complaint_card_html,
            unsafe_allow_html=True,
        )

        button_text = (
            f"공감 완료 · {like_count}"
            if is_liked
            else f"공감하기 · {like_count}"
        )

        if st.button(
            button_text,
            key=f"like_{complaint_id}",
            disabled=is_liked,
            use_container_width=True,
        ):
            try:
                result = like_complaint(complaint_id)

                if result.get("success"):
                    st.success(
                        "민원에 공감했습니다."
                    )

                else:
                    st.info(
                        result.get(
                            "message",
                            "이미 공감한 민원입니다.",
                        )
                    )

                st.rerun()

            except requests.exceptions.ConnectionError:
                st.error(
                    "민원 서버에 연결할 수 없습니다."
                )

            except requests.exceptions.Timeout:
                st.error(
                    "민원 서버 응답 시간이 초과되었습니다."
                )

            except requests.exceptions.HTTPError as error:
                try:
                    detail = (
                        error.response
                        .json()
                        .get("detail")
                    )
                except Exception:
                    detail = None

                st.error(
                    detail
                    or (
                        "공감 처리 중 오류가 발생했습니다: "
                        f"{error}"
                    )
                )

            except Exception as error:
                st.error(
                    "공감 처리 중 오류가 발생했습니다: "
                    f"{error}"
                )


except requests.exceptions.ConnectionError:
    st.error(
        "민원 게시판을 불러올 수 없습니다. "
        "FastAPI 서버가 실행 중인지 확인해 주세요."
    )

except requests.exceptions.Timeout:
    st.error(
        "민원 게시판 서버의 응답 시간이 초과되었습니다."
    )

except requests.exceptions.HTTPError as error:
    try:
        detail = error.response.json().get("detail")
    except Exception:
        detail = None

    st.error(
        detail
        or f"민원 목록 조회 중 오류가 발생했습니다: {error}"
    )

except Exception as error:
    st.error(
        f"민원 목록 조회 중 오류가 발생했습니다: {error}"
    )