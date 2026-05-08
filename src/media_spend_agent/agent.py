from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, timedelta

import pandas as pd
from anthropic import Anthropic

from media_spend_agent.amc.client import AMCClient
from media_spend_agent.amc.conversions import fetch_conversions
from media_spend_agent.amc.spend import fetch_spend
from media_spend_agent.analytics.iroas import compute_iroas, compute_iroas_trend
from media_spend_agent.analytics.recommendations import (
    generate_recommendations,
    summarize_reallocation,
)
from media_spend_agent.config import Settings

SYSTEM_PROMPT = """\
You are a Media Spend Analyst agent. You help marketing managers understand their \
incremental ROAS (iROAS) from Amazon Marketing Cloud campaigns and make budget decisions.

You have access to tools that fetch spend and conversion data from AMC, compute iROAS, \
and generate budget recommendations. Use them to gather data, then reason about it.

## How to respond after tool calls

Tools return raw computed data. Your job is to turn that data into insight. \
After every tool result, you MUST:

1. **Synthesize, don't just format** — interpret what the numbers mean for the business, \
not just display them in a table. Explain the "why" behind each recommendation.
2. **Compare campaigns against each other** — which is the top performer? Which is the \
biggest drag on portfolio efficiency? Name them explicitly.
3. **Prioritize actions** — lead with the most urgent item (biggest CUT or highest SCALE \
opportunity). Marketing managers want to know what to do first.
4. **Quantify the opportunity** — if reallocating budget from CUT to SCALE campaigns, \
state the expected revenue impact in dollars.
5. **Explain iROAS in plain terms** — always include: \
"For every $1 spent on [campaign], you generated $X.XX in incremental revenue."
6. **Flag anomalies** — low baseline means iROAS could be overstated; \
high spend with low iROAS is the most urgent problem.
7. **End with a clear next step** — one specific action the manager should take today.

## Formatting rules

- Format numbers as currency ($X,XXX.XX) or percentages (XX.X%) — never raw floats
- Use campaign names, not IDs
- If data is missing or insufficient, say so and suggest what data would help

## Recommendation thresholds

- iROAS < 1.0 → CUT (destroying value — spend exceeds incremental revenue)
- 1.0 ≤ iROAS < 2.0 → MAINTAIN (marginal — optimize before scaling)
- iROAS ≥ 2.0 → SCALE (strong return — increase budget, capped at +30%)
"""

TOOLS = [
    {
        "name": "get_iroas",
        "description": (
            "Compute incremental ROAS for campaigns in a date range. "
            "Returns raw iROAS numbers per campaign and ad type — you must then reason about "
            "which campaigns are strong/weak, compare them, and explain the business implications."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_spend_summary",
        "description": "Get a summary of ad spend broken down by campaign and ad type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_recommendations",
        "description": (
            "Generate structured budget reallocation data based on iROAS analysis. "
            "Returns per-campaign actions (CUT/MAINTAIN/SCALE) and suggested budget numbers. "
            "After receiving this data, synthesize it into a strategic narrative: prioritize the "
            "most urgent actions, explain why each recommendation matters, quantify the revenue "
            "opportunity from reallocation, and tell the manager exactly what to do first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_trends",
        "description": "Get daily iROAS trend over a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
]


class MediaSpendAgent:
    def __init__(self, settings: Settings, amc_client: AMCClient | None = None) -> None:
        self._settings = settings
        self._anthropic = Anthropic(api_key=settings.anthropic_api_key)
        self._amc_client = amc_client
        self._messages: list[dict] = []
        self._spend_cache: dict[str, pd.DataFrame] = {}
        self._conversions_cache: dict[str, pd.DataFrame] = {}

    def chat(self, user_message: str) -> str:
        self._messages.append({"role": "user", "content": user_message})

        response = self._anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=self._messages,
        )

        # Phase 1: data-gathering loop — execute all tool calls
        tools_were_called = False
        while response.stop_reason == "tool_use":
            tools_were_called = True
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    result = self._handle_tool_call(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        }
                    )

            self._messages.append({"role": "assistant", "content": response.content})
            self._messages.append({"role": "user", "content": tool_results})

            response = self._anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self._messages,
            )

        # Phase 2: reasoning pass — if data was fetched, make a dedicated analysis call
        # WITHOUT tools so Claude must synthesize rather than call more tools or format output
        if tools_were_called:
            self._messages.append({"role": "assistant", "content": response.content})
            response = self._anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=self._messages,
            )

        final_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                final_text += block.text

        self._messages.append({"role": "assistant", "content": response.content})
        return final_text

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        try:
            start = tool_input["start_date"]
            end = tool_input["end_date"]

            spend_df = self._get_spend(start, end)
            conversions_df = self._get_conversions(start, end)

            if tool_name == "get_iroas":
                result = compute_iroas(spend_df, conversions_df)
                return {"iroas_by_campaign": result.to_dict(orient="records")}

            elif tool_name == "get_spend_summary":
                summary = (
                    spend_df.groupby(["campaign_name", "ad_type"])
                    .agg(total_spend=("spend", "sum"), days=("date", "nunique"))
                    .reset_index()
                )
                return {"spend_summary": summary.to_dict(orient="records")}

            elif tool_name == "get_recommendations":
                iroas_df = compute_iroas(spend_df, conversions_df)
                recs = generate_recommendations(iroas_df)
                summary = summarize_reallocation(recs)
                top_scale = max(
                    (r for r in recs if r.action == "SCALE"), key=lambda r: r.iroas, default=None
                )
                top_cut = min(
                    (r for r in recs if r.action == "CUT"), key=lambda r: r.iroas, default=None
                )
                return {
                    "recommendations": [asdict(r) for r in recs],
                    "summary": summary,
                    "analysis_hints": {
                        "highest_iroas_campaign": (
                            f"{top_scale.campaign_name} ({top_scale.ad_type}), "
                            f"iROAS={top_scale.iroas:.2f}"
                        ) if top_scale else None,
                        "lowest_iroas_campaign": (
                            f"{top_cut.campaign_name} ({top_cut.ad_type}), "
                            f"iROAS={top_cut.iroas:.2f}"
                        ) if top_cut else None,
                        "reallocation_opportunity": (
                            f"Cutting underperformers frees "
                            f"${summary['budget_freed_from_cuts']:,.2f} "
                            f"that can be redeployed to top performers "
                            f"(currently capped at "
                            f"${summary['budget_added_to_scale']:,.2f} increase)"
                        ),
                    },
                }

            elif tool_name == "get_trends":
                trend = compute_iroas_trend(spend_df, conversions_df)
                return {"daily_trend": trend.to_dict(orient="records")}

            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"error": str(e)}

    def _get_spend(self, start_date: str, end_date: str) -> pd.DataFrame:
        cache_key = f"{start_date}_{end_date}"
        if cache_key not in self._spend_cache:
            if self._amc_client is None:
                raise RuntimeError("AMC client not configured. Set AMC credentials in .env")
            self._spend_cache[cache_key] = fetch_spend(self._amc_client, start_date, end_date)
        return self._spend_cache[cache_key]

    def _get_conversions(self, start_date: str, end_date: str) -> pd.DataFrame:
        cache_key = f"{start_date}_{end_date}"
        if cache_key not in self._conversions_cache:
            if self._amc_client is None:
                raise RuntimeError("AMC client not configured. Set AMC credentials in .env")
            self._conversions_cache[cache_key] = fetch_conversions(
                self._amc_client, start_date, end_date
            )
        return self._conversions_cache[cache_key]


def _default_date_range() -> tuple[str, str]:
    today = date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()
