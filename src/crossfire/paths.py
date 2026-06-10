"""
Centralised filesystem paths for the CROSSFIRE package.

Assumes this file is at:
    project_root/src/crossfire/paths.py
"""

from pathlib import Path


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = get_project_root()

PROMPTS_DIR  = PROJECT_ROOT / "prompts"
PROFILES_DIR = PROJECT_ROOT / "profiles"
LOGS_DIR     = PROJECT_ROOT / "logs"
DATA_DIR     = PROJECT_ROOT / "data"
RESULTS_DIR  = PROJECT_ROOT / "results"
CONFIGS_DIR  = PROJECT_ROOT / "configs"
