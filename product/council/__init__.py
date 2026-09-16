"""Deterministic orchestration shell for an LLM-led portfolio council."""

from .orchestrator import CouncilOrchestrator, CouncilRunResult
from .output import NO_TRADE_REASONS, validate_final_plan
from .risk_adapter import DeterministicRiskAdapter
from .trace import build_council_trace
from .intake_planning import (
    CouncilPlanningError,
    build_common_stock_council_request,
    build_multidimensional_holding_research_request,
    build_council_request,
    build_research_plan,
    validate_council_request,
    validate_research_plan,
)
from .common_stock_research import (
    BoundedResearchDispatch,
    CommonStockResearchError,
    build_holding_research_requests,
    build_cio_equity_research_input,
    build_initial_research_coverage,
    build_retry_request,
    envelope_equity_research_draft,
    parallel_intervals_overlap,
    prepare_common_stock_research_stage,
    validate_equity_research_report,
    validate_holding_research_request,
    validate_research_coverage,
)
from .research_output import (
    persist_equity_research_report,
    render_equity_research_markdown,
    render_research_progress,
    validate_persisted_equity_research_pair,
)
from .multidimensional_research import (
    BUNDLE_CAPABILITIES,
    RESEARCH_CAPABILITIES,
    MultiDimensionalResearchError,
    finalize_holding_research_bundle,
    finalize_research_dimension_report,
    envelope_research_dimension_draft,
    validate_holding_research_bundle,
    validate_research_dimension_report,
)
from .research_schedule import DependencyResearchScheduler, ResearchScheduleError
from .multidimensional_output import (
    persist_dimension_report,
    render_dimension_report_markdown,
    render_holding_research_bundle_markdown,
)

__all__ = [
    "CouncilOrchestrator",
    "CouncilRunResult",
    "DeterministicRiskAdapter",
    "NO_TRADE_REASONS",
    "build_council_trace",
    "validate_final_plan",
    "CouncilPlanningError",
    "build_common_stock_council_request",
    "build_multidimensional_holding_research_request",
    "build_council_request",
    "build_research_plan",
    "validate_council_request",
    "validate_research_plan",
    "CommonStockResearchError",
    "BoundedResearchDispatch",
    "build_cio_equity_research_input",
    "build_holding_research_requests",
    "build_initial_research_coverage",
    "build_retry_request",
    "envelope_equity_research_draft",
    "parallel_intervals_overlap",
    "prepare_common_stock_research_stage",
    "validate_equity_research_report",
    "validate_holding_research_request",
    "validate_research_coverage",
    "persist_equity_research_report",
    "render_equity_research_markdown",
    "render_research_progress",
    "validate_persisted_equity_research_pair",
    "BUNDLE_CAPABILITIES",
    "RESEARCH_CAPABILITIES",
    "MultiDimensionalResearchError",
    "finalize_holding_research_bundle",
    "finalize_research_dimension_report",
    "envelope_research_dimension_draft",
    "validate_holding_research_bundle",
    "validate_research_dimension_report",
    "DependencyResearchScheduler",
    "ResearchScheduleError",
    "persist_dimension_report",
    "render_dimension_report_markdown",
    "render_holding_research_bundle_markdown",
]
