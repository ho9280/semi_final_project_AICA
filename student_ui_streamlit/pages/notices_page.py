import streamlit as st

st.set_page_config(
    page_title="공지사항",
    page_icon="🔔",
    layout="centered",
)

st.title("공지사항")

if st.button("← 메인으로"):
    st.switch_page("student_app.py")

st.info("공지사항 화면을 준비 중입니다.")