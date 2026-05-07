import pandas as pd

from media_spend_agent.analytics.recommendations import (
    generate_recommendations,
    summarize_reallocation,
)


def _make_iroas_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_recommendations_cut_maintain_scale():
    iroas_df = _make_iroas_df(
        [
            {
                "campaign_id": "c1",
                "campaign_name": "LowPerf",
                "ad_type": "SP",
                "total_spend": 1000,
                "total_revenue": 500,
                "baseline_revenue": 200,
                "incremental_revenue": 300,
                "iroas": 0.3,
            },
            {
                "campaign_id": "c2",
                "campaign_name": "MidPerf",
                "ad_type": "SB",
                "total_spend": 1000,
                "total_revenue": 2000,
                "baseline_revenue": 500,
                "incremental_revenue": 1500,
                "iroas": 1.5,
            },
            {
                "campaign_id": "c3",
                "campaign_name": "HighPerf",
                "ad_type": "SD",
                "total_spend": 1000,
                "total_revenue": 5000,
                "baseline_revenue": 200,
                "incremental_revenue": 4800,
                "iroas": 4.8,
            },
        ]
    )

    recs = generate_recommendations(iroas_df)
    assert len(recs) == 3

    actions = {r.campaign_id: r.action for r in recs}
    assert actions["c1"] == "CUT"
    assert actions["c2"] == "MAINTAIN"
    assert actions["c3"] == "SCALE"


def test_cut_reduces_spend():
    iroas_df = _make_iroas_df(
        [
            {
                "campaign_id": "c1",
                "campaign_name": "Bad",
                "ad_type": "SP",
                "total_spend": 1000,
                "total_revenue": 200,
                "baseline_revenue": 100,
                "incremental_revenue": 100,
                "iroas": 0.1,
            },
        ]
    )
    recs = generate_recommendations(iroas_df)
    assert recs[0].suggested_spend < recs[0].current_spend


def test_scale_increases_spend_with_cap():
    iroas_df = _make_iroas_df(
        [
            {
                "campaign_id": "c1",
                "campaign_name": "Great",
                "ad_type": "SP",
                "total_spend": 1000,
                "total_revenue": 50000,
                "baseline_revenue": 100,
                "incremental_revenue": 49900,
                "iroas": 49.9,
            },
        ]
    )
    recs = generate_recommendations(iroas_df)
    assert recs[0].action == "SCALE"
    # Max increase capped at 30%
    assert recs[0].suggested_change_pct <= 0.30
    assert recs[0].suggested_spend <= 1300


def test_maintain_no_change():
    iroas_df = _make_iroas_df(
        [
            {
                "campaign_id": "c1",
                "campaign_name": "Mid",
                "ad_type": "SP",
                "total_spend": 1000,
                "total_revenue": 2500,
                "baseline_revenue": 500,
                "incremental_revenue": 1500,
                "iroas": 1.5,
            },
        ]
    )
    recs = generate_recommendations(iroas_df)
    assert recs[0].suggested_change_pct == 0.0
    assert recs[0].suggested_spend == 1000


def test_summarize_reallocation():
    iroas_df = _make_iroas_df(
        [
            {"campaign_id": "c1", "campaign_name": "Bad", "ad_type": "SP", "total_spend": 1000, "total_revenue": 200, "baseline_revenue": 100, "incremental_revenue": 100, "iroas": 0.1},
            {"campaign_id": "c2", "campaign_name": "Good", "ad_type": "SD", "total_spend": 1000, "total_revenue": 5000, "baseline_revenue": 200, "incremental_revenue": 4800, "iroas": 4.8},
        ]
    )
    recs = generate_recommendations(iroas_df)
    summary = summarize_reallocation(recs)

    assert summary["num_cut"] == 1
    assert summary["num_scale"] == 1
    assert summary["budget_freed_from_cuts"] > 0
    assert summary["budget_added_to_scale"] > 0


def test_empty_recommendations():
    iroas_df = pd.DataFrame(
        columns=[
            "campaign_id", "campaign_name", "ad_type", "total_spend",
            "total_revenue", "baseline_revenue", "incremental_revenue", "iroas",
        ]
    )
    recs = generate_recommendations(iroas_df)
    assert recs == []
