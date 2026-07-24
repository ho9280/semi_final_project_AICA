import streamlit as st

st.set_page_config(
    page_title="민원 신청",
    page_icon="📣",
    layout="centered",
)

st.title("민원 신청")

if st.button("← 메인으로"):
    st.switch_page("student_app.py")

st.info("민원 화면을 준비 중입니다.")