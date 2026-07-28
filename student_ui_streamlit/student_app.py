import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.menu_agent_tool import get_current_menu


st.set_page_config(
    page_title="인사교 학생 앱",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# -----------------------------
# 기본 CSS
# -----------------------------
st.markdown(
    """
    <style>
    .block-container {
        max-width: 430px;
        padding-top: 0;
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

    #MainMenu {
        visibility: hidden;
    }

    footer {
        visibility: hidden;
    }

    header {
        visibility: hidden;
    }

    .header-box {
        background: linear-gradient(
            135deg,
            #58A9E6 0%,
            #3291D9 100%
        );
        border-radius: 0 0 24px 24px;
        padding: 34px 22px 30px 22px;
        margin-left: -16px;
        margin-right: -16px;
        margin-bottom: 24px;
        color: white;
    }

    .header-title {
        font-size: 25px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .header-subtitle {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.92);
    }

    .section-title {
        font-size: 19px;
        font-weight: 700;
        color: #202124;
        margin-top: 8px;
        margin-bottom: 12px;
    }

    .meal-card {
        background-color: white;
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 24px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.07);
        border: 1px solid #EEF1F5;
    }

    .meal-type {
        font-size: 14px;
        font-weight: 700;
        color: #2E8CD9;
        margin-bottom: 8px;
    }

    .meal-menu {
        font-size: 17px;
        font-weight: 700;
        color: #202124;
        margin-bottom: 8px;
    }

    .meal-caption {
        font-size: 12px;
        color: #747981;
    }

    div[data-testid="stButton"] > button {
        width: 100%;
        height: 116px;
        border-radius: 18px;
        background-color: white;
        border: 1px solid #EDF0F4;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.07);
        color: #202124;
        font-size: 15px;
        font-weight: 700;
        white-space: pre-line;
        transition: 0.2s;
    }

    div[data-testid="stButton"] > button:hover {
        border-color: #3291D9;
        color: #2E8CD9;
        transform: translateY(-2px);
    }

    div[data-testid="stButton"] > button:focus {
        box-shadow: 0 0 0 2px rgba(50, 145, 217, 0.18);
    }

    /* 주요 기능 버튼 전체 텍스트: 설명은 회색 */
    div[data-testid="stButton"] > button p {
        color: #7A808A;
        font-size: 13px;
        font-weight: 400;
        line-height: 1.7;
    }

    /* 주요 기능 버튼 제목: 굵고 조금 크게 */
    div[data-testid="stButton"] > button p strong {
        color: #202124;
        font-size: 16px;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 상단 환영 영역
# -----------------------------
st.markdown(
    """
    <div class="header-box">
        <div class="header-title">안녕하세요, 사용자님 👋</div>
        <div class="header-subtitle">
            오늘도 인공지능사관학교에서 좋은 하루 보내세요
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 식단
# -----------------------------
# 한국 시간 기준으로 19시 이후에는 '내일의 식단' 표시
current_hour = datetime.now(ZoneInfo("Asia/Seoul")).hour
meal_section_title = "내일의 식단" if current_hour >= 19 else "오늘의 식단"

st.markdown(
    f'<div class="section-title">{meal_section_title}</div>',
    unsafe_allow_html=True,
)

# 실제 식단 Agent에서 현재 시간대 식단 조회
menu_result = get_current_menu()
menu_list = menu_result.get("results", [])

# 현재 보고 있는 식단 카드 번호 저장
if "meal_slide_index" not in st.session_state:
    st.session_state.meal_slide_index = 0

# 식단 데이터가 있는 경우
if menu_result.get("success") and menu_list:
    # 데이터 개수가 바뀌어 인덱스가 범위를 벗어나는 경우 초기화
    if st.session_state.meal_slide_index >= len(menu_list):
        st.session_state.meal_slide_index = 0

    current_menu = menu_list[st.session_state.meal_slide_index]

    organization = current_menu.get("organization", "식당")
    meal_type = current_menu.get("meal_type", "식단")
    menu_items = current_menu.get("menu_items", [])

    # 메뉴 리스트를 가운데점으로 연결
    menu_text = (
        " · ".join(menu_items)
        if menu_items
        else "등록된 메뉴가 없습니다."
    )

    st.markdown(
        f"""
        <div class="meal-card">
            <div class="meal-type">{organization} {meal_type}</div>
            <div class="meal-menu">
                {menu_text}
            </div>
            <div class="meal-caption">
                {st.session_state.meal_slide_index + 1} / {len(menu_list)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 식단이 2개 이상일 때만 이전·다음 버튼 표시
    if len(menu_list) > 1:
        previous_col, next_col = st.columns(2)

        with previous_col:
            if st.button(
                "◀ 이전 식단",
                key="previous_meal",
                use_container_width=True,
            ):
                st.session_state.meal_slide_index = (
                    st.session_state.meal_slide_index - 1
                ) % len(menu_list)
                st.rerun()

        with next_col:
            if st.button(
                "다음 식단 ▶",
                key="next_meal",
                use_container_width=True,
            ):
                st.session_state.meal_slide_index = (
                    st.session_state.meal_slide_index + 1
                ) % len(menu_list)
                st.rerun()

# 식단 데이터가 없는 경우
else:
    error_message = menu_result.get(
        "answer",
        "현재 표시할 수 있는 식단 정보가 없습니다.",
    )

    st.markdown(
        f"""
        <div class="meal-card">
            <div class="meal-type">식단 안내</div>
            <div class="meal-menu">
                {error_message}
            </div>
            <div class="meal-caption">
                식단 데이터가 등록되면 자동으로 표시됩니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# 주요 기능
# -----------------------------
st.markdown(
    '<div class="section-title">주요 기능</div>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2, gap="small")

with col1:
    if st.button(
        "📅\n**출결 계산**\n출석률과 지원 기준 확인",
        key="attendance_button",
        use_container_width=True,
    ):
        st.switch_page("pages/attendance_page.py")

with col2:
    if st.button(
        "💬\n**AI 챗봇**\n학습·생활 관련 질문",
        key="chatbot_button",
        use_container_width=True,
    ):
        st.switch_page("pages/chatbot_page.py")

col3, col4 = st.columns(2, gap="small")

with col3:
    if st.button(
        "📢\n**공지사항**\n공지 제목 검색 및 조회",
        key="notice_button",
        use_container_width=True,
    ):
        st.switch_page("pages/notices_page.py")

with col4:
    if st.button(
        "📝\n**민원 신청**\n민원 작성과 상태 확인",
        key="complaint_button",
        use_container_width=True,
    ):
        st.switch_page("pages/complaints_page.py")