"""
Semantic determinism verifier for JSON artifacts.

Goal:
- Compare two JSON files for semantic equivalence under a stable canonicalization.
- Useful for CI gates where strict byte-identical JSON is not guaranteed
  (e.g., whitespace, key order, float formatting).

Canonicalization:
- Dict keys are sorted.
- Floats are rounded to configurable decimals.
- NaN/Inf/-Inf are normalized to strings ("NaN", "Infinity", "-Infinity").
- Lists preserve order by default (important: list ordering is often meaningful).
  Optional: enable deterministic sorting for lists of scalars or dicts via flags.

Exit code:
- 0 if equivalent under canonicalization
- 1 otherwise
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CanonConfig:
    float_decimals: int = 8
    sort_lists: bool = False
    list_sort_key: str = "id"


def _hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _normalize_float(x: float, decimals: int) -> Any:
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    return round(x, decimals)


def _is_scalar(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, bool))


def _try_sort_list(lst: list[Any], cfg: CanonConfig) -> list[Any]:
    """
    Sort lists only when it is safe-ish and deterministic.
    Default behavior (recommended) is to NOT sort lists.
    """
    if not cfg.sort_lists:
        return lst

    if all(_is_scalar(x) for x in lst):

        def scalar_key(v: Any) -> tuple[int, str]:
            if v is None:
                t = 0
            elif isinstance(v, bool):
                t = 1
            elif isinstance(v, int):
                t = 2
            else:  # str
                t = 3
            return (t, repr(v))

        return sorted(lst, key=scalar_key)

    if all(isinstance(x, dict) for x in lst):
        key = cfg.list_sort_key
        if all(key in x for x in lst):

            def dict_key(d: dict[str, Any]) -> str:
                return str(d.get(key))

            return sorted(lst, key=dict_key)

    return lst


def canonicalize(obj: Any, cfg: CanonConfig) -> Any:
    """
    Recursively canonicalize JSON-loaded Python objects.
    """
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, float):
        return _normalize_float(obj, cfg.float_decimals)

    if isinstance(obj, dict):
        return {k: canonicalize(obj[k], cfg) for k in sorted(obj.keys())}

    if isinstance(obj, list):
        canon_items = [canonicalize(x, cfg) for x in obj]
        canon_items = _try_sort_list(canon_items, cfg)
        return canon_items

    return str(obj)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_canonical(obj: Any) -> bytes:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    return s.encode("utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("a", help="Path to JSON A")
    p.add_argument("b", help="Path to JSON B")
    p.add_argument("--float-decimals", type=int, default=8)
    p.add_argument(
        "--sort-lists",
        action="store_true",
        help="Attempt to sort lists deterministically in safe cases (off by default).",
    )
    p.add_argument(
        "--list-sort-key",
        default="id",
        help="Key name used to sort lists of dicts when --sort-lists is enabled.",
    )
    args = p.parse_args()

    cfg = CanonConfig(
        float_decimals=args.float_decimals,
        sort_lists=args.sort_lists,
        list_sort_key=args.list_sort_key,
    )

    path_a = Path(args.a)
    path_b = Path(args.b)

    if not path_a.exists():
        print(f"ERROR: file not found: {path_a}", file=sys.stderr)
        return 2
    if not path_b.exists():
        print(f"ERROR: file not found: {path_b}", file=sys.stderr)
        return 2

    obj_a = load_json(path_a)
    obj_b = load_json(path_b)

    canon_a = canonicalize(obj_a, cfg)
    canon_b = canonicalize(obj_b, cfg)

    bytes_a = dump_canonical(canon_a)
    bytes_b = dump_canonical(canon_b)

    h_a = _hash_bytes(bytes_a)
    h_b = _hash_bytes(bytes_b)

    if h_a == h_b:
        print(f"OK: semantic JSON determinism verified (sha256={h_a})")
        return 0

    print("FAIL: semantic JSON mismatch under canonicalization", file=sys.stderr)
    print(f"A sha256: {h_a}", file=sys.stderr)
    print(f"B sha256: {h_b}", file=sys.stderr)

    if isinstance(canon_a, dict) and isinstance(canon_b, dict):
        keys_a = set(canon_a.keys())
        keys_b = set(canon_b.keys())
        only_a = sorted(keys_a - keys_b)
        only_b = sorted(keys_b - keys_a)
        if only_a:
            print(f"Keys only in A: {only_a[:20]}", file=sys.stderr)
        if only_b:
            print(f"Keys only in B: {only_b[:20]}", file=sys.stderr)

        common = sorted(keys_a & keys_b)
        for k in common:
            if canon_a.get(k) != canon_b.get(k):
                print(f"First differing top-level key: {k}", file=sys.stderr)
                break

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
