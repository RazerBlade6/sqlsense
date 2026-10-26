"""Conversation memory (last N turns per session) and the daily question budget.

DynamoDB layout, one table:
  PK session_id = <uuid>,          SK = turn#<ISO timestamp>   one item per answered turn
  PK session_id = budget#<date>,   SK = count                  questions asked that day (UTC)
Items carry `expires_at` for DynamoDB TTL.
"""

import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from app.agents.planner import HistoryTurn

SESSION_TTL_S = 7 * 24 * 3600
BUDGET_TTL_S = 3 * 24 * 3600


class BudgetExceeded(RuntimeError):
    pass


class Memory(Protocol):
    def load(self, session_id: str, limit: int) -> list[HistoryTurn]: ...

    def save(self, session_id: str, turn: HistoryTurn) -> None: ...

    def take_question(self, daily_limit: int) -> None:
        """Count one question against today's budget; raise BudgetExceeded when it's spent."""
        ...


class LocalMemory:
    def __init__(self) -> None:
        self._turns: dict[str, list[HistoryTurn]] = defaultdict(list)
        self._budget: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def load(self, session_id: str, limit: int) -> list[HistoryTurn]:
        return self._turns[session_id][-limit:]

    def save(self, session_id: str, turn: HistoryTurn) -> None:
        self._turns[session_id].append(turn)

    def take_question(self, daily_limit: int) -> None:
        if daily_limit <= 0:
            return
        with self._lock:
            today = _today()
            if self._budget[today] >= daily_limit:
                raise BudgetExceeded(f"the daily limit of {daily_limit} questions is used up")
            self._budget[today] += 1


class DynamoMemory:
    def __init__(self, table_name: str, region: str):
        self.table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    def load(self, session_id: str, limit: int) -> list[HistoryTurn]:
        response = self.table.query(
            KeyConditionExpression="session_id = :s AND begins_with(sk, :p)",
            ExpressionAttributeValues={":s": session_id, ":p": "turn#"},
            ScanIndexForward=False,
            Limit=limit,
        )
        items = reversed(response.get("Items", []))
        return [
            HistoryTurn(question=i["question"], answer=i["answer"], sql=i.get("sql")) for i in items
        ]

    def save(self, session_id: str, turn: HistoryTurn) -> None:
        item = {
            "session_id": session_id,
            "sk": f"turn#{datetime.now(UTC).isoformat(timespec='milliseconds')}",
            "question": turn.question,
            "answer": turn.answer,
            "expires_at": int(time.time()) + SESSION_TTL_S,
        }
        if turn.sql:
            item["sql"] = turn.sql
        self.table.put_item(Item=item)

    def take_question(self, daily_limit: int) -> None:
        if daily_limit <= 0:
            return
        try:
            self.table.update_item(
                Key={"session_id": f"budget#{_today()}", "sk": "count"},
                UpdateExpression="ADD questions :one SET expires_at = :ttl",
                ConditionExpression="attribute_not_exists(questions) OR questions < :limit",
                ExpressionAttributeValues={
                    ":one": 1,
                    ":limit": daily_limit,
                    ":ttl": int(time.time()) + BUDGET_TTL_S,
                },
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise BudgetExceeded(
                    f"the daily limit of {daily_limit} questions is used up"
                ) from exc
            raise


def _today() -> str:
    return datetime.now(UTC).date().isoformat()
