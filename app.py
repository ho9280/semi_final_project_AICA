import streamlit as st
import attendance

st.set_page_config(
    page_title="7기 인사교 출결 계산기",
    page_icon="📅",
    layout="centered"
)

st.title("📅 7기 인사교 출결 계산기")

st.info(
    """
    💡 **이용 안내 및 주요 기준**
    - **지각, 조퇴, 외출 각 항목별 3회 누적 시 1결석** 처리됩니다.
    - **50% 이상:** 주거지원비 지급 대상 (타지역 교육생 기준 35만 원)
    - **80% 이상:** 식비(30만 원) + 교통비(20만 원) + (주거지원비 35만 원) 지원 대상
    - *본 결과는 참고용 수치이며, 정식 출석부 집계 기준을 따릅니다.*
    """
)

st.divider()

selected_month = st.selectbox(
    "📅 조회 월 선택",
    options=[5, 6, 7, 8, 9, 10, 11, 12],
    index=2, # 기본값: 7월
    format_func=lambda x: f"{x}월"
)

base_info = attendance.calculate_attendance_tool(month=selected_month)

# 상단 가이드 영역 (공가 한도 표시 추가)
st.subheader("🎯 지원금 수급 및 출결 가이드")
col_target1, col_target2, col_target3 = st.columns(3)

with col_target1:
    st.caption("50% 기준 (주거비)")
    st.write(f"최소 **{base_info['target_50_days']}일** 출석")

with col_target2:
    st.caption("80% 기준 (식비·교통비)")
    st.write(f"최소 **{base_info['target_80_days']}일** 출석")

with col_target3:
    st.caption("최대 공가 한도")
    st.write(f"최대 **{base_info['max_official_leave']}일** (20%이내)")

st.divider()

# 출결 내역 입력 (지각, 조퇴, 외출 각각 분리)
st.subheader("✏️ 출결 내역 입력")

col_in1, col_in2 = st.columns(2)

with col_in1:
    absent_input = st.number_input(
        "결석 일수",
        min_value=0,
        max_value=20,
        value=0,
        step=1
    )
    tardy_input = st.number_input(
        "지각 횟수 (3회=1결석)",
        min_value=0,
        max_value=20,
        value=0,
        step=1
    )

with col_in2:
    early_leave_input = st.number_input(
        "조퇴 횟수 (3회=1결석)",
        min_value=0,
        max_value=20,
        value=0,
        step=1
    )
    out_input = st.number_input(
        "외출 횟수 (3회=1결석)",
        min_value=0,
        max_value=20,
        value=0,
        step=1
    )

st.markdown("---")

official_leave_input = st.number_input(
    "공가 (출석인정) 일수",
    min_value=0,
    max_value=base_info['max_official_leave'],
    value=0,
    step=1,
    help="공가는 인정 출석일수에 합산됩니다."
)

# 결과 산출
result = attendance.calculate_attendance_tool(
    month=selected_month,
    absent_days=absent_input,
    tardy_count=tardy_input,
    early_leave_count=early_leave_input,
    out_count=out_input,
    official_leave_days=official_leave_input
)

st.divider()

st.subheader("📊 출석 산출 결과")

col_res1, col_res2 = st.columns(2)

with col_res1:
    st.metric(
        label="인정 출석일수",
        value=f"{result['calculated_days']}일 / {result['total_days']}일"
    )

with col_res2:
    st.metric(
        label="현재 출석률",
        value=f"{result['attendance_rate']} %"
    )