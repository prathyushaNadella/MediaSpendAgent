import pandas as pd

from media_spend_agent.analytics.iroas import compute_iroas, compute_iroas_trend


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


def test_iroas_basic_calculation():
    """With zero-spend baseline days, iROAS should reflect incremental revenue."""
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
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 10, "revenue": 500},
            {"date": "2024-01-05", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 10, "revenue": 500},
        ]
    )

    result = compute_iroas(spend, conversions)
    assert len(result) == 1
    row = result.iloc[0]

    # baseline_daily = mean(50,50,50) = 50, over 5 days = 250
    # total_revenue = 1150, incremental = 1150-250 = 900
    # total_spend = 200, iROAS = 900/200 = 4.5
    assert row["total_spend"] == 200.0
    assert row["total_revenue"] == 1150.0
    assert row["baseline_revenue"] == 250.0
    assert row["incremental_revenue"] == 900.0
    assert row["iroas"] == 4.5


def test_iroas_zero_spend_returns_zero():
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 5, "revenue": 100},
        ]
    )
    result = compute_iroas(spend, conversions)
    assert result.iloc[0]["iroas"] == 0.0


def test_iroas_empty_data():
    spend = pd.DataFrame(columns=["date", "campaign_id", "campaign_name", "ad_type", "spend"])
    conversions = pd.DataFrame(
        columns=["date", "campaign_id", "campaign_name", "ad_type", "conversions", "revenue"]
    )
    result = compute_iroas(spend, conversions)
    assert result.empty


def test_iroas_multiple_campaigns():
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
            {"date": "2024-01-01", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "spend": 0},
            {"date": "2024-01-02", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "spend": 0},
            {"date": "2024-01-03", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "spend": 0},
            {"date": "2024-01-04", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "spend": 200},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 10},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 10},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 10},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 5, "revenue": 200},
            {"date": "2024-01-01", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "conversions": 2, "revenue": 20},
            {"date": "2024-01-02", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "conversions": 2, "revenue": 20},
            {"date": "2024-01-03", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "conversions": 2, "revenue": 20},
            {"date": "2024-01-04", "campaign_id": "c2", "campaign_name": "Camp2", "ad_type": "SD", "conversions": 3, "revenue": 50},
        ]
    )

    result = compute_iroas(spend, conversions)
    assert len(result) == 2


def test_iroas_trend():
    spend = _make_spend(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 0},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "spend": 100},
        ]
    )
    conversions = _make_conversions(
        [
            {"date": "2024-01-01", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-02", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-03", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 1, "revenue": 50},
            {"date": "2024-01-04", "campaign_id": "c1", "campaign_name": "Camp1", "ad_type": "SP", "conversions": 10, "revenue": 400},
        ]
    )

    trend = compute_iroas_trend(spend, conversions)
    assert len(trend) == 4
    assert "iroas" in trend.columns
    # Day 4: spend=100, revenue=400, baseline=50, incremental=350, iROAS=3.5
    day4 = trend[trend["date"] == pd.Timestamp("2024-01-04")].iloc[0]
    assert day4["iroas"] == 3.5
