from __future__ import annotations

from typing import Any, Dict

import requests


class CalendarMeetingSchedulerClient:
    """Minimal HTTP client for the calendar meeting scheduler environment."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def reset(self, task_id: str, seed: int | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"task_id": task_id, "seed": seed}
        resp = requests.post(f"{self.base_url}/reset", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def step(self, task_id: str, action: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"task_id": task_id, "action": action}
        resp = requests.post(f"{self.base_url}/step", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def state(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/state", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def tasks(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.base_url}/tasks", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def baseline(self) -> Dict[str, Any]:
        resp = requests.post(f"{self.base_url}/baseline", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def grader(self, task_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        payload = {"task_id": task_id, "state": state}
        resp = requests.post(f"{self.base_url}/grader", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()

