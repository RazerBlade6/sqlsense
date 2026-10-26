import time
from dataclasses import dataclass
from typing import Any, Literal

from botocore.exceptions import ClientError
from langchain_aws import ChatBedrockConverse
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.config import Settings

StructuredOutputMethod = Literal["function_calling", "json_schema"]


def get_chat_model(model_id: str, settings: Settings) -> ChatBedrockConverse:
    """Bedrock Converse chat model.

    Temperature 0 keeps runs repeatable where it's supported; newer Claude models reject
    sampling parameters, so they run with defaults.
    """
    kwargs: dict[str, Any] = {}
    if "anthropic." not in model_id:
        kwargs["temperature"] = 0
    return ChatBedrockConverse(
        model=model_id,
        region_name=settings.aws_region,
        max_tokens=settings.llm_max_tokens,
        **kwargs,
    )


def structured_output_method(model_id: str) -> StructuredOutputMethod:
    # Recent Claude models reject the forced tool_choice that function calling relies on,
    # so they use Bedrock's native JSON-schema output instead.
    if "anthropic." in model_id:
        return "json_schema"
    return "function_calling"


def with_structured_output(
    model_id: str, schema: type[BaseModel], settings: Settings
) -> Runnable[Any, Any]:
    """Structured output that keeps the raw message, so callers can record token usage."""
    llm = get_chat_model(model_id, settings)
    return llm.with_structured_output(
        schema, method=structured_output_method(model_id), include_raw=True
    )


@dataclass
class LLMCall[T: BaseModel]:
    output: T
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int


def invoke_structured[T: BaseModel](
    runnable: Runnable[Any, Any], inputs: dict[str, Any], schema: type[T]
) -> LLMCall[T]:
    started = time.perf_counter()
    try:
        result = runnable.invoke(inputs)
    except ClientError as exc:
        # Nova occasionally emits a malformed tool call; a second try usually succeeds.
        if exc.response["Error"]["Code"] != "ModelErrorException":
            raise
        result = runnable.invoke(inputs)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if result.get("parsing_error"):
        raise result["parsing_error"]
    parsed = result["parsed"]
    if parsed is None:
        raise ValueError(f"model returned no {schema.__name__}")
    usage = getattr(result["raw"], "usage_metadata", None) or {}
    return LLMCall(
        output=parsed if isinstance(parsed, schema) else schema.model_validate(parsed),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        duration_ms=duration_ms,
    )
