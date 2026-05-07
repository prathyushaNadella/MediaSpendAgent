from __future__ import annotations

import uuid

import pandas as pd

from media_spend_agent.amc.client import AMCClient

SPEND_SQL = """
SELECT
    date_format(impression_dt, 'yyyy-MM-dd') AS date,
    campaign_id,
    campaign_name,
    ad_product AS ad_type,
    SUM(cost) AS spend
FROM amazon_attributed_events_by_traffic_time
WHERE impression_dt BETWEEN CAST('{start_date}' AS DATE) AND CAST('{end_date}' AS DATE)
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2
"""

WORKFLOW_ID_PREFIX = "msa_spend_"


def fetch_spend(client: AMCClient, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch daily spend by campaign from AMC."""
    workflow_id = f"{WORKFLOW_ID_PREFIX}{uuid.uuid4().hex[:8]}"
    sql = SPEND_SQL.format(start_date=start_date, end_date=end_date)

    client.create_workflow(sql, workflow_id)
    execution = client.execute_workflow(workflow_id, start_date, end_date)
    execution_id = execution["executionId"]

    client.poll_execution(workflow_id, execution_id)
    result = client.get_execution_result(workflow_id, execution_id)

    rows = result.get("rows", [])
    if not rows:
        return _empty_spend_df()

    columns = [col["name"] for col in result.get("columns", [])]
    df = pd.DataFrame(rows, columns=columns)
    df["date"] = pd.to_datetime(df["date"])
    df["spend"] = df["spend"].astype(float)
    return df


def _empty_spend_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "campaign_id", "campaign_name", "ad_type", "spend"])
