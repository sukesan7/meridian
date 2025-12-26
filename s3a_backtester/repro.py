"""
Reproducibility Module
----------------------
Handles environment hashing, git versioning, and deterministic serialization.
Ensures that every backtest run can be linked back to the exact code and configuration state.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, cast


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_json_dumps(obj: Any) -> str:
    """
    Produce a stable, sorted JSON string for hashing and comparison.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    """Compute SHA256 hash of a text string (UTF-8)."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA256 hash of a file by reading in chunks."""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def try_git_sha() -> Optional[str]:
    """Attempt to retrieve the current Git commit SHA."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return None


def try_git_describe() -> Optional[str]:
    """Attempt to retrieve the current Git tag/description."""
    try:
        out = subprocess.check_output(
            ["git", "describe", "--tags", "--always"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return None


def env_info() -> Dict[str, Any]:
    """Capture critical environment details for reproducibility."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "executable": sys.executable,
        "cwd": os.getcwd(),
    }


def dataclass_to_dict(dc: Any) -> Dict[str, Any]:
    """Safely convert a dataclass instance to a dictionary."""
    if not is_dataclass(dc):
        raise TypeError("dataclass_to_dict expected a dataclass instance")
    return asdict(cast(Any, dc))
