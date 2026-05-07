import pandas as pd

from media_spend_agent.analytics.baseline import estimate_baseline


def _make_spend(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["spend"] = df["spend"].astype(float)
    return df


def _make_conversions(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["conversions"] = df["conversions"].astype(int)
    df["revenue"] = df["revenue"].astype(float)
    return df


def test_baseline_from_zero_spend_days():
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
            {"date": "2024-01-05", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 2, "revenue": 50},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 3, "revenue": 60},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 40},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 10, "revenue": 300},
            {"date": "2024-01-05", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 12, "revenue": 350},
        ]
    )

    result = estimate_baseline(spend, conversions)
    assert len(result) == 1
    assert result.iloc[0]["campaign_id"] == "c1"
    baseline = result.iloc[0]["baseline_daily_revenue"]
    assert baseline == 50.0  # mean of (50, 60, 40) for the 3 zero-spend days


def test_baseline_fallback_to_min_revenue():
    """When fewer than 3 low-spend days, use min revenue as baseline."""
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 5, "revenue": 200},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 8, "revenue": 300},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 3, "revenue": 150},
        ]
    )

    result = estimate_baseline(spend, conversions)
    baseline = result.iloc[0]["baseline_daily_revenue"]
    assert baseline == 150.0  # min revenue day


def test_baseline_empty_data():
    spend = pd.DataFrame(columns=["date", "campaign_id", "campaign_name", "ad_type", "spend"])
    conversions = pd.DataFrame(
        columns=["date", "campaign_id", "campaign_name", "ad_type", "conversions", "revenue"]
    )
    result = estimate_baseline(spend, conversions)
    assert result.empty


def test_baseline_never_negative():
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 0, "revenue": 0},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 0, "revenue": 0},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 0, "revenue": 0},
        ]
    )
    result = estimate_baseline(spend, conversions)
    assert result.iloc[0]["baseline_daily_revenue"] >= 0
