from __future__ import annotations

import pandas as pd

from media_spend_agent.analytics.baseline import estimate_baseline


def compute_iroas(
    spend_df: pd.DataFrame,
    conversions_df: pd.DataFrame,
    spend_threshold_pct: float = 0.1,
) -> pd.DataFrame:
    """Compute incremental ROAS per campaign and ad type.

    iROAS = (actual_revenue - baseline_revenue) / spend

    Returns a DataFrame with columns:
        campaign_id, campaign_name, ad_type, total_spend, total_revenue,
        baseline_revenue, incremental_revenue, iroas
    """
    if spend_df.empty:
        return _empty_iroas_df()

    baseline_df = estimate_baseline(spend_df, conversions_df, spend_threshold_pct)

    joined = pd.merge(
        spend_df,
        conversions_df,
        on=["date", "campaign_id", "campaign_name", "ad_type"],
        how="outer",
    )
    joined["spend"] = joined["spend"].fillna(0.0)
    joined["revenue"] = joined["revenue"].fillna(0.0)

    agg = (
        joined.groupby(["campaign_id", "campaign_name", "ad_type"])
        .agg(
            total_spend=("spend", "sum"),
            total_revenue=("revenue", "sum"),
            num_days=("date", "nunique"),
        )
        .reset_index()
    )

    agg = agg.merge(baseline_df, on=["campaign_id", "campaign_name", "ad_type"], how="left")
    agg["baseline_daily_revenue"] = agg["baseline_daily_revenue"].fillna(0.0)

    agg["baseline_revenue"] = agg["baseline_daily_revenue"] * agg["num_days"]
    agg["incremental_revenue"] = (agg["total_revenue"] - agg["baseline_revenue"]).clip(lower=0)
    agg["iroas"] = agg.apply(
        lambda r: r["incremental_revenue"] / r["total_spend"] if r["total_spend"] > 0 else 0.0,
        axis=1,
    )

    return agg[
        [
            "campaign_id",
            "campaign_name",
            "ad_type",
            "total_spend",
            "total_revenue",
            "baseline_revenue",
            "incremental_revenue",
            "iroas",
        ]
    ]


def compute_iroas_trend(
    spend_df: pd.DataFrame,
    conversions_df: pd.DataFrame,
    spend_threshold_pct: float = 0.1,
) -> pd.DataFrame:
    """Compute daily iROAS trend across all campaigns."""
    if spend_df.empty:
        return pd.DataFrame(columns=["date", "total_spend", "total_revenue", "iroas"])

    baseline_df = estimate_baseline(spend_df, conversions_df, spend_threshold_pct)

    joined = pd.merge(
        spend_df,
        conversions_df,
        on=["date", "campaign_id", "campaign_name", "ad_type"],
        how="outer",
    )
    joined["spend"] = joined["spend"].fillna(0.0)
    joined["revenue"] = joined["revenue"].fillna(0.0)

    joined = joined.merge(
        baseline_df[["campaign_id", "ad_type", "baseline_daily_revenue"]],
        on=["campaign_id", "ad_type"],
        how="left",
    )
    joined["baseline_daily_revenue"] = joined["baseline_daily_revenue"].fillna(0.0)
    joined["incremental_revenue"] = (
        joined["revenue"] - joined["baseline_daily_revenue"]
    ).clip(lower=0)

    daily = (
        joined.groupby("date")
        .agg(
            total_spend=("spend", "sum"),
            total_revenue=("revenue", "sum"),
            incremental_revenue=("incremental_revenue", "sum"),
        )
        .reset_index()
    )
    daily["iroas"] = daily.apply(
        lambda r: r["incremental_revenue"] / r["total_spend"] if r["total_spend"] > 0 else 0.0,
        axis=1,
    )
    return daily.sort_values("date").reset_index(drop=True)


def _empty_iroas_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "campaign_id",
            "campaign_name",
            "ad_type",
            "total_spend",
            "total_revenue",
            "baseline_revenue",
            "incremental_revenue",
            "iroas",
        ]
    )
