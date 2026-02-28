"""
OptimEngine — Multi-objective Pareto Optimization Data Models
Generate the Pareto frontier: the set of non-dominated trade-off solutions.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class ParetoSolverType(str, Enum):
    SCHEDULING = "scheduling"
    ROUTING = "routing"
    PACKING = "packing"


class ObjectiveSpec(BaseModel):
    """Specification of one objective to optimize."""
    name: str = Field(
        ...,
        description=(
            "Objective name. For scheduling: 'minimize_makespan', 'minimize_total_tardiness', "
            "'minimize_total_completion_time', 'maximize_machine_utilization'. "
            "For routing: 'minimize_total_distance', 'minimize_num_vehicles', "
            "'minimize_longest_route', 'minimize_total_time'. "
            "For packing: 'minimize_bins', 'maximize_items', 'maximize_value', 'minimize_waste'."
        ),
    )
    weight: float = Field(
        1.0, ge=0.0, le=100.0,
        description="Relative importance weight (used for weighted-sum scalarization). Higher = more important.",
    )


class ParetoRequest(BaseModel):
    """
    Multi-objective Pareto optimization request.
    Specify 2+ objectives and the engine will find the Pareto frontier —
    the set of solutions where no objective can be improved without degrading another.
    """
    solver_type: ParetoSolverType = Field(..., description="Which solver to use.")
    solver_request: dict = Field(..., description="The solver request as JSON (without 'objective' field).")
    objectives: list[ObjectiveSpec] = Field(
        ..., min_length=2, max_length=4,
        description="2-4 objectives to trade off.",
    )
    num_points: int = Field(
        10, ge=3, le=50,
        description="Number of points to generate on the Pareto frontier.",
    )
    max_solve_time_seconds: int = Field(10, ge=1, le=60, description="Time limit per individual solve.")


class ParetoPoint(BaseModel):
    """A single point on the Pareto frontier."""
    point_id: int
    objectives: dict[str, float] = Field(
        default_factory=dict,
        description="Objective name → value for this solution.",
    )
    weights_used: dict[str, float] = Field(
        default_factory=dict,
        description="Weights used to generate this point.",
    )
    feasible: bool = True
    status: str = ""
    is_extreme: bool = Field(False, description="True if this point optimizes a single objective.")
    is_balanced: bool = Field(False, description="True if this is the equal-weight balanced solution.")


class TradeOff(BaseModel):
    """Trade-off analysis between two objectives."""
    objective_a: str
    objective_b: str
    correlation: float = Field(
        0,
        description="Correlation coefficient. Negative = trade-off (improving A worsens B). Positive = synergy.",
    )
    trade_off_ratio: float = Field(
        0,
        description="Average units of B sacrificed per unit of A gained.",
    )
    relationship: str = Field(
        "",
        description="'conflict', 'synergy', or 'independent'.",
    )


class ParetoMetrics(BaseModel):
    """Aggregate metrics for the Pareto analysis."""
    points_generated: int = 0
    points_feasible: int = 0
    points_on_frontier: int = 0
    total_solves: int = 0
    solve_time_seconds: float = 0
    spread: dict[str, float] = Field(
        default_factory=dict,
        description="Range (max - min) for each objective on the frontier.",
    )


class ParetoResponse(BaseModel):
    """
    Complete multi-objective Pareto optimization response.
    Contains the Pareto frontier points, trade-off analysis, and recommendations.
    """
    status: str = Field(..., description="'completed', 'partial', or 'error'.")
    message: str
    frontier: list[ParetoPoint] = Field(default_factory=list)
    trade_offs: list[TradeOff] = Field(default_factory=list)
    metrics: Optional[ParetoMetrics] = None
    recommendation: str = Field("", description="Human-readable trade-off recommendation.")
