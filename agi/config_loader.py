from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CONFIG_KEYS = {
    "AGI_LLM_PROVIDER",
    "GEMINI_API_KEY",
    "AGI_GEMINI_MODEL",
    "AGI_LLM_TIMEOUT_SECONDS",
    "AGI_LLM_MAX_OUTPUT_TOKENS",
}

PLACEHOLDER_VALUES = {
    "",
    "YOUR_GEMINI_API_KEY_HERE",
    "PASTE_YOUR_GEMINI_API_KEY_HERE",
}


def load_llm_config(base_dir: str | Path | None = None) -> dict[str, Any]:
    """Load optional local LLM config into this process environment.

    Existing OS environment variables win. This keeps deployment overrides safe
    and prevents a local config file from unexpectedly replacing explicit env.
    """
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    config_path = root / "llm_config.local.json"
    used_example = False
    if not config_path.exists():
        config_path = root / "llm_config.example.json"
        used_example = True
    if not config_path.exists():
        return {"loaded": False, "path": None, "used_example": False, "keys": []}

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"loaded": False, "path": str(config_path), "used_example": used_example, "keys": []}

    loaded_keys: list[str] = []
    for key in CONFIG_KEYS:
        if os.getenv(key):
            continue
        value = data.get(key)
        if value is None:
            continue
        value_text = str(value).strip()
        if key == "GEMINI_API_KEY" and value_text in PLACEHOLDER_VALUES:
            continue
        if not value_text:
            continue
        os.environ[key] = value_text
        loaded_keys.append(key)

    return {
        "loaded": bool(loaded_keys),
        "path": str(config_path),
        "used_example": used_example,
        "keys": loaded_keys,
    }
