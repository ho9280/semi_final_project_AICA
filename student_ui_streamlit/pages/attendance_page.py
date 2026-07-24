import streamlit as st

st.set_page_config(
    page_title="출결 계산",
    page_icon="📊",
    layout="centered",
)

st.title("출결 계산")

if st.button("← 메인으로"):
    st.switch_page("student_app.py")

st.info("출결 계산 화면을 준비 중입니다.")