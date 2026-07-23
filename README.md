# semi_final_project_AICA

## 📌 [가이드] VSCode 기반 출결 Agent 백엔드 실행 방법

### 1. 실행 전 체크리스트 (파일 위치)

VSCode에서 프로젝트 폴더를 열었을 때, 아래 파일들이 지정된 위치에 있는지 확인합니다.

* `attendance_agent.py` (백엔드 메인 코드)
* `aica_attendance_rules.md` (출결 규정 문서)
* `aica_financial_support.md` (지원비 규정 문서)



> 💡 **폴더 위치 관련 팁**: MD 파일들이 `data/` 같은 하위 폴더에 들어간 경우, `attendance_agent.py` 상단의 `load_md_file("하위폴더/파일명.md")` 경로 문자열만 맞춰주시면 됩니다.

---

### 2. VSCode 터미널 패키지 설치

VSCode 상단 메뉴 **`Terminal` $\rightarrow$ `New Terminal**` (단축키: `Ctrl + ~`)을 열고 아래 명령어를 실행하여 필수 패키지를 설치합니다.

```bash
pip install fastapi uvicorn langchain langchain-openai langgraph pydantic

```

---

### 3. API Key 주입 및 백엔드 서버 구동

VSCode 터미널 종류(Git Bash, PowerShell, CMD)에 따라 **본인의 OpenAI API Key**를 설정하고 서버를 실행합니다.

#### 🟢 VSCode 터미널이 `Git Bash` 또는 `Bash`인 경우 (추천)

```bash
export OPENAI_API_KEY='본인의_OPENAI_API_KEY'
uvicorn attendance_agent:app --reload --port 8000

```

#### 🔵 VSCode 터미널이 `PowerShell`인 경우

```powershell
$env:OPENAI_API_KEY="본인의_OPENAI_API_KEY"
uvicorn attendance_agent:app --reload --port 8000

```

#### 🟡 VSCode 터미널이 `Command Prompt (CMD)`인 경우

```cmd
set OPENAI_API_KEY=본인의_OPENAI_API_KEY
uvicorn attendance_agent:app --reload --port 8000

```

---

### 4. 서버 동작 확인 (Swagger UI)

서버가 뜬 후 브라우저 주소창에 아래 주소를 입력하여 접속합니다.

* **접속 주소**: `http://localhost:8000/docs`
* **`POST /chat`** 테스트 클릭 $\rightarrow$ `Try it out`으로 규정 질문 및 계산기 팝업 질문이 제대로 응답되는지 확인합니다.