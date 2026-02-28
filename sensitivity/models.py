"""
OptimEngine — Sensitivity Analysis Data Models
Parametric perturbation analysis for scheduling, routing, and packing solvers.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator


class SolverType(str, Enum):
    SCHEDULING = "scheduling"
    ROUTING = "routing"
    PACKING = "packing"


class PerturbationMode(str, Enum):
    PERCENTAGE = "percentage"
    ABSOLUTE = "absolute"


class ParameterSpec(BaseModel):
    """Defines which parameter to perturb and how."""
    parameter_path: str = Field(
        ...,
        description=(
            "Dot-notation path to the parameter to perturb. "
            "Examples: 'jobs[ORDER-001].tasks[mixing].duration', "
            "'locations[customer_A].demand', 'items[laptop].weight', "
            "'vehicles[truck_1].capacity'. Use [id] to target specific entities."
        ),
    )
    perturbations: list[float] = Field(
        default=[-50, -20, -10, 10, 20, 50],
        description="List of perturbation values. Interpreted as % or absolute based on mode.",
    )
    mode: PerturbationMode = Field(
        PerturbationMode.PERCENTAGE,
        description="How to interpret perturbation values: 'percentage' (default) or 'absolute'.",
    )


class SensitivityRequest(BaseModel):
    """
    Sensitivity analysis request.
    Provide the original solver request and specify which parameters to perturb.
    If no parameters are specified, the engine auto-detects critical parameters.
    """
    solver_type: SolverType = Field(..., description="Which solver to analyze: scheduling, routing, or packing.")
    solver_request: dict = Field(..., description="The original solver request as JSON (same schema as the solver endpoint).")
    parameters: list[ParameterSpec] = Field(
        default_factory=list,
        description="Parameters to perturb. If empty, auto-detects critical parameters.",
    )
    max_perturbations_per_param: int = Field(6, ge=2, le=20)
    max_solve_time_seconds: int = Field(10, ge=1, le=60, description="Time limit per individual solve.")


class PerturbationResult(BaseModel):
    """Result of a single perturbation of a single parameter."""
    perturbation_value: float = Field(..., description="The perturbation applied (% or absolute).")
    new_param_value: Any = Field(..., description="The actual parameter value after perturbation.")
    objective_value: float = Field(..., description="Objective metric after perturbation.")
    objective_delta_pct: float = Field(..., description="% change in objective vs baseline.")
    feasible: bool = Field(True, description="Whether the perturbed problem was still feasible.")
    status: str = Field("optimal", description="Solver status for this perturbation.")


class ParameterSensitivity(BaseModel):
    """Sensitivity profile for a single parameter."""
    parameter_path: str
    parameter_name: str = Field(..., description="Human-readable name.")
    baseline_value: Any
    sensitivity_score: float = Field(
        ..., ge=0,
        description="0-100 score. Higher = more sensitive. Computed as max |objective_delta_pct| across perturbations.",
    )
    elasticity: float = Field(
        ...,
        description="Average % change in objective per 1% change in parameter. >1 means amplifying.",
    )
    critical: bool = Field(
        False,
        description="True if any perturbation causes infeasibility or >25% objective change.",
    )
    direction: str = Field(
        "symmetric",
        description="'increase_hurts', 'decrease_hurts', or 'symmetric'.",
    )
    perturbation_results: list[PerturbationResult] = Field(default_factory=list)
    risk_summary: str = Field("", description="Human-readable risk assessment for this parameter.")


class SensitivityMetrics(BaseModel):
    """Aggregate metrics across all analyzed parameters."""
    parameters_analyzed: int = Field(0)
    total_solves: int = Field(0)
    critical_parameters: int = Field(0)
    most_sensitive_parameter: Optional[str] = None
    least_sensitive_parameter: Optional[str] = None
    baseline_objective: float = Field(0)
    baseline_status: str = Field("")
    avg_sensitivity_score: float = Field(0)
    solve_time_seconds: float = Field(0)


class SensitivityResponse(BaseModel):
    """
    Complete sensitivity analysis response.
    Contains baseline results, per-parameter sensitivity profiles,
    risk ranking, and aggregate metrics.
    """
    status: str = Field(..., description="'completed', 'partial', or 'error'.")
    message: str
    baseline_objective: float = Field(0)
    baseline_objective_name: str = Field("", description="Name of the objective metric analyzed.")
    parameters: list[ParameterSensitivity] = Field(default_factory=list)
    risk_ranking: list[str] = Field(
        default_factory=list,
        description="Parameters ranked by sensitivity score, most sensitive first.",
    )
    metrics: Optional[SensitivityMetrics] = None
