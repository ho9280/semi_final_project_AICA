from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {
        "message": "인공지능사관학교 보조 앱 서버입니다."
    }