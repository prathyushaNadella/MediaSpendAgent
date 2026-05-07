from __future__ import annotations

import pandas as pd


def estimate_baseline(
    spend_df: pd.DataFrame,
    conversions_df: pd.DataFrame,
    spend_threshold_pct: float = 0.1,
) -> pd.DataFrame:
    """Estimate organic baseline revenue per campaign using low-spend days.

    Strategy:
    - Join spend and conversion data by (date, campaign_id, ad_type)
    - Identify "low-spend" days: days where spend is <= spend_threshold_pct
      of that campaign's median daily spend (or zero-spend days)
    - Average revenue on those days = estimated organic daily revenue
    - If no low-spend days exist, use the minimum-revenue day as proxy

    Returns a DataFrame with columns:
        campaign_id, campaign_name, ad_type, baseline_daily_revenue
    """
    joined = _join_spend_conversions(spend_df, conversions_df)
    if joined.empty:
        return _empty_baseline_df()

    results = []
    for (cid, ad_type), group in joined.groupby(["campaign_id", "ad_type"]):
        campaign_name = group["campaign_name"].iloc[0]
        median_spend = group["spend"].median()
        threshold = median_spend * spend_threshold_pct

        low_spend_days = group[group["spend"] <= threshold]

        if len(low_spend_days) >= 3:
            baseline_daily = low_spend_days["revenue"].mean()
        else:
            baseline_daily = group["revenue"].min()

        baseline_daily = max(baseline_daily, 0.0)

        results.append(
            {
                "campaign_id": cid,
                "campaign_name": campaign_name,
                "ad_type": ad_type,
                "baseline_daily_revenue": baseline_daily,
            }
        )

    return pd.DataFrame(results)


def _join_spend_conversions(
    spend_df: pd.DataFrame, conversions_df: pd.DataFrame
) -> pd.DataFrame:
    if spend_df.empty or conversions_df.empty:
        return pd.DataFrame()

    joined = pd.merge(
        spend_df,
        conversions_df,
        on=["date", "campaign_id", "campaign_name", "ad_type"],
        how="outer",
    )
    joined["spend"] = joined["spend"].fillna(0.0)
    joined["revenue"] = joined["revenue"].fillna(0.0)
    joined["conversions"] = joined["conversions"].fillna(0).astype(int)
    return joined


def _empty_baseline_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["campaign_id", "campaign_name", "ad_type", "baseline_daily_revenue"]
    )
