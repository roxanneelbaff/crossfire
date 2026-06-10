"""
Renders prompt templates from the project-level prompts/ folder at runtime.
All templates use {placeholder} syntax (double-braces {{ }} for literal braces).
"""

from .utils import _read_prompt


def system_prompt(group_label: str, group_description: str) -> str:
    return _read_prompt(
        "system_role_play.md",
        group_label=group_label,
        group_description=group_description,
    )


def task_prompt(article_title: str, article_author: str, article_body: str, group_label: str) -> str:
    author_line = f"Author: {article_author}\n" if article_author else ""
    return _read_prompt(
        "task_assess_effect.md",
        article_title=article_title,
        author_line=author_line,
        article_body=article_body,
        group_label=group_label,
    )


def json_retry_reminder() -> str:
    return _read_prompt("json_retry_reminder.md")
