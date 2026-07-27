"""
db_update.py
설명: 기존 complaints.db의 status / updated_at / like_count 컬럼만
      카테고리별 가중치 랜덤 로직으로 재생성한다.

- id, user_id, category, raw_content, summary, photo_url, created_at 은 그대로 유지
- users, complaints_likes 등 다른 테이블은 건드리지 않음
- random.seed(42) 로 재현성 확보 (은하수를 여행하는 히치하이커를 위한 안내서, 42)
- updated_at 상한은 "실행 시점의 오늘 날짜"로 자동 캡 (하드코딩 아님)

사용법:
    python db_update.py                     # 기본 경로: ./complaints.db
    python db_update.py --db 경로/complaints.db
    python db_update.py --db 경로/complaints.db --no-backup   # 백업 생략(권장 안 함)
"""

import argparse
import shutil
import sqlite3
import random
from datetime import datetime, timedelta

SEED = 42  # 은하수를 여행하는 히치하이커를 위한 안내서 - 42

STATUSES = ['접수', '⚙️ 처리 중', '✅ 처리 완료', '❌ 승인 거절']

# 카테고리별 4상태 가중치 (접수, 처리중, 완료, 거절) - 합 100
CATEGORY_WEIGHTS = {
    '시설/환경':     [15, 40, 30, 15],
    '학습 장비':     [15, 40, 35, 10],
    '수업/학습':     [25, 20, 30, 25],
    '청결':          [20, 15, 55, 10],
    '개선 방안':     [20, 15, 25, 40],
    '비공개 - 기타': [25, 30, 25, 20],
}

# 카테고리별 최대 공감 수 (비공개-기타는 별도 처리)
CATEGORY_MAX_LIKES = {
    '시설/환경': 8,
    '학습 장비': 8,
    '수업/학습': 5,
    '청결': 5,
    '개선 방안': 10,
}


def renormalize_exclude_first(weights):
    """접수(첫 항목) 제외 후 나머지 3개 비율 재정규화"""
    rest = weights[1:]
    total = sum(rest)
    return [w / total for w in rest]


def weighted_choice(options, weights, rng):
    return rng.choices(options, weights=weights, k=1)[0]


def sample_days(status, category, rng):
    if status == '접수':
        return 0.0
    if status == '⚙️ 처리 중':
        base = rng.uniform(1, 5)
    elif status == '✅ 처리 완료':
        base = rng.uniform(3, 12)
    else:  # 승인 거절
        base = rng.uniform(1, 4)

    adj = 0.0
    if category in ('시설/환경', '학습 장비'):
        adj = rng.uniform(2, 3)
    elif category == '청결':
        adj = -rng.uniform(1, 2)
    elif category == '개선 방안':
        adj = 2.0

    return max(0.0, base + adj)


def adjust_for_weekend(dt):
    """토/일요일이면 다음 월요일 같은 시각으로 이동 (운영진 휴무 반영)"""
    weekday = dt.weekday()  # 0=월 ... 5=토, 6=일
    if weekday == 5:  # 토요일
        dt += timedelta(days=2)
    elif weekday == 6:  # 일요일
        dt += timedelta(days=1)
    return dt


def sample_like_count(status, category, rng):
    if category == '비공개 - 기타':
        return rng.randint(0, 2)

    max_likes = CATEGORY_MAX_LIKES.get(category, 5)
    if status == '접수':
        return rng.randint(0, max(1, max_likes // 3))
    elif status == '⚙️ 처리 중':
        return rng.randint(max_likes // 3, max_likes)
    elif status == '✅ 처리 완료':
        return rng.randint(max_likes // 4, max(1, max_likes * 2 // 3))
    else:  # 승인 거절
        return rng.randint(0, max(1, max_likes // 2))


def main():
    parser = argparse.ArgumentParser(description='complaints.db status/updated_at/like_count 재생성')
    parser.add_argument('--db', default='complaints.db', help='complaints.db 파일 경로 (기본: ./complaints.db)')
    parser.add_argument('--no-backup', action='store_true', help='백업 파일 생성 생략 (권장하지 않음)')
    args = parser.parse_args()

    db_path = args.db

    if not args.no_backup:
        backup_path = db_path.replace('.db', '') + '_backup_before_update.db'
        shutil.copy(db_path, backup_path)
        print(f'백업 완료: {backup_path}')

    rng = random.Random(SEED)
    today = datetime.now().replace(microsecond=0)  # 실행 시점 기준 상한 (하드코딩 아님)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute('SELECT id, category, created_at FROM complaints ORDER BY created_at DESC')
    rows = cur.fetchall()

    if not rows:
        print('complaints 테이블에 데이터가 없습니다. 종료합니다.')
        conn.close()
        return

    recent20_ids = set(r[0] for r in rows[:20])

    updates = []
    for cid, category, created_at_str in rows:
        if category not in CATEGORY_WEIGHTS:
            print(f'경고: id={cid} 의 카테고리 "{category}" 가 가중치 표에 없어 건너뜁니다.')
            continue

        created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
        weights = CATEGORY_WEIGHTS[category]

        if cid in recent20_ids:
            # 최근 20건: 접수 포함 4개 상태 가중치 랜덤
            status = weighted_choice(STATUSES, weights, rng)
        else:
            # 나머지: 접수 제외 3개 상태만
            rest_statuses = STATUSES[1:]
            rest_weights = renormalize_exclude_first(weights)
            status = weighted_choice(rest_statuses, rest_weights, rng)

        days = sample_days(status, category, rng)
        updated_at = created_at + timedelta(days=days)
        updated_at = adjust_for_weekend(updated_at)

        if updated_at > today:
            updated_at = today
        if updated_at < created_at:
            updated_at = created_at

        like_count = sample_like_count(status, category, rng)

        updates.append((status, updated_at.strftime('%Y-%m-%d %H:%M:%S'), like_count, cid))

    cur.executemany(
        'UPDATE complaints SET status = ?, updated_at = ?, like_count = ? WHERE id = ?',
        updates
    )
    conn.commit()

    print(f'\n총 {len(updates)}건 업데이트 완료 (기준일: {today.strftime("%Y-%m-%d %H:%M:%S")})\n')

    cur.execute('SELECT status, COUNT(*) FROM complaints GROUP BY status')
    print('=== 전체 status 분포 ===')
    for row in cur.fetchall():
        print(row)

    print('\n=== 카테고리별 status 분포 ===')
    cur.execute('SELECT category, status, COUNT(*) FROM complaints GROUP BY category, status ORDER BY category, status')
    for row in cur.fetchall():
        print(row)

    print('\n=== 카테고리별 평균 처리 소요일 (접수 제외) ===')
    cur.execute('''
        SELECT category,
               ROUND(AVG(JULIANDAY(updated_at) - JULIANDAY(created_at)), 2) as avg_days
        FROM complaints
        WHERE status != '접수'
        GROUP BY category
    ''')
    for row in cur.fetchall():
        print(row)

    print('\n=== 카테고리별 공감 수 평균/최대 ===')
    cur.execute('SELECT category, ROUND(AVG(like_count),2), MAX(like_count) FROM complaints GROUP BY category')
    for row in cur.fetchall():
        print(row)

    conn.close()


if __name__ == '__main__':
    main()