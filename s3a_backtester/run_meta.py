"""
Run Metadata
------------
Captures and writes execution details (Git SHA, Config Hash, CLI args)
to ensure backtest provenance and reproducibility.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional

from s3a_backtester.repro import (
    dataclass_to_dict,
    env_info,
    sha256_file,
    sha256_text,
    stable_json_dumps,
    try_git_describe,
    try_git_sha,
    utc_now_iso,
)


def get_dependency_lock_hash() -> Optional[str]:
    """
    Attempts to locate and hash the 'requirements.lock' file.
    Assumes the lockfile is in the project root.
    """
    try:
        lock_path = Path("requirements.lock")
        if lock_path.exists() and lock_path.is_file():
            return sha256_file(lock_path)

        lock_path_alt = (
            Path(__file__).resolve().parent.parent.parent.parent / "requirements.lock"
        )
        if lock_path_alt.exists() and lock_path_alt.is_file():
            return sha256_file(lock_path_alt)

    except Exception:
        pass
    return None


def build_run_meta(
    *,
    cmd: str,
    argv: list[str],
    run_id: str,
    outputs_dir: str | Path,
    config_path: Optional[str] = None,
    config_obj: Optional[Any] = None,
    data_path: Optional[str] = None,
    seed: Optional[int] = None,
    hash_data: bool = False,
) -> Dict[str, Any]:
    """Constructs a metadata dictionary for the current execution context."""
    out_dir = Path(outputs_dir)

    meta: Dict[str, Any] = {
        "cmd": cmd,
        "run_id": run_id,
        "argv": argv,
        "outputs_dir": str(out_dir),
        "timestamp_utc": utc_now_iso(),
        "git_sha": try_git_sha(),
        "git_describe": try_git_describe(),
        "seed": seed,
        "env": env_info(),
        "dependency_lock_sha256": get_dependency_lock_hash(),
    }

    if config_path:
        meta["config_path"] = config_path
        meta["config_sha256"] = sha256_file(config_path)

    if config_obj is not None:
        cfg_dict = dataclass_to_dict(config_obj)
        meta["config_dump"] = cfg_dict
        meta["config_dump_sha256"] = sha256_text(stable_json_dumps(cfg_dict))

    if data_path:
        p = Path(data_path)
        meta["data_path"] = data_path
        try:
            stat = p.stat()
            meta["data_size_bytes"] = stat.st_size
            mtime_dt = datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            )
            meta["data_mtime_utc"] = mtime_dt.isoformat()
        except Exception:
            meta["data_mtime_utc"] = None

        if hash_data:
            meta["data_sha256"] = sha256_file(data_path)

    return meta


def write_run_meta(outputs_dir: str | Path, meta: Dict[str, Any]) -> Path:
    """Writes the metadata dictionary to run_meta.json in the output directory."""
    out_dir = Path(outputs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "run_meta.json"
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path
