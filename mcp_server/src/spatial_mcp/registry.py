"""Generic tool registry + dispatcher.

Zero biology knowledge: validates args against a JSON schema, invokes a callable,
wraps errors, and logs timing. Individual tools register themselves; the dispatcher
never branches on tool name.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from jsonschema import Draft202012Validator, ValidationError

from spatial_mcp.logging_util import log_tool_call

Handler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler


class ToolValidationError(Exception):
    """Raised when arguments fail schema validation."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class UnknownToolError(Exception):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Duplicate tool registration: {spec.name}")
        # Validate the schema itself is well-formed
        Draft202012Validator.check_schema(spec.input_schema)
        self._tools[spec.name] = spec

    def list_specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise UnknownToolError(f"Unknown tool: {name}")
        return self._tools[name]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Validate, invoke, log. Never lets a handler exception kill the process."""
        arguments = arguments or {}
        t0 = time.perf_counter()
        try:
            spec = self.get(name)
            self._validate(spec, arguments)
            result = spec.handler(arguments)
            duration_ms = (time.perf_counter() - t0) * 1000
            log_tool_call(
                name=name,
                arguments=arguments,
                status="ok",
                duration_ms=duration_ms,
                result=result,
            )
            return result
        except ToolValidationError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            log_tool_call(
                name=name,
                arguments=arguments,
                status="validation_error",
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise
        except UnknownToolError as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            log_tool_call(
                name=name,
                arguments=arguments,
                status="unknown_tool",
                duration_ms=duration_ms,
                error=str(exc),
            )
            raise
        except Exception as exc:  # noqa: BLE001 — isolate teammate tool failures
            duration_ms = (time.perf_counter() - t0) * 1000
            log_tool_call(
                name=name,
                arguments=arguments,
                status="error",
                duration_ms=duration_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def _validate(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        validator = Draft202012Validator(spec.input_schema)
        errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.path))
        if not errors:
            return
        details = []
        for err in errors:
            path = ".".join(str(p) for p in err.path) or "(root)"
            details.append(f"{path}: {err.message}")
        raise ToolValidationError(
            f"Invalid arguments for tool '{spec.name}'",
            details=details,
        )


def build_default_registry() -> ToolRegistry:
    """Assemble all seven tools. Teammates swap stub handlers by editing one file."""
    from spatial_mcp.stubs.list_candidate_cells import list_candidate_cells
    from spatial_mcp.stubs.map_spatial_to_single import map_spatial_to_single
    from spatial_mcp.stubs.search_literature import search_literature
    from spatial_mcp.stubs.suggest_perturbations import suggest_perturbations
    from spatial_mcp.stubs.simulate_perturbations import simulate_perturbations
    from spatial_mcp.memory_tools.record_finding import record_finding
    from spatial_mcp.memory_tools.query_prior_findings import query_prior_findings
    from spatial_mcp import schemas

    registry = ToolRegistry()
    pairs: list[tuple[dict[str, Any], Handler]] = [
        (schemas.LIST_CANDIDATE_CELLS, list_candidate_cells),
        (schemas.MAP_SPATIAL_TO_SINGLE, map_spatial_to_single),
        (schemas.SEARCH_LITERATURE, search_literature),
        (schemas.SUGGEST_PERTURBATIONS, suggest_perturbations),
        (schemas.SIMULATE_PERTURBATIONS, simulate_perturbations),
        (schemas.RECORD_FINDING, record_finding),
        (schemas.QUERY_PRIOR_FINDINGS, query_prior_findings),
    ]
    for meta, handler in pairs:
        registry.register(
            ToolSpec(
                name=meta["name"],
                description=meta["description"],
                input_schema=meta["input_schema"],
                handler=handler,
            )
        )
    return registry
