"""Async HTTP client for DOGMA layouts-filter API."""

from __future__ import annotations

from typing import Any

import httpx


class DogmaClientError(Exception):
    """Raised when DOGMA HTTP request fails."""


class DogmaClient:
    """HTTP-only client for DOGMA JSON API. No DB access."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30,
        page_limit: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._page_limit = page_limit
        self._client = client
        self._owns_client = client is None

    @property
    def page_limit(self) -> int:
        return self._page_limit

    async def __aenter__(self) -> DogmaClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
            self._owns_client = True
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("DogmaClient is not started; use 'async with' or pass a client")
        return self._client

    async def fetch_objects_page(self, *, offset: int, limit: int | None = None) -> dict[str, Any]:
        """POST /v4/objects/filter with sync filters and pagination offset."""
        page_limit = self._page_limit if limit is None else limit
        payload = {
            "type": 1,
            "statuses": [2],
            "limit": page_limit,
            "offset": offset,
            "group_by": "",
        }
        return await self._post_json("/v4/objects/filter", payload)

    async def fetch_projects(self) -> dict[str, Any]:
        """POST /v4/projects/config — list of residential complexes."""
        return await self._post_json("/v4/projects/config", {})

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._require_client()
        url = f"{self._base_url}{path}"
        try:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise DogmaClientError(f"DOGMA request failed: {exc}") from exc
        except ValueError as exc:
            raise DogmaClientError(f"DOGMA returned invalid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise DogmaClientError("DOGMA response root must be an object")
        return data
