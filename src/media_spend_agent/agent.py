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
and generate budget recommendations. Use them to answer questions.

When presenting results:
- Format numbers as currency ($X,XXX.XX) or percentages where appropriate
- Always explain what iROAS means in context \
(e.g., "For every $1 spent, you earned $X.XX incrementally")
- Be direct with recommendations — marketing managers want clear actions
- If data is missing or insufficient, say so honestly

Recommendation thresholds:
- iROAS < 1.0 → CUT (losing money)
- 1.0 ≤ iROAS < 2.0 → MAINTAIN (marginal, optimize before scaling)
- iROAS ≥ 2.0 → SCALE (strong return, increase budget)
"""

TOOLS = [
    {
        "name": "get_iroas",
        "description": (
            "Compute incremental ROAS for campaigns in a date range. "
            "Returns iROAS per campaign and ad type."
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
            "Generate budget reallocation recommendations based on iROAS analysis. "
            "Returns per-campaign actions (CUT/MAINTAIN/SCALE) with suggested budget changes."
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

        while response.stop_reason == "tool_use":
            tool_results = []
            assistant_content = response.content

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

            self._messages.append({"role": "assistant", "content": assistant_content})
            self._messages.append({"role": "user", "content": tool_results})

            response = self._anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
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
                return {
                    "recommendations": [asdict(r) for r in recs],
                    "summary": summary,
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
