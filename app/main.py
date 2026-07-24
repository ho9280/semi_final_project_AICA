from fastapi import FastAPI

from app.menu_agent_tool import menu_router

app = FastAPI()
app.include_router(menu_router)


@app.get("/")
def read_root():
    return {
        "message": "인공지능사관학교 보조 앱 서버입니다."
    }
