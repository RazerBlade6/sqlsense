import pytest

from app.llm import structured_output_method


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("au.anthropic.claude-sonnet-5-5", "json_schema"),
        ("au.anthropic.claude-haiku-5-5", "json_schema"),
        ("apac.amazon.nova-pro-v1:0", "function_calling"),
        ("apac.amazon.nova-micro-v1:0", "function_calling"),
    ],
)
def test_structured_output_method(model_id: str, expected: str) -> None:
    assert structured_output_method(model_id) == expected
