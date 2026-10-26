import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient

from app.agents.planner import HistoryTurn
from app.api import app, get_assistant, get_memory
from app.config import Settings, get_settings
from app.memory import BudgetExceeded, DynamoMemory, LocalMemory
from app.models import ChatResponse


class StubAssistant:
    def __init__(self) -> None:
        self.histories: list[list[HistoryTurn]] = []

    def ask(self, question, history, session_id) -> ChatResponse:
        self.histories.append(list(history))
        return ChatResponse(
            session_id=session_id,
            question=question,
            standalone_question=question,
            route="docs",
            answer=f"answer to {question}",
            total_ms=1,
        )


@pytest.fixture
def client():
    assistant, memory = StubAssistant(), LocalMemory()
    app.dependency_overrides[get_assistant] = lambda: assistant
    app.dependency_overrides[get_memory] = lambda: memory
    app.dependency_overrides[get_settings] = lambda: Settings(DAILY_QUESTION_LIMIT=3)
    yield TestClient(app), assistant
    app.dependency_overrides.clear()


def test_chat_keeps_session_history(client) -> None:
    http, assistant = client
    first = http.post("/chat", json={"question": "Top departments?"}).json()
    http.post("/chat", json={"question": "And the bottom?", "session_id": first["session_id"]})

    assert assistant.histories[0] == []
    assert assistant.histories[1][0].question == "Top departments?"


def test_chat_rejects_malformed_session_ids(client) -> None:
    http, _ = client
    response = http.post("/chat", json={"question": "Hello?", "session_id": "../../etc"})
    assert response.status_code == 422


def test_daily_budget_returns_429(client) -> None:
    http, _ = client
    codes = [http.post("/chat", json={"question": "Q one"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_dynamo_budget_maps_condition_failure() -> None:
    memory = DynamoMemory("sqlsense-sessions", "ap-southeast-2")
    with Stubber(memory.table.meta.client) as stub:
        stub.add_client_error("update_item", "ConditionalCheckFailedException")
        with pytest.raises(BudgetExceeded):
            memory.take_question(10)
