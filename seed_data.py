import sqlite3
import random
from datetime import datetime

# DB 연결
DB_FILE = "complaints.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 스키마 외래키 제약조건 활성화
cursor.execute("PRAGMA foreign_keys = ON;")

# 카테고리 6종 (순환용)
CATEGORIES = [
    "시설/환경",
    "학습 장비",
    "수업/학습",
    "청결",
    "개선 방안",
    "비공개 - 기타"
]

# 카테고리별 고화질 무료 이미지 URL (Unsplash 직링크)
CATEGORY_PHOTOS = {
    "시설/환경": "https://images.unsplash.com/photo-1517581177682-a085bb7ffb15?w=600",
    "학습 장비": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600",
    "수업/학습": "https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=600",
    "청결": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=600",
    "개선 방안": "https://images.unsplash.com/photo-1531403009284-440f080d1e12?w=600",
    "비공개 - 기타": "https://images.unsplash.com/photo-1584438784894-089d6a62b8fa?w=600"
}

# 민원 데이터 생성을 위한 원문(50자 전후) 및 요약문 샘플 템플릿
COMPLAINT_SAMPLES = {
    "시설/환경": [
        ("AI 카페 내부가 너무 추워서 장시간 학습하기 힘듭니다. 적정 온도로 설정해 주세요.", "AI 카페 난방 및 적정 온도 조절 요청"),
        ("1층 강의실 에어컨에서 원인 불명의 소음이 발생하여 수업에 집중하기 어렵습니다.", "1층 강의실 에어컨 소음 점검 및 수리 요청"),
        ("휴게실 의자 중 하나가 부서져 있어서 부상의 위험이 있습니다. 교체 부탁드립니다.", "휴게실 파손된 의자 교체 및 파손 부위 점검")
    ],
    "학습 장비": [
        ("2반 15번 자리의 모니터 화면이 주기적으로 깜빡거려서 작업하기가 매우 불편합니다.", "2반 15번 모니터 화면 깜빡임 점검 요청"),
        ("실습용 PC의 실습 환경 백업 프로그램이 실행 시 오류를 뿜으며 자꾸 튕깁니다.", "실습 PC 백업 프로그램 오류 및 에러 점검"),
        ("키보드 몇 개 키가 제대로 눌리지 않아 코딩 테스트 실습할 때 오타가 자주 납니다.", "실습실 키보드 키 입력 불량 점검 및 교체")
    ],
    "수업/학습": [
        ("최근 진행되는 딥러닝 실습 진도가 너무 빨라서 이론 복습 시간이 조금 더 필요합니다.", "딥러닝 실습 진도 속도 조절 및 복습 시간 요청"),
        ("오후 실습 과제 난이도가 높아 추가 보충 자료나 가이드라인이 제공되면 좋겠습니다.", "실습 과제 보충 가이드라인 및 설명 자료 요청"),
        ("온라인 강의 플랫폼의 VOD 영상 화질이 낮아 코드 글씨가 잘 보이지 않습니다.", "온라인 VOD 강의 영상 화질 개선 요청")
    ],
    "청결": [
        ("탕비실 전자레인지 내부에 음식물이 많이 튀어있어 위생 청소가 필요해 보입니다.", "탕비실 전자레인지 내부 위생 청소 요청"),
        ("3층 남자 화장실 세면대 배수구가 막혀 물이 잘 내려가지 않으니 점검 바랍니다.", "3층 세면대 배수구 막힘 점검 및 청소"),
        ("강의실 입구 쓰레기통이 자주 가득 차서 분리수거함 추가 배치가 필요합니다.", "강의실 쓰레기통 수거 및 분리수거함 추가")
    ],
    "개선 방안": [
        ("1층 출입구 부근 흡연 구역 냄새가 들어오니 탈취제나 공기청정기를 놓아주세요.", "출입구 주변 탈취제 설치 및 담배 냄새 개선"),
        ("비오는 날 우산 비닐 커버 대신 우산 빗물 제거기를 설치하면 환경에 좋을 것 같아요.", "친환경 우산 빗물 제거기 도입 검토 요청"),
        ("자습 공간에 스탠드 조명을 추가 배치해 주시면 야간 학습 환경이 더 좋아집니다.", "야간 자습 공간 스탠드 조명 추가 배치")
    ],
    "비공개 - 기타": [
        ("개인적인 사정으로 반 변경 가능 여부와 상담 절차에 대해 문의드리고 싶습니다.", "비공개 민원입니다."),
        ("특정 교육생과의 마찰 문제로 인해 면담을 신청하고자 하오니 확인 부탁드립니다.", "비공개 민원입니다."),
        ("출석 인정 서류 제출과 관련하여 개인정보 서류 확인 건으로 문의합니다.", "비공개 민원입니다.")
    ]
}

def generate_seed_data():
    print("🚀 추가 더미 데이터 생성 시작...")

    # 1. 사용자 추가 (학생 40명, 관리자 5명)
    # 기존 DB의 student1, admin1 뒤에 붙도록 카운트를 1부터 시작 (student02, admin02...)
    students = []
    admins = []
    student_count = 1
    admin_count = 1

    for cycle in range(5):
        # 학생 8명 추가
        for _ in range(8):
            student_count += 1
            username = f"student{student_count:02d}"
            name = f"학생{student_count:02d}"
            birth = f"2001-{(student_count % 12) + 1:02d}-{(student_count % 28) + 1:02d}"

            cursor.execute(
                "INSERT INTO users (username, password, name, birth_date, role) VALUES (?, ?, ?, ?, ?)",
                (username, "1234", name, birth, "STUDENT")
            )
            user_id = cursor.lastrowid
            students.append({"id": user_id, "username": username})

        # 관리자 1명 추가
        admin_count += 1
        admin_username = f"admin{admin_count:02d}"
        admin_name = f"관리자{admin_count:02d}"
        admin_birth = f"1990-{(admin_count % 12) + 1:02d}-15"

        cursor.execute(
            "INSERT INTO users (username, password, name, birth_date, role) VALUES (?, ?, ?, ?, ?)",
            (admin_username, "1234", admin_name, admin_birth, "ADMIN")
        )
        admin_id = cursor.lastrowid
        admins.append({"id": admin_id, "username": admin_username})

    print(f"✅ 사용자 생성 완료: 학생 {len(students)}명 추가 (student02~), 관리자 {len(admins)}명 추가 (admin02~)")

    # 2. 민원 게시글 작성 (앞쪽 학생 6명에게 6종 포토 URL 각각 매칭)
    category_idx = 0  # 카테고리 순환용 인덱스
    photo_assigned_count = 0  # 이미지 할당 횟수 카운터

    for student in students:
        s_id = student["id"]

        # 조건: 초기 생성 학생 일부는 1개, 이후 학생은 2개 작성
        complaint_count = 1 if len(students) <= 30 else (1 if s_id <= 30 else 2)

        for _ in range(complaint_count):
            category = CATEGORIES[category_idx % len(CATEGORIES)]
            category_idx += 1  # 다음 카테고리로 변경

            # 민원 샘플 데이터 선택
            sample_raw, sample_sum = random.choice(COMPLAINT_SAMPLES[category])

            # 조건: 5의 배수 학생은 요약문 미실행 테스트용 ("")
            if s_id % 5 == 0:
                summary_text = ""
            else:
                summary_text = sample_sum

            # [핵심] 앞쪽 6개의 민원에만 카테고리별 포토 URL 할당, 이후는 None
            if photo_assigned_count < 6:
                photo_url = CATEGORY_PHOTOS[category]
                photo_assigned_count += 1
            else:
                photo_url = None

            cursor.execute(
                """
                INSERT INTO complaints (user_id, category, raw_content, summary, photo_url, status, like_count)
                VALUES (?, ?, ?, ?, ?, '접수', 0)
                """,
                (s_id, category, sample_raw, summary_text, photo_url)
            )

    print(f"✅ 민원 게시글 작성 완료 (이미지 첨부 민원: {photo_assigned_count}개)")

    # 3. 좋아요(Like) 처리
    for student in students:
        s_id = student["id"]
        target_complaints = []

        if s_id % 7 == 0:
            target_complaints.append(1)
        if s_id % 11 == 0:
            target_complaints.append(2)

        for cid in target_complaints:
            try:
                cursor.execute(
                    "INSERT INTO complaints_likes (complaint_id, user_id) VALUES (?, ?)",
                    (cid, s_id)
                )
                cursor.execute(
                    "UPDATE complaints SET like_count = like_count + 1 WHERE id = ?",
                    (cid,)
                )
            except sqlite3.IntegrityError:
                pass  # 중복 좋아요 무시

    # 커밋 및 종료
    conn.commit()
    conn.close()
    print("🎉 이미지 링크가 적용된 추가 시드 데이터 주입이 성공적으로 완료 되었습니다!")

if __name__ == "__main__":
    generate_seed_data()