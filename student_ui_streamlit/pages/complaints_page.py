import requests
import streamlit as st

# 민원 FastAPI 서버 주소
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
    page_icon="✍️",
    layout="centered",
)

st.title("민원 신청")

if st.button("← 메인으로"):
    st.switch_page("student_app.py")


# -----------------------------------
# 공통 API 요청 함수
# -----------------------------------
def request_summary(category: str, raw_content: str) -> str:
    """민원 내용을 FastAPI 요약 API로 보내 AI 요약문 반환"""

    # 비공개 민원은 AI 요약을 사용하지 않음
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
    """민원을 DB에 최종 등록"""

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


# -----------------------------------
# 민원 작성 영역
# -----------------------------------
st.subheader("새 민원 작성")

with st.form("complaint_form", clear_on_submit=True):
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
        placeholder="첨부할 사진 링크가 있다면 입력해 주세요. 선택 사항입니다.",
    )

    submitted = st.form_submit_button(
        "민원 제출",
        use_container_width=True,
    )


if submitted:
    cleaned_content = raw_content.strip()
    cleaned_photo_url = photo_url.strip() or None

    if not cleaned_content:
        st.warning("민원 내용을 입력해 주세요.")

    elif len(cleaned_content) > 1000:
        st.warning("민원 내용은 최대 1,000자까지 입력할 수 있습니다.")

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
            st.error("민원 서버 응답 시간이 초과되었습니다.")

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
            st.error(f"예상하지 못한 오류가 발생했습니다: {error}")


st.divider()


# -----------------------------------
# 공개 민원 피드
# -----------------------------------
st.subheader("민원 게시판")

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
        complaint_category = complaint.get("category", "카테고리 없음")
        summary = complaint.get("summary", "요약 내용 없음")
        status = complaint.get("status", "접수")
        like_count = complaint.get("like_count", 0)
        created_at = complaint.get("created_at", "")
        is_liked = bool(complaint.get("is_liked_by_me", False))

        with st.container(border=True):
            st.markdown(
                f"**No. {complaint_id} · {complaint_category}**"
            )

            st.write(summary)

            col1, col2 = st.columns(2)

            with col1:
                st.caption(f"상태: {status}")

                if created_at:
                    st.caption(f"등록일: {created_at}")

            with col2:
                button_text = (
                    f"공감완료 · {like_count}"
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
                            st.success("민원에 공감했습니다.")
                        else:
                            st.info(
                                result.get(
                                    "message",
                                    "이미 공감한 민원입니다.",
                                )
                            )

                        st.rerun()

                    except requests.exceptions.ConnectionError:
                        st.error("민원 서버에 연결할 수 없습니다.")

                    except requests.exceptions.HTTPError as error:
                        try:
                            detail = error.response.json().get("detail")
                        except Exception:
                            detail = None

                        st.error(
                            detail
                            or f"공감 처리 중 오류가 발생했습니다: {error}"
                        )

                    except Exception as error:
                        st.error(
                            f"공감 처리 중 오류가 발생했습니다: {error}"
                        )

except requests.exceptions.ConnectionError:
    st.error(
        "민원 게시판을 불러올 수 없습니다. "
        "FastAPI 서버가 실행 중인지 확인해 주세요."
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
    st.error(f"민원 목록 조회 중 오류가 발생했습니다: {error}")