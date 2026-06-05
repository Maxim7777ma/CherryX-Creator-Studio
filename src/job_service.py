from __future__ import annotations

from types import ModuleType
from typing import Any

from . import web_actions


class JobService:
    """Thin contract boundary for Django views and background job actions."""

    def __init__(self, actions: ModuleType = web_actions) -> None:
        self._actions = actions

    def __getattr__(self, name: str) -> Any:
        return getattr(self._actions, name)

    def native_status(self) -> dict[str, object]:
        return self._actions.native_status()


job_service = JobService()
