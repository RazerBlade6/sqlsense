from typing import Any, Literal

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
    llm = get_chat_model(model_id, settings)
    return llm.with_structured_output(schema, method=structured_output_method(model_id))
