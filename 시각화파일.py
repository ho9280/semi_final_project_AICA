import sqlite3
from typing import Tuple
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# 한글 폰트 설정 (Windows/Mac 공통 대처)
plt.rcParams["font.family"] = "Malgun Gothic"  # Windows (Mac: 'AppleGothic')
plt.rcParams["axes.unicode_minus"] = False


def load_complaint_data(db_path: str = "complaints.db") -> pd.DataFrame:
    """SQLite DB에서 민원 데이터를 읽어와 DataFrame으로 반환합니다."""
    conn = sqlite3.connect(db_path)
    query = "SELECT id, category, status, created_at FROM complaints"
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Type Hint 및 데이터 검증 assert
    assert isinstance(df, pd.DataFrame), "데이터 로드 실패: DataFrame 타입이 아닙니다."
    return df


def generate_admin_dashboard(
    df: pd.DataFrame, output_filename: str = "admin_dashboard_eda.png"
) -> None:
    """관리자용 미처리 현황 및 카테고리별 분포 시각화 차트를 생성하고 저장합니다."""
    # 1. 상태별 기본 집계
    total_count: int = len(df)
    status_counts: pd.Series = df["status"].value_counts()

    # 상태 명칭 매핑 처리
    pending_count: int = status_counts.get("접수", 0)
    in_progress_count: int = status_counts.get("⚙️ 처리 중", 0) + status_counts.get(
        "처리 중", 0
    )
    completed_count: int = status_counts.get("✅ 처리 완료", 0) + status_counts.get(
        "처리 완료", 0
    )

    # 2. Subplots 서브플롯 구성 (1행 2열)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    fig.suptitle(
        "🏛️ 광주 AI 아카데미 민원 관리자 대시보드 (PoC EDA)",
        fontsize=18,
        fontweight="bold",
    )

    # -------------------------------------------------------------
    # [좌측 차트] 관리자 핵심 KPI 숫자 요약 카드
    # -------------------------------------------------------------
    ax_kpi = axes[0]
    ax_kpi.axis("off")  # 축 숨기기

    kpi_text = (
        f"📊 총 접수 건수 : {total_count} 건\n\n"
        f"🚨 미처리 (접수) : {pending_count} 건\n\n"
        f"🔄 처리 진행 중 : {in_progress_count} 건\n\n"
        f"✅ 처리 완료     : {completed_count} 건"
    )

    ax_kpi.text(
        0.5,
        0.5,
        kpi_text,
        transform=ax_kpi.transAxes,
        fontsize=16,
        fontweight="bold",
        va="center",
        ha="center",
        bbox=dict(
            boxstyle="round,pad=1.5",
            facecolor="#f8f9fa",
            edgecolor="#007bff",
            linewidth=2,
        ),
    )
    ax_kpi.set_title(
        "[1] 실시간 민원 처리 상태 요약 (KPI)", fontsize=14, fontweight="bold", pad=20
    )

    # -------------------------------------------------------------
    # [우측 차트] 카테고리별 민원 발생 및 처리 현황 (Bar Chart)
    # -------------------------------------------------------------
    ax_bar = axes[1]
    category_status_df = (
        df.groupby(["category", "status"]).size().unstack(fill_value=0)
    )

    category_status_df.plot(
        kind="bar", stacked=True, ax=ax_bar, colormap="viridis", edgecolor="black"
    )

    ax_bar.set_title(
        "[2] 카테고리별 민원 분포 및 미처리 현황", fontsize=14, fontweight="bold", pad=20
    )
    ax_bar.set_xlabel("민원 카테고리", fontsize=12, fontweight="bold")
    ax_bar.set_ylabel("민원 건수", fontsize=12, fontweight="bold")
    ax_bar.legend(title="처리 상태", bbox_to_anchor=(1.05, 1), loc="upper left")
    ax_bar.tick_params(axis="x", rotation=30)
    ax_bar.grid(axis="y", linestyle="--", alpha=0.7)

    plt.tight_layout()
    plt.savefig(output_filename, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"✅ 시각화 차트 생성이 완료되었습니다: {output_filename}")


if __name__ == "__main__":
    # 데이터 로드 및 시각화 실행
    complaint_df = load_complaint_data("complaints.db")
    generate_admin_dashboard(complaint_df)