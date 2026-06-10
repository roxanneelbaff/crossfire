"""Response parsers for non-structured-output LLM models."""

import json
import re


def _parse_structured_json(response, schema_cls):
    """
    Parse a raw LangChain AIMessage response into a Pydantic model instance.

    Handles common quirks:
    - <think>...</think> reasoning blocks (Qwen / reasoning models)
    - ```json ... ``` / ``` ... ``` code fences
    """
    raw_content = response.content
    content = raw_content.strip()

    # Strip <think>...</think> reasoning blocks
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    if content.startswith("```json"):
        content = content.removeprefix("```json").strip()
    if content.startswith("```"):
        content = content.removeprefix("```").strip()
    if content.endswith("```"):
        content = content.removesuffix("```").strip()

    if not content:
        raise ValueError(f"Empty response after stripping. Raw content: {raw_content!r}")

    data = json.loads(content)
    return schema_cls.model_validate(data)
