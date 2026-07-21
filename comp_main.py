from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 1~4단계 모듈에서 임포트
from database import init_db
from router import router as complaints_router


# FastAPI 최신 표준 라이프사이클 핸들러 (on_event 경고 완전 제거)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # [서버 시작 시 실행] DB 테이블 생성 및 초기화
    init_db()
    yield
    # [서버 종료 시 실행] 필요한 자원 해제 로직 위치


# 1. FastAPI 메인 앱 생성 (lifespan 핸들러 연결)
app = FastAPI(
    title="광주 AI 아카데미 민원 수집 & 요약 서비스",
    description="학생 민원 접수, AI 요약 미리보기, 단방향 공감 피드 API",
    version="1.0.0",
    lifespan=lifespan,
)

# 2. CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 이미지 업로드 폴더 생성 및 정적 마운트
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 4. 라우터 부착
app.include_router(complaints_router)


# 5. 헬스체크 API
@app.get("/")
def root():
    return {
        "status": "online",
        "message": "민원 수집 API 서버가 정상 동작 중입니다.",
        "docs_url": "http://127.0.0.1:8000/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("comp_main:app", host="127.0.0.1", port=8000, reload=True)