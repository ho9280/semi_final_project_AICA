import sys
from pathlib import Path

import streamlit as st


# =========================================================
# attendance.py를 불러오기 위한 경로 설정
# =========================================================
# 현재 파일:
# student_ui_streamlit/pages/attendance_page.py
#
# 불러올 파일:
# student_ui_streamlit/attendance.py

CURRENT_FILE = Path(__file__).resolve()
PAGES_DIR = CURRENT_FILE.parent
STUDENT_UI_DIR = PAGES_DIR.parent

if str(STUDENT_UI_DIR) not in sys.path:
    sys.path.insert(0, str(STUDENT_UI_DIR))


import attendance


# =========================================================
# 페이지 기본 설정
# =========================================================
st.set_page_config(
    page_title="7기 인사교 출결 계산기",
    page_icon="📅",
    layout="centered",
)


# =========================================================
# 상단 영역
# =========================================================
if st.button("← 메인으로"):
    st.switch_page("student_app.py")


st.title("📅 7기 인사교 출결 계산기")


st.info(
    """
    💡 **이용 안내 및 주요 기준**

    - **지각, 조퇴, 외출은 각 항목별 3회 누적 시 1결석** 처리됩니다.
    - **50% 이상:** 주거지원비 지급 대상
    - **80% 이상:** 식비와 교통비 지원 대상
    - 본 결과는 참고용 수치이며, 실제 출결은 정식 출석부 집계 기준을 따릅니다.
    """
)


st.divider()


# =========================================================
# 조회 월 선택
# =========================================================
selected_month = st.selectbox(
    label="📅 조회 월 선택",
    options=[5, 6, 7, 8, 9, 10, 11, 12],
    index=2,
    format_func=lambda month: f"{month}월",
)


# 선택한 월의 기본 정보 조회
base_info = attendance.calculate_attendance_tool(
    month=selected_month
)


# =========================================================
# 지원금 및 출결 가이드
# =========================================================
st.subheader("🎯 지원금 수급 및 출결 가이드")


col_target1, col_target2, col_target3 = st.columns(3)


with col_target1:
    st.caption("50% 기준")
    st.write(
        f"최소 **{base_info['target_50_days']}일** 출석"
    )


with col_target2:
    st.caption("80% 기준")
    st.write(
        f"최소 **{base_info['target_80_days']}일** 출석"
    )


with col_target3:
    st.caption("최대 공가 한도")
    st.write(
        f"최대 **{base_info['max_official_leave']}일**"
    )


st.divider()


# =========================================================
# 출결 내역 입력
# =========================================================
st.subheader("✏️ 출결 내역 입력")


col_input1, col_input2 = st.columns(2)


with col_input1:
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
        help="지각은 3회당 결석 1일로 환산됩니다.",
    )


with col_input2:
    early_leave_input = st.number_input(
        label="조퇴 횟수",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        help="조퇴는 3회당 결석 1일로 환산됩니다.",
    )

    out_input = st.number_input(
        label="외출 횟수",
        min_value=0,
        max_value=30,
        value=0,
        step=1,
        help="외출은 3회당 결석 1일로 환산됩니다.",
    )


official_leave_input = st.number_input(
    label="공가 일수",
    min_value=0,
    max_value=base_info["max_official_leave"],
    value=0,
    step=1,
    help="공가는 최대 허용 한도 내에서 인정 출석일수에 반영됩니다.",
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


st.divider()


# =========================================================
# 계산 결과
# =========================================================
st.subheader("📊 출석 산출 결과")


col_result1, col_result2 = st.columns(2)


with col_result1:
    st.metric(
        label="인정 출석일수",
        value=(
            f"{result['calculated_days']}일 "
            f"/ {result['total_days']}일"
        ),
    )


with col_result2:
    st.metric(
        label="현재 출석률",
        value=f"{result['attendance_rate']}%",
    )


# 출석률 진행 막대
attendance_progress = min(
    max(result["attendance_rate"] / 100, 0.0),
    1.0,
)

st.progress(attendance_progress)


# =========================================================
# 지원 기준 충족 여부
# =========================================================
st.subheader("✅ 지원 기준 확인")


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
        f"현재 50% 기준은 충족했습니다. "
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
    st.write(
        f"- 선택 월: {result['month']}월"
    )

    st.write(
        f"- 총 수업일수: {result['total_days']}일"
    )

    st.write(
        f"- 순수 결석: {absent_input}일"
    )

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

    st.write(
        f"- 공가 인정: {official_leave_input}일"
    )

    st.write(
        f"- 50% 기준: {result['target_50_days']}일"
    )

    st.write(
        f"- 80% 기준: {result['target_80_days']}일"
    )

    st.write(
        f"- 최대 공가 한도: "
        f"{result['max_official_leave']}일"
    )