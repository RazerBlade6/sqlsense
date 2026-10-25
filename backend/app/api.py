from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings, get_settings
from app.db import get_engine
from app.models import QueryRequest, QueryResponse, SchemaResponse
from app.schema import build_schema_summary

app = FastAPI(title="SQLSense API", version="0.2.0")


def get_agent(
    settings: Settings = Depends(get_settings),
    engine: Engine = Depends(get_engine),
) -> SQLQueryAgent:
    return SQLQueryAgent(engine, settings)


settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/schema", response_model=SchemaResponse)
def schema(
    current_settings: Settings = Depends(get_settings),
    engine: Engine = Depends(get_engine),
) -> SchemaResponse:
    return SchemaResponse(
        schemas=current_settings.schema_names,
        summary=build_schema_summary(engine, current_settings.schema_names),
    )


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, agent: SQLQueryAgent = Depends(get_agent)) -> QueryResponse:
    try:
        return agent.run(request.question, request.max_attempts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
