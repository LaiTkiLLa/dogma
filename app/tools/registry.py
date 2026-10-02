"""Registry of backend tools available to the agent."""

from __future__ import annotations

from collections.abc import Mapping

from app.apartments.search_service import SearchService
from app.llm.types import ToolDefinition
from app.tools.search_apartments import SearchApartmentsTool


def build_tool_registry(search_service: SearchService) -> dict[str, SearchApartmentsTool]:
    """Create the MVP tool map (only `search_apartments`)."""
    tool = SearchApartmentsTool(search_service)
    return {tool.name: tool}


def get_tool(
    registry: Mapping[str, SearchApartmentsTool],
    name: str,
) -> SearchApartmentsTool:
    try:
        return registry[name]
    except KeyError as exc:
        raise KeyError(f"unknown tool: {name}") from exc


def list_tool_definitions(
    registry: Mapping[str, SearchApartmentsTool],
) -> list[ToolDefinition]:
    return [tool.definition() for tool in registry.values()]
