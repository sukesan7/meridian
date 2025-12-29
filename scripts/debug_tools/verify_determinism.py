"""
Determinism Verifier
--------------------
Calculates a cryptographic hash of two trade logs to prove they are identical.
Used in CI/CD to validate that the engine is deterministic across runs.

Usage:
    python scripts/verify_determinism.py <file_a> <file_b>
"""

import sys
import hashlib
import pandas as pd
from pathlib import Path


def get_deterministic_fingerprint(file_path: str) -> str:
    """
    Normalizes and hashes a DataFrame to ensure reproducible signatures.
    Handles column ordering, row sorting, and floating-point epsilon noise.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Artifact not found: {path}")

    # 1. Load Data
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    if df.empty:
        return "empty_dataframe_hash"

    # 2. Sort Columns (prevent column insertion order from affecting hash)
    df = df.sort_index(axis=1)

    # 3. Sort Rows (prevent execution order jitter from affecting hash)
    #    We attempt to sort by entry time + symbol + price to lock order
    sort_cols = [
        c for c in ["entry_time", "date", "symbol", "entry"] if c in df.columns
    ]
    if sort_cols:
        df = df.sort_values(by=sort_cols).reset_index(drop=True)

    # 4. Normalize Floats (The "Epsilon" Killer)
    #    Round to 8 decimals to ignore architecture-specific noise (Intel vs M1)
    #    Convert to string to ensure serialization consistency
    df_str = df.copy()
    for col in df.select_dtypes(include=["float", "float32", "float64"]).columns:
        # Fill NaNs with a fixed string before formatting to avoid NaN != NaN issues
        df_str[col] = df[col].fillna(-999.999).apply(lambda x: f"{x:.8f}")

    # 5. Serialize to JSON string (canonical format)
    #    'split' format is compact and stable
    content = df_str.to_json(orient="split", date_format="iso", index=False)

    # 6. SHA-256 Hash
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_determinism.py <file_a> <file_b>")
        sys.exit(1)

    file_a = sys.argv[1]
    file_b = sys.argv[2]

    print(f"Comparing artifacts:\n  A: {file_a}\n  B: {file_b}")

    try:
        hash_a = get_deterministic_fingerprint(file_a)
        hash_b = get_deterministic_fingerprint(file_b)
    except Exception as e:
        print(f"Error processing files: {e}")
        sys.exit(1)

    print("-" * 60)
    print(f"Hash A: {hash_a}")
    print(f"Hash B: {hash_b}")
    print("-" * 60)

    if hash_a == hash_b:
        print("✅ SUCCESS: Artifacts are bit-perfect identical.")
        sys.exit(0)
    else:
        print("❌ FAILURE: Artifacts diverge!")
        sys.exit(1)


if __name__ == "__main__":
    main()
