import sys
from pathlib import Path

import streamlit as st


# =========================================================
# attendance.py 경로 설정
# =========================================================
CURRENT_FILE = Path(__file__).resolve()
PAGES_DIR = CURRENT_FILE.parent
STUDENT_UI_DIR = PAGES_DIR.parent

if str(STUDENT_UI_DIR) not in sys.path:
    sys.path.insert(0, str(STUDENT_UI_DIR))

import attendance


# =========================================================
# 페이지 설정
# =========================================================
st.set_page_config(
    page_title="출결 계산",
    page_icon="📅",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# =========================================================
# 모바일 UI CSS
# =========================================================
st.markdown(
    """
    <style>
    /* 전체 모바일 화면 폭 */
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

    /* Streamlit 기본 UI 숨김 */
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

    /* 메인 이동 버튼 */
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

    /* 상단 파란색 영역 */
    .attendance-header {
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

    .attendance-header-title {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 7px;
    }

    .attendance-header-subtitle {
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

    /* 안내 카드 */
    .guide-card {
        background-color: #EEF6FD;
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 20px;
        color: #4E5968;
        font-size: 13px;
        line-height: 1.75;
    }

    .guide-card strong {
        color: #202124;
    }

    /* 지원 기준 카드 */
    .target-card {
        background-color: white;
        border: 1px solid #EEF1F5;
        border-radius: 16px;
        padding: 15px 10px;
        text-align: center;
        min-height: 88px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
    }

    .target-label {
        font-size: 12px;
        color: #7A808A;
        margin-bottom: 8px;
    }

    .target-value {
        font-size: 15px;
        color: #202124;
        font-weight: 700;
    }

    /* 입력창 */
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label {
        color: #202124;
        font-size: 14px;
        font-weight: 600;
    }

    div[data-baseweb="select"] > div,
    div[data-testid="stNumberInput"] input {
        background-color: #F1F4F8;
        border-radius: 12px;
    }

    /* 결과 카드 */
    .result-card {
        background-color: white;
        border: 1px solid #EEF1F5;
        border-radius: 18px;
        padding: 18px;
        margin-top: 4px;
        margin-bottom: 14px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
    }

    .result-label {
        font-size: 13px;
        color: #7A808A;
        margin-bottom: 6px;
    }

    .result-value {
        font-size: 23px;
        font-weight: 700;
        color: #202124;
    }

    /* 구분선 */
    hr {
        border: none;
        border-top: 1px solid #E8ECF1;
        margin-top: 24px;
        margin-bottom: 24px;
    }

    /* 알림 메시지 */
    div[data-testid="stAlert"] {
        border-radius: 14px;
        font-size: 13px;
    }

    /* 상세 계산 기준 */
    div[data-testid="stExpander"] {
        background-color: white;
        border: 1px solid #E8ECF1;
        border-radius: 14px;
    }

    /* metric 기본 여백 축소 */
    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #EEF1F5;
        border-radius: 16px;
        padding: 14px;
    }

    div[data-testid="stMetricLabel"] {
        font-size: 13px;
    }

    div[data-testid="stMetricValue"] {
        font-size: 23px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
    <div class="attendance-header">
        <div class="attendance-header-title">
            📅 출결 계산
        </div>
        <div class="attendance-header-subtitle">
            월별 출석률과 지원금 수급 기준을 확인해 보세요
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 이용 안내
# =========================================================
st.markdown(
    """
    <div class="guide-card">
        <strong>💡 이용 안내</strong><br>
        지각·조퇴·외출은 각 항목별로 3회 누적 시
        결석 1일로 환산됩니다.<br>
        계산 결과는 참고용이며 실제 출결과 일치하지 않을 수 있습니다.
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 조회 월 선택
# =========================================================
st.markdown(
    '<div class="section-title">조회 월 선택</div>',
    unsafe_allow_html=True,
)

selected_month = st.selectbox(
    label="조회할 월",
    options=[5, 6, 7, 8, 9, 10, 11, 12],
    index=2,
    format_func=lambda month: f"{month}월",
    label_visibility="collapsed",
)


# 선택 월 기본 정보
base_info = attendance.calculate_attendance_tool(
    month=selected_month
)


# =========================================================
# 지원금 및 출결 기준
# =========================================================
st.markdown(
    '<div class="section-title">🎯 지원금 및 출결 기준</div>',
    unsafe_allow_html=True,
)

target_col1, target_col2, target_col3 = st.columns(3)

with target_col1:
    st.markdown(
        f"""
        <div class="target-card">
            <div class="target-label">50% 기준</div>
            <div class="target-value">
                {base_info['target_50_days']}일
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with target_col2:
    st.markdown(
        f"""
        <div class="target-card">
            <div class="target-label">80% 기준</div>
            <div class="target-value">
                {base_info['target_80_days']}일
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with target_col3:
    st.markdown(
        f"""
        <div class="target-card">
            <div class="target-label">공가 한도</div>
            <div class="target-value">
                {base_info['max_official_leave']}일
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# 출결 입력
# =========================================================
st.markdown(
    '<div class="section-title">✏️ 출결 내역 입력</div>',
    unsafe_allow_html=True,
)

input_col1, input_col2 = st.columns(2)

with input_col1:
    absent_input = st.number_input(
        label="결석 일수",
        min_value=0,
        max_value=base_info["total_days"],
        value=0,
        step=1,
    )

    tardy_input = st.number_input(
        label="지각 횟수",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        help="지각 3회당 결석 1일로 환산됩니다.",
    )

with input_col2:
    early_leave_input = st.number_input(
        label="조퇴 횟수",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        help="조퇴 3회당 결석 1일로 환산됩니다.",
    )

    out_input = st.number_input(
        label="외출 횟수",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        help="외출 3회당 결석 1일로 환산됩니다.",
    )

official_leave_input = st.number_input(
    label="공가 일수",
    min_value=0,
    max_value=base_info["max_official_leave"],
    value=0,
    step=1,
    help="공가는 최대 허용 범위 내에서 출석일수에 반영됩니다.",
)


# =========================================================
# 출결 계산
# =========================================================
result = attendance.calculate_attendance_tool(
    month=selected_month,
    absent_days=absent_input,
    tardy_count=tardy_input,
    early_leave_count=early_leave_input,
    out_count=out_input,
    official_leave_days=official_leave_input,
)


# =========================================================
# 계산 결과
# =========================================================
st.markdown(
    '<div class="section-title">📊 출석 산출 결과</div>',
    unsafe_allow_html=True,
)

result_col1, result_col2 = st.columns(2)

with result_col1:
    st.metric(
        label="인정 출석일수",
        value=(
            f"{result['calculated_days']}일 "
            f"/ {result['total_days']}일"
        ),
    )

with result_col2:
    st.metric(
        label="현재 출석률",
        value=f"{result['attendance_rate']}%",
    )


attendance_progress = min(
    max(result["attendance_rate"] / 100, 0.0),
    1.0,
)

st.progress(attendance_progress)


# =========================================================
# 지원 기준 확인
# =========================================================
st.markdown(
    '<div class="section-title">✅ 지원 기준 확인</div>',
    unsafe_allow_html=True,
)

if result["calculated_days"] >= result["target_80_days"]:
    st.success(
        "현재 인정 출석일수는 80% 기준을 충족합니다."
    )

elif result["calculated_days"] >= result["target_50_days"]:
    remaining_days = (
        result["target_80_days"]
        - result["calculated_days"]
    )

    st.warning(
        f"현재 50% 기준을 충족했습니다. "
        f"80% 기준까지 {remaining_days}일이 더 필요합니다."
    )

else:
    remaining_days = (
        result["target_50_days"]
        - result["calculated_days"]
    )

    st.error(
        f"현재 50% 기준 미달입니다. "
        f"50% 기준까지 {remaining_days}일이 더 필요합니다."
    )


# =========================================================
# 상세 계산 기준
# =========================================================
with st.expander("상세 계산 기준 보기"):
    st.write(f"- 선택 월: {result['month']}월")
    st.write(f"- 총 수업일수: {result['total_days']}일")
    st.write(f"- 순수 결석: {absent_input}일")

    st.write(
        f"- 지각 {tardy_input}회 → "
        f"환산 결석 {tardy_input // 3}일"
    )

    st.write(
        f"- 조퇴 {early_leave_input}회 → "
        f"환산 결석 {early_leave_input // 3}일"
    )

    st.write(
        f"- 외출 {out_input}회 → "
        f"환산 결석 {out_input // 3}일"
    )

    st.write(f"- 공가 인정: {official_leave_input}일")
    st.write(f"- 50% 기준: {result['target_50_days']}일")
    st.write(f"- 80% 기준: {result['target_80_days']}일")

    st.write(
        f"- 최대 공가 한도: "
        f"{result['max_official_leave']}일"
    )