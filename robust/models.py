"""
OptimEngine — Robust Optimization Data Models
Worst-case optimization under parameter uncertainty.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator


class RobustSolverType(str, Enum):
    SCHEDULING = "scheduling"
    ROUTING = "routing"
    PACKING = "packing"


class UncertainParameter(BaseModel):
    """A parameter with uncertain range."""
    parameter_path: str = Field(
        ...,
        description=(
            "Dot-notation path to the uncertain parameter. "
            "Same syntax as sensitivity analysis."
        ),
    )
    min_value: float = Field(..., description="Minimum plausible value (best case or lower bound).")
    max_value: float = Field(..., description="Maximum plausible value (worst case or upper bound).")
    nominal_value: Optional[float] = Field(
        None,
        description="Nominal/expected value. If omitted, uses the value from the solver request.",
    )

    @model_validator(mode="after")
    def validate_range(self):
        if self.min_value > self.max_value:
            raise ValueError(f"min_value ({self.min_value}) > max_value ({self.max_value})")
        return self


class RobustMode(str, Enum):
    WORST_CASE = "worst_case"
    PERCENTILE_90 = "percentile_90"
    PERCENTILE_95 = "percentile_95"
    REGRET_MINIMIZATION = "regret_minimization"


class RobustRequest(BaseModel):
    """
    Robust optimization request.
    Provide the solver request, uncertain parameters with ranges,
    and the engine will find a solution that protects against worst-case outcomes.
    """
    solver_type: RobustSolverType = Field(..., description="Which solver: scheduling, routing, or packing.")
    solver_request: dict = Field(..., description="The original solver request as JSON.")
    uncertain_parameters: list[UncertainParameter] = Field(
        ..., min_length=1,
        description="Parameters with uncertainty ranges.",
    )
    mode: RobustMode = Field(
        RobustMode.WORST_CASE,
        description=(
            "Robustness mode. 'worst_case': optimize for the worst scenario. "
            "'percentile_90/95': optimize for the 90th/95th percentile scenario. "
            "'regret_minimization': minimize the gap between robust and nominal solution."
        ),
    )
    num_scenarios: int = Field(
        20, ge=5, le=100,
        description="Number of scenarios to generate for evaluating robustness.",
    )
    max_solve_time_seconds: int = Field(10, ge=1, le=60, description="Time limit per individual solve.")


class ScenarioResult(BaseModel):
    """Result of solving one scenario."""
    scenario_id: int
    parameter_values: dict[str, float] = Field(
        default_factory=dict,
        description="Parameter values used in this scenario.",
    )
    objective_value: float
    feasible: bool
    status: str
    is_worst_case: bool = False
    is_nominal: bool = False


class RobustSolution(BaseModel):
    """The recommended robust solution."""
    objective_value: float = Field(..., description="Objective value of the robust solution.")
    scenario_used: str = Field("", description="Which scenario produced this solution.")
    parameter_values: dict[str, float] = Field(
        default_factory=dict,
        description="Parameter values of the scenario used for the robust solution.",
    )


class RobustMetrics(BaseModel):
    """Aggregate metrics for robust analysis."""
    nominal_objective: float = Field(0, description="Objective with nominal/original values.")
    worst_case_objective: float = Field(0, description="Objective in worst-case scenario.")
    best_case_objective: float = Field(0, description="Objective in best-case scenario.")
    robust_objective: float = Field(0, description="Objective of the recommended robust solution.")
    price_of_robustness_pct: float = Field(
        0,
        description="% degradation from nominal to robust. The 'cost' of being safe.",
    )
    feasibility_rate_pct: float = Field(
        0,
        description="% of scenarios that remained feasible.",
    )
    scenarios_evaluated: int = 0
    total_solves: int = 0
    solve_time_seconds: float = 0
    percentile_90_objective: float = Field(0, description="90th percentile objective value.")
    percentile_95_objective: float = Field(0, description="95th percentile objective value.")
    objective_std_dev: float = Field(0, description="Standard deviation of objectives across scenarios.")


class RobustResponse(BaseModel):
    """
    Complete robust optimization response.
    Contains the recommended robust solution, scenario analysis,
    and metrics including the price of robustness.
    """
    status: str = Field(..., description="'completed', 'partial', or 'error'.")
    message: str
    objective_name: str = Field("", description="Name of the objective metric.")
    robust_solution: Optional[RobustSolution] = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    metrics: Optional[RobustMetrics] = None
    recommendation: str = Field(
        "",
        description="Human-readable recommendation based on the analysis.",
    )
