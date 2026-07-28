import math
from typing import Dict, Union

# 월별 총 수업일수 (평일 기준)
MONTH_TOTAL_DAYS: Dict[int, int] = {
    5: 17,
    6: 21,
    7: 22,
    8: 20,
    9: 20,
    10: 20,
    11: 21,
    12: 9
}

def calculate_attendance_tool(
    month: int,
    absent_days: int = 0,
    tardy_count: int = 0,       # 지각 횟수
    early_leave_count: int = 0, # 조퇴 횟수
    out_count: int = 0,         # 외출 횟수
    official_leave_days: int = 0 # 공가 일수
) -> Dict[str, Union[int, float]]:
    """
    7기 출결 계산 로직 (지각/조퇴/외출 각각 3회당 1결석)
    """
    total_days: int = MONTH_TOTAL_DAYS.get(month, 20)
    
    # 지각, 조퇴, 외출 각각 항목별 3회당 1결석 처리
    tardy_absent: int = tardy_count // 3
    early_leave_absent: int = early_leave_count // 3
    out_absent: int = out_count // 3
    
    total_converted_absent: int = tardy_absent + early_leave_absent + out_absent
    
    # 순수 결석 합산
    net_absent: int = absent_days + total_converted_absent
    
    # 인정 출석일수 계산 (총 수업일수를 초과할 수 없도록 min 처리)
    raw_calculated_days: int = total_days - net_absent + official_leave_days
    calculated_days: int = min(total_days, max(0, raw_calculated_days))
    
    # 출석률 계산 (%)
    attendance_rate: float = round((calculated_days / total_days) * 100, 2)
    
    # 지원금 달성 최소 출석일수
    target_50_days: int = math.ceil(total_days * 0.5)
    target_80_days: int = math.ceil(total_days * 0.8)
    
    # 규정상 최대 공가 허용 한도 (전체 교육일수의 20% 이내)
    max_official_leave: int = math.floor(total_days * 0.2)
    
    return {
        "month": month,
        "total_days": total_days,
        "calculated_days": calculated_days,
        "attendance_rate": attendance_rate,
        "target_50_days": target_50_days,
        "target_80_days": target_80_days,
        "max_official_leave": max_official_leave
    }