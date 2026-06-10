"""LLM loading, prompt loading, and retry-invocation helpers."""

import os
import time
from contextlib import contextmanager

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .parsers import _parse_structured_json
from .paths import PROMPTS_DIR

MAX_RETRIES = 10


def get_model(model_name: str, model_provider: str, temperature: float = 0.7):
    """Load a chat model via langchain, dispatching on provider."""
    if model_provider in ("together", "mistralai"):
        llm = init_chat_model(
            model_name, model_provider=model_provider, temperature=temperature
        )
    elif model_provider in ("openai", "novita"):
        temperature = None if model_name.find("gpt-5") > -1 else temperature
        base_url = "https://api.novita.ai/openai" if model_provider == "novita" else None
        api_key = (
            os.environ["NOVITA_API_KEY"]
            if model_provider == "novita"
            else os.environ["OPENAI_API_KEY"]
        )

        if model_provider == "openai":
            llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                api_key=api_key,
            )
        else:
            llm = ChatOpenAI(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                api_key=api_key,
                extra_body={"enable_thinking": False},
            )
    elif model_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=model_name,
            temperature=temperature,
            api_key=os.environ["ANTHROPIC_API_KEY"],
        )
    else:
        raise ValueError(f"Unknown model_provider: {model_provider}")

    return llm


@contextmanager
def timer(label: str, time_in_seconds_arr: list):
    start = time.perf_counter()
    try:
        yield
    finally:
        end = time.perf_counter()
        print(f"{label}: {end - start:.4f} seconds")
        time_in_seconds_arr.append(end - start)


def _read_prompt(filename: str, **kwargs) -> str:
    with open(PROMPTS_DIR / filename, "r", encoding="utf-8") as f:
        text = f.read()
    return text.format(**kwargs)


def _invoke_with_retry(
    llm,
    instructions: str,
    system_prompt: str,
    structured_model=None,
    parser=None,
    cls_parser=None,
    max_retries: int = MAX_RETRIES,
):
    """
    Invoke an LLM with retries on any failure.

    - structured_model: a `llm.with_structured_output(Schema)` instance —
      returns a validated Pydantic model directly.
    - parser: callable(raw_response) -> Any
    - cls_parser: a Pydantic model class — raw response is parsed via
      `_parse_structured_json`.
    """
    response = None
    raw_response = None

    for attempt in range(max_retries):
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=instructions),
            ]

            if structured_model is not None:
                response = structured_model.invoke(messages)
            else:
                raw_response = llm.invoke(messages)
                response = raw_response
                if parser is not None:
                    response = parser(raw_response)
                elif cls_parser is not None:
                    response = _parse_structured_json(raw_response, cls_parser)

            return response

        except Exception as e:
            print(f"Retry {attempt + 1}/{max_retries} failed: {e}")

    if raw_response is not None:
        print("Last raw response:", raw_response)

    raise RuntimeError("LLM call failed after all retries.")
