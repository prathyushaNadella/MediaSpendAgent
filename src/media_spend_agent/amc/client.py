from __future__ import annotations

import time

import httpx

from media_spend_agent.config import Settings


class AMCClient:
    """Handles OAuth and query execution against Amazon Marketing Cloud."""

    TOKEN_URL = "https://api.amazon.com/auth/o2/token"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0
        self._http = httpx.Client(timeout=60)

    def _refresh_access_token(self) -> None:
        resp = self._http.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self._settings.amc_client_id,
                "client_secret": self._settings.amc_client_secret,
                "refresh_token": self._settings.amc_refresh_token,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 3600) - 60

    def _ensure_token(self) -> str:
        if self._access_token is None or time.time() >= self._token_expires_at:
            self._refresh_access_token()
        assert self._access_token is not None
        return self._access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._ensure_token()}",
            "Amazon-Advertising-API-ClientId": self._settings.amc_client_id,
            "Amazon-Advertising-API-Scope": self._settings.amc_advertiser_id,
            "Content-Type": "application/json",
        }

    def _base_url(self) -> str:
        return (
            f"{self._settings.amc_base_url}/{self._settings.amc_api_version}"
            f"/amc/instances/{self._settings.amc_instance_id}"
        )

    def create_workflow(self, sql: str, workflow_id: str) -> dict:
        url = f"{self._base_url()}/workflows"
        payload = {
            "workflowId": workflow_id,
            "sqlQuery": sql,
        }
        resp = self._http.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        return resp.json()

    def execute_workflow(self, workflow_id: str, start_date: str, end_date: str) -> dict:
        url = f"{self._base_url()}/workflows/{workflow_id}/executions"
        payload = {
            "timeWindowStart": start_date,
            "timeWindowEnd": end_date,
        }
        resp = self._http.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_execution_status(self, workflow_id: str, execution_id: str) -> dict:
        url = f"{self._base_url()}/workflows/{workflow_id}/executions/{execution_id}"
        resp = self._http.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def poll_execution(
        self, workflow_id: str, execution_id: str, max_wait: int = 300, interval: int = 10
    ) -> dict:
        """Poll until execution completes or times out."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            status = self.get_execution_status(workflow_id, execution_id)
            state = status.get("status", "")
            if state == "SUCCEEDED":
                return status
            if state in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"AMC workflow {workflow_id} execution {state}: {status}")
            time.sleep(interval)
        raise TimeoutError(f"AMC workflow {workflow_id} did not complete within {max_wait}s")

    def get_execution_result(self, workflow_id: str, execution_id: str) -> dict:
        url = f"{self._base_url()}/workflows/{workflow_id}/executions/{execution_id}/result"
        resp = self._http.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._http.close()
