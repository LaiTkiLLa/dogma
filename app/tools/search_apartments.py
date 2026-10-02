"""`search_apartments` tool — validates args and delegates to SearchService."""

from __future__ import annotations

from app.apartments.schemas import ApartmentSearchFilters, ApartmentSearchResult
from app.apartments.search_service import SearchService
from app.llm.types import ToolDefinition
from app.tools.schemas import SearchApartmentsArgs

TOOL_NAME = "search_apartments"

TOOL_DESCRIPTION = (
    "Ищет активные квартиры DOGMA в каталоге по цене, площади, числу комнат и ЖК. "
    "Возвращает подходящие варианты, отсортированные по цене и площади."
)


def build_search_apartments_tool_definition() -> ToolDefinition:
    """JSON Schema definition exposed to DeepSeek for tool calling."""
    schema = SearchApartmentsArgs.model_json_schema()
    parameters = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "additionalProperties": False,
    }
    required = schema.get("required")
    if required:
        parameters["required"] = required
    return ToolDefinition(
        name=TOOL_NAME,
        description=TOOL_DESCRIPTION,
        parameters=parameters,
    )


class SearchApartmentsTool:
    """Backend tool used by the agent; no SQL / DOGMA / DeepSeek access."""

    name = TOOL_NAME
    description = TOOL_DESCRIPTION
    args_model = SearchApartmentsArgs

    def __init__(self, search_service: SearchService) -> None:
        self._search_service = search_service

    def definition(self) -> ToolDefinition:
        return build_search_apartments_tool_definition()

    async def execute(self, args: SearchApartmentsArgs | dict) -> ApartmentSearchResult:
        parsed = (
            args
            if isinstance(args, SearchApartmentsArgs)
            else SearchApartmentsArgs.model_validate(args)
        )
        filters = ApartmentSearchFilters.model_validate(parsed.model_dump())
        return await self._search_service.search(filters)
