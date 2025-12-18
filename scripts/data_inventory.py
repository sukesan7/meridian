from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def scan_parquet_dir(parquet_dir: Path) -> pd.DataFrame:
    rows = []
    for p in sorted(parquet_dir.rglob("*.parquet")):
        try:
            df = pd.read_parquet(p, columns=["open", "high", "low", "close"])
            idx = df.index
            rows.append(
                {
                    "path": str(p),
                    "rows": len(df),
                    "t_min": idx.min(),
                    "t_max": idx.max(),
                    "cols": ",".join(df.columns),
                    "bytes": p.stat().st_size,
                }
            )
        except Exception as e:
            rows.append({"path": str(p), "error": repr(e)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet-dir", required=True)
    ap.add_argument("--out", default="outputs/data_inventory.csv")
    args = ap.parse_args()

    parquet_dir = Path(args.parquet_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    inv = scan_parquet_dir(parquet_dir)

    # Derive covered dates if timestamps exist
    if "t_min" in inv.columns and "t_max" in inv.columns:
        ok = inv.dropna(subset=["t_min", "t_max"]).copy()
        if not ok.empty:
            ok["date_min"] = pd.to_datetime(ok["t_min"]).dt.date
            ok["date_max"] = pd.to_datetime(ok["t_max"]).dt.date

    inv.to_csv(out, index=False)
    print(f"Wrote inventory: {out}")
    print(inv.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
