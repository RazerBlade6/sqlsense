from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agents.sql_agent import SQLQueryAgent
from app.config import Settings, get_settings
from app.models import QueryRequest, QueryResponse, SchemaResponse
from app.warehouse import Warehouse
from app.warehouse.factory import get_warehouse

app = FastAPI(title="SQLSense API", version="0.2.0")


def get_agent(
    settings: Settings = Depends(get_settings),
    warehouse: Warehouse = Depends(get_warehouse),
) -> SQLQueryAgent:
    return SQLQueryAgent(warehouse, settings)


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
def schema(warehouse: Warehouse = Depends(get_warehouse)) -> SchemaResponse:
    return SchemaResponse(engine=warehouse.engine, summary=warehouse.schema_summary())


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, agent: SQLQueryAgent = Depends(get_agent)) -> QueryResponse:
    try:
        return agent.run(request.question, request.max_attempts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
