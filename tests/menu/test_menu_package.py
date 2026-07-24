"""app/menu_agent_tool.py가 약속한 공개 인터페이스를 검증한다.

다른 팀 코드는 다음처럼만 import해서 쓸 수 있어야 한다.

    from app.menu_agent_tool import get_menu, get_current_menu, reload_menu_data
    from app.menu_agent_tool import check_ocr_status, preview_menu_ocr, import_menu_image
    from app.menu_agent_tool import menu_agent_tool, menu_current_tool, menu_image_import_tool
    from app.menu_agent_tool import MENU_AGENT_TOOLS, MENU_ADMIN_TOOLS
    from app.menu_agent_tool import ChatRequest, ChatResponse, menu_router
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.menu_agent_tool as menu_agent_tool_module
from app.main import app
from app.menu_agent_tool import (
    MENU_ADMIN_TOOLS,
    MENU_AGENT_TOOLS,
    ChatRequest,
    ChatResponse,
    check_ocr_status,
    get_current_menu,
    get_menu,
    import_menu_image,
    menu_agent_tool,
    menu_current_tool,
    menu_image_import_tool,
    menu_router,
    preview_menu_ocr,
    reload_menu_data,
)


def test_package_exports_exactly_the_public_tool_functions():
    assert menu_agent_tool_module.__all__ == [
        "get_menu",
        "get_current_menu",
        "reload_menu_data",
        "check_ocr_status",
        "preview_menu_ocr",
        "import_menu_image",
        "handle_chat_message",
        "menu_agent_tool",
        "menu_current_tool",
        "menu_image_import_tool",
        "MENU_AGENT_TOOLS",
        "MENU_ADMIN_TOOLS",
        "ChatRequest",
        "ChatResponse",
        "menu_router",
    ]
    assert callable(get_menu)
    assert callable(get_current_menu)
    assert callable(reload_menu_data)
    assert callable(check_ocr_status)
    assert callable(preview_menu_ocr)
    assert callable(import_menu_image)
    assert callable(menu_agent_tool.run)
    assert callable(menu_agent_tool.invoke)
    assert MENU_AGENT_TOOLS == [menu_agent_tool]
    assert MENU_ADMIN_TOOLS == [menu_current_tool, menu_image_import_tool]


def test_ocr_functions_work_without_crashing_even_if_engine_missing():
    # OCR 패키지/프로그램이 없어도 예외를 던지지 않고 구조화된 결과를 반환해야 한다.
    status = check_ocr_status()
    assert isinstance(status, dict)
    assert "any_engine_ready" in status

    preview = preview_menu_ocr("존재하지-않는-이미지.png")
    assert preview["success"] is False
    assert preview["error"] is not None

    result = import_menu_image("존재하지-않는-이미지.png")
    assert result["success"] is False
    assert result["status"] == "rejected"


def test_menu_agent_tool_object_returns_fixed_chat_schema():
    response = menu_agent_tool.run(user_input="오늘 KT 메뉴 뭐야?", thread_id="t-1")
    assert set(response.keys()) == {"text", "action", "show_buttons"}
    assert isinstance(response["text"], str)
    assert response["action"] is None
    assert response["show_buttons"] is True

    invoked = menu_agent_tool.invoke({"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"})
    assert set(invoked.keys()) == {"text", "action", "show_buttons"}
    assert invoked["show_buttons"] is True


def test_chat_request_response_and_router_are_importable():
    request = ChatRequest(user_input="오늘 KT 메뉴 뭐야?", thread_id="t-1")
    assert request.user_input == "오늘 KT 메뉴 뭐야?"

    response = ChatResponse(text="답변", action=None)
    assert response.text == "답변"
    assert response.show_buttons is True

    assert any(getattr(route, "path", None) == "/chat" for route in menu_router.routes)


def test_chat_endpoint_matches_shared_agent_schema():
    response = TestClient(app).post(
        "/chat",
        json={"user_input": "오늘 KT 메뉴 뭐야?", "thread_id": "t-1"},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"text", "action", "show_buttons"}
    assert isinstance(response.json()["text"], str)
    assert response.json()["action"] is None
    assert response.json()["show_buttons"] is True


def test_chat_request_rejects_missing_or_too_long_fields():
    client = TestClient(app)
    assert client.post("/chat", json={"thread_id": "t-1"}).status_code == 422
    assert client.post("/chat", json={"user_input": "메뉴 알려줘"}).status_code == 422
    assert client.post(
        "/chat",
        json={"user_input": "가" * 501, "thread_id": "t-1"},
    ).status_code == 422
