from __future__ import annotations

from typing import Any

import httpx


TREND_RADAR_DEMO_SOURCES = [
    {
        "source": "github",
        "items": [
            {
                "title": "agent-eval-runtime",
                "url": "https://github.com/example/agent-eval-runtime",
                "summary": "A runtime for typed agent evals and worker orchestration.",
                "metrics": {"stars": 420},
            }
        ],
    },
    {
        "source": "arxiv",
        "items": [
            {
                "title": "Evaluating Multi-Agent Execution Systems",
                "url": "https://arxiv.org/abs/2605.00001",
                "summary": "Paper about evaluators, contracts, and failure repair in agent systems.",
                "metrics": {"submitted": "2026-05-25"},
            }
        ],
    },
    {
        "source": "huggingface",
        "items": [
            {
                "title": "orchestration-bench",
                "url": "https://huggingface.co/datasets/example/orchestration-bench",
                "summary": "Dataset for testing L2/L3 orchestration and eval loops.",
                "metrics": {"likes": 80},
            }
        ],
    },
]


class LiveApiClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    async def sync_registry(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/registry/sync/yaml")
            response.raise_for_status()
            return response.json()

    async def create_trend_radar_demo(self) -> dict[str, Any]:
        payload = {
            "process_key": "build-in-public-trend-radar",
            "goal": "Find AI/dev trends and produce reviewed build-in-public draft.",
            "inputs": {"sources": TREND_RADAR_DEMO_SOURCES, "channels": ["x"]},
            "require_human_approval": True,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/runs", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_run(self, run_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{self.api_url}/runs/{run_id}")
            response.raise_for_status()
            return response.json()

    async def control(self, run_id: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{self.api_url}/runs/{run_id}/control", json={"action": action, "payload": payload})
            response.raise_for_status()
            return response.json()
