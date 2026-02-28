"""
OptimEngine — Stochastic Optimization Data Models
Monte Carlo scenario sampling with probabilistic risk metrics (CVaR, VaR).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator


class StochasticSolverType(str, Enum):
    SCHEDULING = "scheduling"
    ROUTING = "routing"
    PACKING = "packing"


class DistributionType(str, Enum):
    NORMAL = "normal"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    LOG_NORMAL = "log_normal"


class StochasticParameter(BaseModel):
    """A parameter with a probability distribution."""
    parameter_path: str = Field(
        ...,
        description="Dot-notation path to the uncertain parameter.",
    )
    distribution: DistributionType = Field(
        DistributionType.NORMAL,
        description="Probability distribution type.",
    )
    mean: Optional[float] = Field(
        None,
        description="Mean value. For normal/log_normal. If omitted, uses value from solver request.",
    )
    std_dev: Optional[float] = Field(
        None,
        description="Standard deviation. Required for normal/log_normal.",
    )
    min_value: Optional[float] = Field(
        None,
        description="Minimum value. For uniform (lower bound) or triangular (min).",
    )
    max_value: Optional[float] = Field(
        None,
        description="Maximum value. For uniform (upper bound) or triangular (max).",
    )
    mode_value: Optional[float] = Field(
        None,
        description="Mode (peak) value. For triangular distribution.",
    )

    @model_validator(mode="after")
    def validate_distribution_params(self):
        d = self.distribution
        if d == DistributionType.NORMAL:
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError("Normal distribution requires std_dev > 0")
        elif d == DistributionType.UNIFORM:
            if self.min_value is None or self.max_value is None:
                raise ValueError("Uniform distribution requires min_value and max_value")
            if self.min_value > self.max_value:
                raise ValueError("min_value must be <= max_value")
        elif d == DistributionType.TRIANGULAR:
            if self.min_value is None or self.max_value is None or self.mode_value is None:
                raise ValueError("Triangular distribution requires min_value, max_value, and mode_value")
            if not (self.min_value <= self.mode_value <= self.max_value):
                raise ValueError("Triangular requires min_value <= mode_value <= max_value")
        elif d == DistributionType.LOG_NORMAL:
            if self.std_dev is None or self.std_dev <= 0:
                raise ValueError("Log-normal distribution requires std_dev > 0")
        return self


class RiskMetric(str, Enum):
    EXPECTED_VALUE = "expected_value"
    CVAR_90 = "cvar_90"
    CVAR_95 = "cvar_95"
    CVAR_99 = "cvar_99"
    WORST_CASE = "worst_case"


class StochasticRequest(BaseModel):
    """
    Stochastic optimization request.
    Provide the solver request, parameters with probability distributions,
    and the engine will run Monte Carlo simulation to produce risk-aware solutions.
    """
    solver_type: StochasticSolverType = Field(..., description="Which solver to use.")
    solver_request: dict = Field(..., description="The original solver request as JSON.")
    stochastic_parameters: list[StochasticParameter] = Field(
        ..., min_length=1,
        description="Parameters with probability distributions.",
    )
    optimize_for: RiskMetric = Field(
        RiskMetric.CVAR_95,
        description=(
            "Which risk metric to optimize. 'expected_value': average outcome. "
            "'cvar_90/95/99': Conditional Value at Risk (average of worst X% outcomes). "
            "'worst_case': optimize for the single worst outcome."
        ),
    )
    num_scenarios: int = Field(
        50, ge=10, le=500,
        description="Number of Monte Carlo scenarios to generate.",
    )
    max_solve_time_seconds: int = Field(10, ge=1, le=60, description="Time limit per individual solve.")
    seed: int = Field(42, description="Random seed for reproducibility.")


class ScenarioOutcome(BaseModel):
    """Result of one Monte Carlo scenario."""
    scenario_id: int
    parameter_values: dict[str, float] = Field(default_factory=dict)
    objective_value: float
    feasible: bool
    status: str


class DistributionSummary(BaseModel):
    """Statistical summary of the outcome distribution."""
    mean: float = 0
    median: float = 0
    std_dev: float = 0
    min_value: float = 0
    max_value: float = 0
    percentile_5: float = 0
    percentile_10: float = 0
    percentile_25: float = 0
    percentile_75: float = 0
    percentile_90: float = 0
    percentile_95: float = 0
    percentile_99: float = 0
    skewness: float = Field(0, description="Positive = tail toward worse outcomes.")
    coefficient_of_variation: float = Field(0, description="Std dev / mean. Higher = more variable.")


class RiskAnalysis(BaseModel):
    """Risk metrics for the objective distribution."""
    expected_value: float = Field(0, description="Mean objective across all scenarios.")
    var_90: float = Field(0, description="Value at Risk 90%: 90th percentile objective.")
    var_95: float = Field(0, description="Value at Risk 95%: 95th percentile objective.")
    var_99: float = Field(0, description="Value at Risk 99%: 99th percentile objective.")
    cvar_90: float = Field(0, description="Conditional VaR 90%: average of worst 10% outcomes.")
    cvar_95: float = Field(0, description="Conditional VaR 95%: average of worst 5% outcomes.")
    cvar_99: float = Field(0, description="Conditional VaR 99%: average of worst 1% outcomes.")
    worst_case: float = Field(0, description="Single worst feasible outcome.")
    best_case: float = Field(0, description="Single best feasible outcome.")
    probability_of_infeasibility: float = Field(0, description="% of scenarios that are infeasible.")


class StochasticMetrics(BaseModel):
    """Aggregate metrics for the stochastic analysis."""
    scenarios_generated: int = 0
    scenarios_feasible: int = 0
    scenarios_infeasible: int = 0
    total_solves: int = 0
    solve_time_seconds: float = 0
    optimized_for: str = ""


class StochasticResponse(BaseModel):
    """
    Complete stochastic optimization response.
    Contains Monte Carlo outcomes, distribution summary, risk analysis,
    and a recommended solution with risk-aware metrics.
    """
    status: str = Field(..., description="'completed', 'partial', or 'error'.")
    message: str
    objective_name: str = Field("")
    recommended_objective: float = Field(
        0,
        description="The objective value optimized for the chosen risk metric.",
    )
    recommended_scenario: Optional[ScenarioOutcome] = None
    distribution: Optional[DistributionSummary] = None
    risk: Optional[RiskAnalysis] = None
    scenarios: list[ScenarioOutcome] = Field(default_factory=list)
    metrics: Optional[StochasticMetrics] = None
    recommendation: str = Field("", description="Human-readable risk assessment and recommendation.")
