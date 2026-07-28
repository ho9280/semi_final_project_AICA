import html
import mimetypes
import sqlite3
from pathlib import Path

import streamlit as st


# =========================================================
# 페이지 기본 설정
# =========================================================
st.set_page_config(
    page_title="공지사항",
    page_icon="📢",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# =========================================================
# 프로젝트 경로 설정
#
# 현재 파일:
# 프로젝트최상위/student_ui_streamlit/pages/notices_page.py
#
# DB:
# 프로젝트최상위/db/notices.db
#
# 첨부파일:
# 프로젝트최상위/AICA_notice/notice_attachment/...
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "db" / "notices.db"


# =========================================================
# DB 조회 함수
# =========================================================
def load_notices(search_keyword: str = "") -> list[dict]:
    """
    notices.db에서 공지사항과 첨부파일 정보를 조회한다.

    - 검색 대상: title 컬럼만
    - 정렬: 작성일 최신순, 동일 날짜는 notice_id 내림차순
    """

    if not DB_PATH.exists():
        return []

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        cursor = connection.cursor()
        keyword = search_keyword.strip()

        if keyword:
            cursor.execute(
                """
                SELECT
                    notice_id,
                    title,
                    release_date,
                    content
                FROM notices
                WHERE title LIKE ?
                ORDER BY
                    release_date DESC,
                    notice_id DESC
                """,
                (f"%{keyword}%",),
            )
        else:
            cursor.execute(
                """
                SELECT
                    notice_id,
                    title,
                    release_date,
                    content
                FROM notices
                ORDER BY
                    release_date DESC,
                    notice_id DESC
                """
            )

        notice_rows = cursor.fetchall()
        notices = []

        for notice_row in notice_rows:
            cursor.execute(
                """
                SELECT
                    attachment_id,
                    file_name,
                    attachment_path,
                    file_type
                FROM notice_attachments
                WHERE notice_id = ?
                ORDER BY attachment_id ASC
                """,
                (notice_row["notice_id"],),
            )

            attachments = [
                dict(attachment_row)
                for attachment_row in cursor.fetchall()
            ]

            notices.append(
                {
                    "notice_id": notice_row["notice_id"],
                    "title": notice_row["title"] or "제목 없음",
                    "release_date": (
                        notice_row["release_date"] or "날짜 없음"
                    ),
                    "content": (
                        notice_row["content"]
                        or "등록된 공지 내용이 없습니다."
                    ),
                    "attachments": attachments,
                }
            )

        return notices

    finally:
        connection.close()


# =========================================================
# 첨부파일 실제 경로 찾기
# =========================================================
def resolve_attachment_path(
    attachment_path: str | None,
    notice_id: int,
    file_name: str,
) -> Path | None:
    """
    DB에 저장된 첨부파일 경로를 실제 Path로 변환한다.

    DB에는 다음처럼 상대경로가 저장될 수 있다.
    AICA_notice/notice_attachment/38/example.pdf

    경로 정보가 없거나 맞지 않으면 공지 번호와 파일명으로
    기본 첨부파일 폴더에서도 다시 찾는다.
    """

    candidates: list[Path] = []

    if attachment_path:
        raw_path = Path(str(attachment_path))

        # DB에 절대경로가 저장된 경우
        if raw_path.is_absolute():
            candidates.append(raw_path)

        # 프로젝트 최상위 폴더 기준 상대경로
        candidates.append(PROJECT_ROOT / raw_path)

        # 현재 실행 위치 기준 상대경로
        candidates.append(Path.cwd() / raw_path)

    # DB 경로가 맞지 않을 때 사용할 기본 예상 경로
    candidates.append(
        PROJECT_ROOT
        / "AICA_notice"
        / "notice_attachment"
        / str(notice_id)
        / file_name
    )

    # 중복 경로 제거 후 실제 존재하는 파일 반환
    checked_paths: set[str] = set()

    for candidate in candidates:
        try:
            normalized = candidate.resolve()
        except OSError:
            normalized = candidate

        normalized_text = str(normalized)

        if normalized_text in checked_paths:
            continue

        checked_paths.add(normalized_text)

        if normalized.exists() and normalized.is_file():
            return normalized

    return None


# =========================================================
# MIME 타입 결정
# =========================================================
def get_mime_type(
    file_path: Path,
    file_type: str | None = None,
) -> str:
    guessed_type, _ = mimetypes.guess_type(file_path.name)

    if guessed_type:
        return guessed_type

    extension = (file_type or file_path.suffix.lstrip(".")).lower()

    fallback_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        "xlsx": (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        "pptx": (
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation"
        ),
        "txt": "text/plain",
    }

    return fallback_types.get(
        extension,
        "application/octet-stream",
    )


# =========================================================
# CSS
# =========================================================
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

    #MainMenu,
    footer,
    header {
        visibility: hidden;
    }

    .page-header {
        background: linear-gradient(
            135deg,
            #58A9E6 0%,
            #3291D9 100%
        );
        border-radius: 0 0 24px 24px;
        padding: 30px 22px 27px;
        margin-left: -16px;
        margin-right: -16px;
        margin-bottom: 22px;
        color: white;
    }

    .page-title {
        font-size: 25px;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .page-subtitle {
        font-size: 13px;
        color: rgba(255, 255, 255, 0.92);
    }

    .section-title {
        font-size: 19px;
        font-weight: 700;
        color: #202124;
        margin-top: 18px;
        margin-bottom: 12px;
    }

    .result-count {
        color: #747981;
        font-size: 13px;
        margin-bottom: 12px;
    }

    .empty-box,
    .error-box {
        background-color: white;
        border: 1px solid #EDF0F4;
        border-radius: 16px;
        padding: 24px 18px;
        color: #747981;
        font-size: 14px;
        line-height: 1.7;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
    }

    div[data-testid="stTextInput"] input {
        min-height: 46px;
        border-radius: 14px;
        border: 1px solid #E2E6EB;
        background-color: white;
    }

    div[data-testid="stTextInput"] input:focus {
        border-color: #3291D9;
        box-shadow: 0 0 0 2px rgba(50, 145, 217, 0.14);
    }

    div[data-testid="stExpander"] {
        background-color: white;
        border: 1px solid #EDF0F4;
        border-radius: 16px;
        margin-bottom: 10px;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.05);
        overflow: hidden;
    }

    div[data-testid="stExpander"] summary {
        padding-top: 3px;
        padding-bottom: 3px;
    }

    div[data-testid="stExpander"] summary p {
        color: #202124;
        font-size: 15px;
        font-weight: 700;
        line-height: 1.5;
    }

    .notice-meta {
        color: #888E98;
        font-size: 12px;
        margin-bottom: 14px;
    }

    .notice-content {
        color: #4E5968;
        font-size: 14px;
        line-height: 1.75;
        white-space: pre-wrap;
        word-break: break-word;
    }

    .attachment-title {
        margin-top: 20px;
        margin-bottom: 9px;
        color: #202124;
        font-size: 14px;
        font-weight: 700;
    }

    .attachment-info {
        background-color: #F5F8FC;
        border: 1px solid #E8EDF3;
        border-radius: 10px;
        padding: 9px 11px;
        margin-top: 8px;
        margin-bottom: 7px;
        color: #4E5968;
        font-size: 12px;
        word-break: break-all;
    }

    .file-error {
        background-color: #FFF4F2;
        border: 1px solid #FFD9D2;
        border-radius: 10px;
        padding: 10px 11px;
        margin-bottom: 7px;
        color: #B54738;
        font-size: 12px;
        line-height: 1.6;
        word-break: break-all;
    }

    div[data-testid="stButton"] > button {
        width: 100%;
        min-height: 46px;
        border-radius: 14px;
        border: 1px solid #DDE3EA;
        background-color: white;
        color: #4E5968;
        font-size: 14px;
        font-weight: 600;
    }

    div[data-testid="stButton"] > button:hover {
        border-color: #3291D9;
        color: #2E8CD9;
    }

    div[data-testid="stDownloadButton"] > button {
        width: 100%;
        min-height: 42px;
        border-radius: 11px;
        border: 1px solid #CFE3F7;
        background-color: #EEF6FD;
        color: #2E78B7;
        font-size: 13px;
        font-weight: 700;
        text-align: left;
    }

    div[data-testid="stDownloadButton"] > button:hover {
        border-color: #3291D9;
        background-color: #E4F1FC;
        color: #1769AA;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 상단 헤더
# =========================================================
st.markdown(
    """
    <div class="page-header">
        <div class="page-title">📢 공지사항</div>
        <div class="page-subtitle">
            공지 제목을 검색하고 상세 내용을 확인하세요
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 메인 화면으로 이동
# =========================================================
if st.button(
    "← 메인 화면으로 돌아가기",
    key="back_to_main",
    use_container_width=True,
):
    st.switch_page("student_app.py")


# =========================================================
# 공지 제목 검색
# =========================================================
st.markdown(
    '<div class="section-title">공지 검색</div>',
    unsafe_allow_html=True,
)

search_keyword = st.text_input(
    "공지 제목 검색",
    placeholder="검색할 공지 제목을 입력하세요",
    label_visibility="collapsed",
    key="notice_search_keyword",
)

st.caption("제목 기준으로만 검색됩니다.")


# =========================================================
# DB 연결 및 공지 목록 출력
# =========================================================
if not DB_PATH.exists():
    escaped_db_path = html.escape(str(DB_PATH))

    error_html = (
        '<div class="error-box">'
        "공지사항 DB 파일을 찾지 못했습니다.<br><br>"
        "확인 경로:<br>"
        f"{escaped_db_path}"
        "</div>"
    )

    st.markdown(
        error_html,
        unsafe_allow_html=True,
    )

else:
    try:
        notices = load_notices(search_keyword)

        st.markdown(
            '<div class="section-title">공지 목록</div>',
            unsafe_allow_html=True,
        )

        result_count_html = (
            '<div class="result-count">'
            f"총 {len(notices)}개의 공지가 있습니다."
            "</div>"
        )

        st.markdown(
            result_count_html,
            unsafe_allow_html=True,
        )

        if notices:
            for notice in notices:
                notice_id = int(notice["notice_id"])
                title = str(notice["title"])
                release_date = html.escape(
                    str(notice["release_date"])
                )
                content = html.escape(
                    str(notice["content"])
                )
                attachments = notice["attachments"]

                # 첨부파일이 있는 공지는 제목에 클립 표시
                attachment_icon = " 📎" if attachments else ""

                with st.expander(
                    f"No. {notice_id} · {title}{attachment_icon}"
                ):
                    notice_html = (
                        '<div class="notice-meta">'
                        f"작성일 · {release_date}"
                        "</div>"
                        '<div class="notice-content">'
                        f"{content}"
                        "</div>"
                    )

                    st.markdown(
                        notice_html,
                        unsafe_allow_html=True,
                    )

                    # -----------------------------------------
                    # 첨부파일
                    # -----------------------------------------
                    if attachments:
                        st.markdown(
                            (
                                '<div class="attachment-title">'
                                "📎 첨부파일"
                                "</div>"
                            ),
                            unsafe_allow_html=True,
                        )

                        for attachment_index, attachment in enumerate(
                            attachments
                        ):
                            attachment_id = attachment.get(
                                "attachment_id",
                                attachment_index,
                            )

                            file_name = str(
                                attachment.get("file_name")
                                or "첨부파일"
                            )

                            file_type = str(
                                attachment.get("file_type")
                                or Path(file_name).suffix.lstrip(".")
                            ).lower()

                            stored_path = attachment.get(
                                "attachment_path"
                            )

                            resolved_path = resolve_attachment_path(
                                attachment_path=stored_path,
                                notice_id=notice_id,
                                file_name=file_name,
                            )

                            escaped_file_name = html.escape(file_name)
                            type_label = (
                                file_type.upper()
                                if file_type
                                else "FILE"
                            )

                            st.markdown(
                                (
                                    '<div class="attachment-info">'
                                    f"📄 {escaped_file_name}"
                                    f" · {html.escape(type_label)}"
                                    "</div>"
                                ),
                                unsafe_allow_html=True,
                            )

                            if resolved_path is None:
                                stored_path_text = html.escape(
                                    str(stored_path or "경로 정보 없음")
                                )

                                st.markdown(
                                    (
                                        '<div class="file-error">'
                                        "첨부파일을 찾을 수 없습니다.<br>"
                                        f"저장 경로: {stored_path_text}"
                                        "</div>"
                                    ),
                                    unsafe_allow_html=True,
                                )
                                continue

                            try:
                                file_bytes = resolved_path.read_bytes()
                                mime_type = get_mime_type(
                                    resolved_path,
                                    file_type,
                                )
                            except OSError as error:
                                st.error(
                                    "첨부파일을 읽는 중 오류가 "
                                    f"발생했습니다: {error}"
                                )
                                continue

                            # 클릭 시 브라우저에서 다운로드하거나,
                            # 브라우저 설정에 따라 새 화면에서 열림
                            st.download_button(
                                label=f"📎 {file_name}",
                                data=file_bytes,
                                file_name=file_name,
                                mime=mime_type,
                                key=(
                                    f"notice_attachment_"
                                    f"{notice_id}_{attachment_id}_"
                                    f"{attachment_index}"
                                ),
                                use_container_width=True,
                            )

                            # 이미지 첨부파일은 페이지에서 미리보기 제공
                            if file_type in {
                                "png",
                                "jpg",
                                "jpeg",
                                "gif",
                                "webp",
                            }:
                                preview_key = (
                                    f"preview_{notice_id}_"
                                    f"{attachment_id}_"
                                    f"{attachment_index}"
                                )

                                if st.checkbox(
                                    "이미지 미리보기",
                                    key=preview_key,
                                ):
                                    st.image(
                                        file_bytes,
                                        caption=file_name,
                                        use_container_width=True,
                                    )

        else:
            st.markdown(
                (
                    '<div class="empty-box">'
                    "입력한 제목과 일치하는 공지사항이 없습니다."
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

    except sqlite3.Error as error:
        st.error(
            f"공지사항 DB 조회 중 오류가 발생했습니다: {error}"
        )