"""
Registry of LLM model configurations used by CROSSFIRE.

Each entry describes how to load the model via langchain (`get_model` in
utils.py), whether it supports native structured output
(`.with_structured_output()`), and which env var holds its API key.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    key: str
    model: str
    model_provider: str
    with_structure: bool
    label: str
    env_key: str


MODELS = {
    "qwen_small": ModelConfig(
        key="qwen_small",
        model="qwen/qwen2.5-72b-instruct",
        model_provider="novita",
        with_structure=False,
        label="Qwen 2.5-72B",
        env_key="NOVITA_API_KEY",
    ),
    "mistral_small": ModelConfig(
        key="mistral_small",
        model="mistral-small-latest",
        model_provider="mistralai",
        with_structure=True,
        label="Mistral Small",
        env_key="MISTRAL_API_KEY",
    ),
    "gpt_small": ModelConfig(
        key="gpt_small",
        model="gpt-4o-mini",
        model_provider="openai",
        with_structure=True,
        label="GPT-4o mini",
        env_key="OPENAI_API_KEY",
    ),
}
