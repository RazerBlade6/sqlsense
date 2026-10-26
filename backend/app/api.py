import logging
import uuid
from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.planner import HistoryTurn
from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings, get_settings
from app.graph import Assistant
from app.memory import BudgetExceeded, DynamoMemory, LocalMemory, Memory
from app.models import ChatRequest, ChatResponse, QueryRequest, QueryResponse, SchemaResponse
from app.retrieval.factory import get_retriever
from app.warehouse import Warehouse
from app.warehouse.factory import get_warehouse

logger = logging.getLogger("sqlsense")

app = FastAPI(title="SQLSense API", version="0.3.0")


def get_agent(
    settings: Settings = Depends(get_settings),
    warehouse: Warehouse = Depends(get_warehouse),
) -> SQLQueryAgent:
    return SQLQueryAgent(warehouse, settings)


@lru_cache
def get_assistant() -> Assistant:
    return Assistant(get_warehouse(), get_retriever(), get_settings())


@lru_cache
def get_memory() -> Memory:
    settings = get_settings()
    if settings.memory_store == "dynamodb":
        return DynamoMemory(settings.sessions_table, settings.aws_region)
    return LocalMemory()


settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/schema", response_model=SchemaResponse)
def schema(warehouse: Warehouse = Depends(get_warehouse)) -> SchemaResponse:
    return SchemaResponse(engine=warehouse.engine, summary=warehouse.schema_summary())


@app.post("/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    agent: SQLQueryAgent = Depends(get_agent),
    memory: Memory = Depends(get_memory),
    settings: Settings = Depends(get_settings),
) -> QueryResponse:
    _take_question(memory, settings)
    try:
        return agent.run(request.question, request.max_attempts)
    except Exception as exc:
        logger.exception("query failed")
        raise HTTPException(status_code=500, detail="The SQL agent failed.") from exc


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    assistant: Assistant = Depends(get_assistant),
    memory: Memory = Depends(get_memory),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    """Session-aware question answering: the planner sees the session's last few turns."""
    _take_question(memory, settings)
    session_id = request.session_id or str(uuid.uuid4())
    history = memory.load(session_id, settings.memory_turns)
    try:
        response = assistant.ask(request.question, history, session_id)
    except Exception as exc:
        logger.exception("chat failed")
        raise HTTPException(status_code=500, detail="The assistant failed.") from exc
    memory.save(
        session_id,
        HistoryTurn(
            question=response.standalone_question,
            answer=response.answer,
            sql=response.result.sql if response.result else None,
        ),
    )
    return response


def _take_question(memory: Memory, settings: Settings) -> None:
    try:
        memory.take_question(settings.daily_question_limit)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=f"Try again tomorrow: {exc}.") from exc
