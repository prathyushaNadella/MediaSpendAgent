from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BudgetRecommendation:
    campaign_id: str
    campaign_name: str
    ad_type: str
    current_spend: float
    iroas: float
    action: str  # CUT, MAINTAIN, SCALE
    suggested_change_pct: float
    suggested_spend: float
    reasoning: str


IROAS_CUT_THRESHOLD = 1.0
IROAS_SCALE_THRESHOLD = 2.0
MAX_SCALE_INCREASE_PCT = 0.30


def generate_recommendations(iroas_df: pd.DataFrame) -> list[BudgetRecommendation]:
    """Generate budget reallocation recommendations from iROAS results."""
    if iroas_df.empty:
        return []

    recommendations: list[BudgetRecommendation] = []

    for _, row in iroas_df.iterrows():
        iroas = row["iroas"]
        spend = row["total_spend"]

        if iroas < IROAS_CUT_THRESHOLD:
            action = "CUT"
            change_pct = -0.50
            reasoning = (
                f"iROAS of {iroas:.2f} is below 1.0 — each dollar spent generates "
                f"only ${iroas:.2f} in incremental revenue. Recommend cutting 50% of budget."
            )
        elif iroas < IROAS_SCALE_THRESHOLD:
            action = "MAINTAIN"
            change_pct = 0.0
            reasoning = (
                f"iROAS of {iroas:.2f} is marginally positive. "
                f"Monitor closely and optimize creative/targeting before scaling."
            )
        else:
            action = "SCALE"
            change_pct = min(MAX_SCALE_INCREASE_PCT, (iroas - IROAS_SCALE_THRESHOLD) * 0.10)
            reasoning = (
                f"iROAS of {iroas:.2f} shows strong incremental return. "
                f"Recommend increasing budget by {change_pct:.0%}."
            )

        recommendations.append(
            BudgetRecommendation(
                campaign_id=row["campaign_id"],
                campaign_name=row["campaign_name"],
                ad_type=row["ad_type"],
                current_spend=spend,
                iroas=iroas,
                action=action,
                suggested_change_pct=change_pct,
                suggested_spend=spend * (1 + change_pct),
                reasoning=reasoning,
            )
        )

    recommendations.sort(key=lambda r: (-_action_priority(r.action), -r.iroas))
    return recommendations


def summarize_reallocation(recommendations: list[BudgetRecommendation]) -> dict:
    """Summarize total budget reallocation across all recommendations."""
    total_current = sum(r.current_spend for r in recommendations)
    total_suggested = sum(r.suggested_spend for r in recommendations)
    freed = sum(
        r.current_spend - r.suggested_spend for r in recommendations if r.action == "CUT"
    )
    added = sum(
        r.suggested_spend - r.current_spend for r in recommendations if r.action == "SCALE"
    )
    return {
        "total_current_spend": total_current,
        "total_suggested_spend": total_suggested,
        "budget_freed_from_cuts": freed,
        "budget_added_to_scale": added,
        "net_change": total_suggested - total_current,
        "num_cut": sum(1 for r in recommendations if r.action == "CUT"),
        "num_maintain": sum(1 for r in recommendations if r.action == "MAINTAIN"),
        "num_scale": sum(1 for r in recommendations if r.action == "SCALE"),
    }


def _action_priority(action: str) -> int:
    return {"SCALE": 3, "MAINTAIN": 2, "CUT": 1}.get(action, 0)
