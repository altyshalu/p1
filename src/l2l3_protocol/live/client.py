from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

API_TIMEOUT_SECONDS = 60


class LiveApiClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip('/')

    async def sync_registry(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.api_url}/hub/sync/yaml")
            response.raise_for_status()
            return response.json()

    async def create_trend_radar_run(
        self,
        *,
        goal: str,
        query: str,
        providers: list[str],
        channels: list[str],
        max_results: int,
    ) -> dict[str, Any]:
        payload = {
            'playbook_key': 'build-in-public-trend-radar',
            'l2_mode': 'execution',
            'goal': goal,
            'inputs': {'query': query, 'providers': providers, 'channels': channels, 'max_results': max_results},
            'require_human_approval': True,
        }
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.api_url}/runs", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.api_url}/runs/{run_id}")
            response.raise_for_status()
            return response.json()

    async def control(self, run_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.api_url}/runs/{run_id}/control", json={'action': action, 'payload': payload})
            response.raise_for_status()
            return response.json()

    async def send_message(self, run_id: str, message: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.api_url}/runs/{run_id}/messages", json={'message': message})
            response.raise_for_status()
            return response.json()

    async def create_recent_system_review(
        self,
        *,
        limit: int = 50,
        playbook_key: str | None = None,
        since_hours: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {'limit': limit}
        if playbook_key is not None:
            payload['playbook_key'] = playbook_key
        if since_hours is not None:
            payload['since_hours'] = since_hours
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{self.api_url}/system-reviews/recent", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_system_learning_report(self, *, playbook_key: str | None = None, since_hours: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if playbook_key is not None:
            params['playbook_key'] = playbook_key
        if since_hours is not None:
            params['since_hours'] = since_hours
        query = f"?{urlencode(params)}" if params else ''
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.api_url}/reports/system-learning{query}")
            response.raise_for_status()
            return response.json()

    async def list_regression_cases(self, *, playbook_key: str | None = None) -> list[dict[str, Any]]:
        params = {'playbook_key': playbook_key} if playbook_key is not None else {}
        query = f"?{urlencode(params)}" if params else ''
        async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{self.api_url}/regression-cases{query}")
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else []
