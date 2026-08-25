"""Build work/outputs/dataset.csv from the FlyRank internship warehouse (HF, ~79M rows).

Follows the data contract documented in work/notebooks/w03_data_contract.ipynb:
  - feature window: 2026-01-01 -> 2026-03-31 (90 days)
  - label window:   2026-04-01 -> 2026-04-30
  - label: is_declining_label = 1 if GSC impressions dropped >= 30% from March to April
  - min-impressions filter: >= 50 GSC impressions in March AND in April
  - momentum_pct capped at the 99th percentile (right-tail only; -100% is the natural floor)

Never bring the 79M rows to pandas: DuckDB aggregates per (client_hash_id, content_hash_id)
remotely, only the small aggregate crosses the wire (see skills/querying-big-datasets/SKILL.md).

Token: reads HF_TOKEN from a local .env (gitignored) or the environment. Never hardcode it.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "work" / "outputs" / "dataset.csv"
REL = "hf://datasets/FlyRank/internship-warehouse"

FEATURE_START, FEATURE_END = "2026-01-01", "2026-03-31"
LAST30_START = "2026-03-01"          # March = recency slice of the feature window
LABEL_START, LABEL_END = "2026-04-01", "2026-04-30"
MIN_MONTHLY_IMPRESSIONS = 50
FIRST60_DAYS = 59                     # Jan (31) + Feb (28) 2026, actual calendar days


def load_hf_token() -> str:
    token = os.environ.get("HF_TOKEN")
    if token:
        return token
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip().startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("HF_TOKEN not found in environment or .env")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute(f"CREATE OR REPLACE SECRET hf (TYPE huggingface, TOKEN '{load_hf_token()}')")
    return con


def month_partitions(months: list[str]) -> str:
    """Build a read_parquet() call over exactly the needed month partitions (partition pruning)."""
    globs = ", ".join(f"'{REL}/fact_content_daily_performance/month={m}/*.parquet'" for m in months)
    return f"read_parquet([{globs}])"


FEATURE_SQL = """
SELECT
    client_hash_id,
    content_hash_id,
    SUM(CASE WHEN gsc_data_available THEN gsc_impressions ELSE 0 END)               AS impressions_90d,
    SUM(CASE WHEN gsc_data_available THEN gsc_clicks ELSE 0 END)                    AS clicks_90d,
    SUM(CASE WHEN gsc_data_available THEN gsc_sum_position ELSE 0 END)              AS sum_position_90d,
    SUM(ga4_sessions)                                                               AS sessions_90d,
    SUM(ga4_pageviews)                                                              AS pageviews_90d,
    SUM(ga4_engaged_sessions)                                                       AS engaged_sessions_90d,
    SUM(sessions_organic)                                                           AS organic_sessions_90d,
    SUM(CASE WHEN gsc_data_available AND report_date >= DATE '{last30_start}'
              THEN gsc_impressions ELSE 0 END)                                      AS impressions_last30,
    SUM(CASE WHEN gsc_data_available AND report_date <  DATE '{last30_start}'
              THEN gsc_impressions ELSE 0 END)                                      AS impressions_first60,
    COUNT(DISTINCT CASE WHEN gsc_data_available THEN report_date END)               AS active_days_90d
FROM {rel}
WHERE report_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY 1, 2
"""

LABEL_SQL = """
SELECT
    client_hash_id,
    content_hash_id,
    SUM(CASE WHEN gsc_data_available THEN gsc_impressions ELSE 0 END) AS impressions_apr
FROM {rel}
WHERE report_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY 1, 2
"""


def build(feature_months: list[str], label_months: list[str]) -> pd.DataFrame:
    con = connect()

    print(f"Aggregating feature window ({FEATURE_START} -> {FEATURE_END}) over partitions {feature_months} ...")
    features = con.sql(
        FEATURE_SQL.format(
            rel=month_partitions(feature_months),
            start=FEATURE_START, end=FEATURE_END, last30_start=LAST30_START,
        )
    ).df()
    print(f"  {len(features):,} (client, content) pairs with any activity in the feature window")

    print(f"Aggregating label window ({LABEL_START} -> {LABEL_END}) over partitions {label_months} ...")
    label = con.sql(
        LABEL_SQL.format(rel=month_partitions(label_months), start=LABEL_START, end=LABEL_END)
    ).df()

    clients = con.sql(f"SELECT client_hash_id, has_ga4_access FROM read_parquet('{REL}/dim_clients.parquet')").df()

    ga4_cols = ["sessions_90d", "pageviews_90d", "engaged_sessions_90d", "organic_sessions_90d"]
    features[ga4_cols] = features[ga4_cols].fillna(0)  # SUM() over an all-NULL group returns NULL

    df = features.merge(label, on=["client_hash_id", "content_hash_id"], how="inner")
    df = df.merge(clients, on="client_hash_id", how="left")
    df["impressions_apr"] = df["impressions_apr"].fillna(0)

    # --- min-impressions filter: 50/month in both the March slice and April label month ---
    df = df[(df["impressions_last30"] >= MIN_MONTHLY_IMPRESSIONS) & (df["impressions_apr"] >= MIN_MONTHLY_IMPRESSIONS)].copy()
    # rename the March slice into the leak-tracked name used to build the label
    df = df.rename(columns={"impressions_last30": "impressions_mar"})

    # --- label ---
    df["pct_change"] = (df["impressions_apr"] - df["impressions_mar"]) / df["impressions_mar"]
    df["trend_direction"] = np.where(df["pct_change"] <= -0.30, "down", "up")
    df["trend_pct"] = df["pct_change"] * 100
    df["is_declining_label"] = (df["trend_direction"] == "down").astype(int)

    # restore impressions_last30 as a feature (identical values to impressions_mar, kept
    # under its feature name; impressions_mar itself gets dropped below as a leak column)
    df["impressions_last30"] = df["impressions_mar"]

    # --- derived features ---
    df["ctr_90d"] = np.where(df["impressions_90d"] > 0, df["clicks_90d"] / df["impressions_90d"] * 100, 0.0)
    df["avg_position_90d"] = np.where(
        df["impressions_90d"] > 0,
        np.maximum(df["sum_position_90d"] / df["impressions_90d"], 1.0),
        np.nan,
    )
    df["has_ga4_data"] = df["has_ga4_access"].fillna(False).astype(int)
    df["has_momentum"] = (df["impressions_first60"] > 0).astype(int)

    rate_last30 = df["impressions_last30"] / 30.0
    rate_first60 = df["impressions_first60"] / FIRST60_DAYS
    momentum_pct = np.where(
        df["has_momentum"] == 1,
        (rate_last30 - rate_first60) / rate_first60 * 100,
        0.0,
    )
    p99 = np.percentile(momentum_pct[df["has_momentum"] == 1], 99)
    df["momentum_pct"] = np.minimum(momentum_pct, p99)
    print(f"  momentum_pct 99th percentile cap: {p99:,.1f}%")

    # GA4 columns zero-filled already at source for has_ga4_data=0 rows; drop rows missing position
    df = df.dropna(subset=["avg_position_90d"]).copy()

    feature_cols = [
        "impressions_90d", "clicks_90d", "ctr_90d", "avg_position_90d",
        "sessions_90d", "pageviews_90d", "engaged_sessions_90d",
        "organic_sessions_90d", "impressions_last30", "impressions_first60",
        "momentum_pct", "active_days_90d", "has_ga4_data", "has_momentum",
    ]
    keep = ["client_hash_id", "content_hash_id", "is_declining_label"] + feature_cols
    return df[keep].reset_index(drop=True)


def main() -> None:
    all_months = ["2026-01", "2026-02", "2026-03"]
    df = build(feature_months=all_months, label_months=["2026-04"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_PATH, index=False)

    print(f"\nWrote {OUT_PATH}")
    print(f"Rows: {len(df):,}   Clients: {df['client_hash_id'].nunique()}")
    print(f"Declining: {df['is_declining_label'].sum():,} ({df['is_declining_label'].mean():.1%})")


if __name__ == "__main__":
    main()
