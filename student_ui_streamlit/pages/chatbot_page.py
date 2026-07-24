import streamlit as st

st.set_page_config(
    page_title="AI 챗봇",
    page_icon="🤖",
    layout="centered",
)

st.title("AI 챗봇")

if st.button("← 메인으로"):
    st.switch_page("student_app.py")

st.info("AI 챗봇 화면을 준비 중입니다.")