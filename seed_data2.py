import sqlite3
import random

# DB 연결
DB_FILE = "complaints.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 스키마 외래키 제약조건 활성화
cursor.execute("PRAGMA foreign_keys = ON;")

# 카테고리 6종
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

# 민원 데이터 샘플 템플릿
COMPLAINT_SAMPLES = {
    "시설/환경": [
        ("AI 카페 내부가 너무 추워서 장시간 학습하기 힘듭니다. 적정 온도로 설정해 주세요.", "AI 카페 난방 및 적정 온도 조절 요청"),
        ("1층 강의실 에어컨에서 원인 불명의 소음이 발생하여 수업에 집중하기 어렵습니다.", "1층 강의실 에어컨 소음 점검 및 수리 요청")
    ],
    "학습 장비": [
        ("2반 15번 자리의 모니터 화면이 주기적으로 깜빡거려서 작업하기가 매우 불편합니다.", "2반 15번 모니터 화면 깜빡임 점검 요청"),
        ("키보드 몇 개 키가 제대로 눌리지 않아 코딩 테스트 실습할 때 오타가 자주 납니다.", "실습실 키보드 키 입력 불량 점검 및 교체")
    ],
    "수업/학습": [
        ("최근 진행되는 딥러닝 실습 진도가 너무 빨라서 이론 복습 시간이 조금 더 필요합니다.", "딥러닝 실습 진도 속도 조절 및 복습 시간 요청"),
        ("온라인 강의 플랫폼의 VOD 영상 화질이 낮아 코드 글씨가 잘 보이지 않습니다.", "온라인 VOD 강의 영상 화질 개선 요청")
    ],
    "청결": [
        ("탕비실 전자레인지 내부에 음식물이 많이 튀어있어 위생 청소가 필요해 보입니다.", "탕비실 전자레인지 내부 위생 청소 요청"),
        ("3층 남자 화장실 세면대 배수구가 막혀 물이 잘 내려가지 않으니 점검 바랍니다.", "3층 세면대 배수구 막힘 점검 및 청소")
    ],
    "개선 방안": [
        ("1층 출입구 부근 흡연 구역 냄새가 들어오니 탈취제나 공기청정기를 놓아주세요.", "출입구 주변 탈취제 설치 및 담배 냄새 개선"),
        ("자습 공간에 스탠드 조명을 추가 배치해 주시면 야간 학습 환경이 더 좋아집니다.", "야간 자습 공간 스탠드 조명 추가 배치")
    ],
    "비공개 - 기타": [
        ("개인적인 사정으로 반 변경 가능 여부와 상담 절차에 대해 문의드리고 싶습니다.", "비공개 민원입니다."),
        ("출석 인정 서류 제출과 관련하여 개인정보 서류 확인 건으로 문의합니다.", "비공개 민원입니다.")
    ]
}

def add_complaints_only():
    print("🚀 기존 유저 대상 민원 게시글 추가 시작...")

    # 1. DB에서 기존 학생 유저 ID 목록 가져오기
    cursor.execute("SELECT id FROM users WHERE role = 'STUDENT'")
    student_rows = cursor.fetchall()

    if not student_rows:
        print("❌ DB에 등록된 학생 유저가 없습니다! database.py를 먼저 실행하세요.")
        return

    student_ids = [r[0] for r in student_rows]
    print(f"✅ 기존 학생 유저 {len(student_ids)}명 감지 완료.")

    # 2. 민원 데이터 주입 (6종 카테고리별 이미지 URL 1개씩 포함)
    category_idx = 0
    photo_assigned_count = 0

    # 앞선 학생들 ID부터 순차적으로 민원 생성
    for s_id in student_ids:
        category = CATEGORIES[category_idx % len(CATEGORIES)]
        category_idx += 1

        sample_raw, sample_sum = random.choice(COMPLAINT_SAMPLES[category])

        # 앞쪽 6개 민원에 카테고리별 이미지 직링크 지정
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
            (s_id, category, sample_raw, sample_sum, photo_url)
        )

    conn.commit()
    conn.close()
    print(f"🎉 민원 게시글 추가 완료! (이미지 첨부 민원: {photo_assigned_count}개 포함)")

if __name__ == "__main__":
    add_complaints_only()