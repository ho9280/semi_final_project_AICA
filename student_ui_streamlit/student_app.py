import streamlit as st


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

    .notice-box {
        margin-top: 22px;
        background-color: #EEF6FD;
        border-radius: 14px;
        padding: 14px 16px;
        color: #4E5968;
        font-size: 13px;
        line-height: 1.6;
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
        <div class="header-title">안녕하세요, OOO님</div>
        <div class="header-subtitle">
            오늘도 인공지능사관학교에서 좋은 하루 보내세요
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------
# 오늘의 식단
# -----------------------------
st.markdown(
    '<div class="section-title">오늘의 식단</div>',
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="meal-card">
        <div class="meal-type">KT 중식</div>
        <div class="meal-menu">
            제육볶음 · 계란찜 · 김치
        </div>
        <div class="meal-caption">
            현재 Mock 데이터로 표시 중입니다
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
        "▣\n출결 계산\n출석률과 지원 기준 확인",
        key="attendance_button",
        use_container_width=True,
    ):
        st.switch_page("pages/attendance_page.py")

with col2:
    if st.button(
        "◇\nAI 챗봇\n학습·생활 관련 질문",
        key="chatbot_button",
        use_container_width=True,
    ):
        st.switch_page("pages/chatbot_page.py")

col3, col4 = st.columns(2, gap="small")

with col3:
    if st.button(
        "○\n공지사항\n공지 제목 검색 및 조회",
        key="notice_button",
        use_container_width=True,
    ):
        st.switch_page("pages/notices_page.py")

with col4:
    if st.button(
        "◁\n민원 신청\n민원 작성과 상태 확인",
        key="complaint_button",
        use_container_width=True,
    ):
        st.switch_page("pages/complaints_page.py")


# -----------------------------
# 안내 영역
# -----------------------------
st.markdown(
    """
    <div class="notice-box">
        각 기능은 현재 화면 이동 및 Agent 연결 준비 단계입니다.
    </div>
    """,
    unsafe_allow_html=True,
)