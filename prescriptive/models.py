"""
OptimEngine — Prescriptive Intelligence Data Models
Forecast + Optimize + Risk-Aware Recommendations.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator


class PrescriptiveSolverType(str, Enum):
    SCHEDULING = "scheduling"
    ROUTING = "routing"
    PACKING = "packing"


class ForecastMethod(str, Enum):
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    LINEAR_TREND = "linear_trend"
    SEASONAL_NAIVE = "seasonal_naive"


class TimeSeriesPoint(BaseModel):
    """A single point in a time series."""
    period: int = Field(..., description="Period index (0, 1, 2, ...). Most recent = highest.")
    value: float = Field(..., description="Observed value for this period.")


class ForecastParameter(BaseModel):
    """
    A parameter whose future value should be forecasted from historical data,
    then injected into the solver request.
    """
    parameter_path: str = Field(
        ...,
        description="Dot-notation path where the forecast value will be injected.",
    )
    historical_data: list[TimeSeriesPoint] = Field(
        ..., min_length=3,
        description="Historical observations. Minimum 3 points. Most recent = highest period.",
    )
    forecast_method: ForecastMethod = Field(
        ForecastMethod.EXPONENTIAL_SMOOTHING,
        description="Forecasting method to use.",
    )
    forecast_horizon: int = Field(
        1, ge=1, le=12,
        description="How many periods ahead to forecast.",
    )
    confidence_level: float = Field(
        0.95, ge=0.5, le=0.99,
        description="Confidence level for prediction interval.",
    )
    smoothing_alpha: Optional[float] = Field(
        None, ge=0.01, le=0.99,
        description="Smoothing factor for exponential smoothing. Auto-detected if omitted.",
    )
    seasonal_period: Optional[int] = Field(
        None, ge=2,
        description="Seasonal period for seasonal_naive method (e.g., 12 for monthly, 7 for weekly).",
    )


class RiskAppetite(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class PrescriptiveRequest(BaseModel):
    """
    Prescriptive intelligence request.
    Provide historical data for uncertain parameters, and the engine will:
    1. Forecast future values
    2. Optimize using forecasted values
    3. Assess risk using prediction intervals
    4. Recommend actions based on risk appetite
    """
    solver_type: PrescriptiveSolverType = Field(..., description="Which solver to use.")
    solver_request: dict = Field(..., description="Base solver request. Forecast values will be injected.")
    forecast_parameters: list[ForecastParameter] = Field(
        ..., min_length=1,
        description="Parameters to forecast from historical data.",
    )
    risk_appetite: RiskAppetite = Field(
        RiskAppetite.MODERATE,
        description=(
            "'conservative': plan for upper bound of prediction interval. "
            "'moderate': plan for forecast point estimate. "
            "'aggressive': plan for lower bound (optimistic)."
        ),
    )
    max_solve_time_seconds: int = Field(10, ge=1, le=60)
    include_risk_analysis: bool = Field(
        True,
        description="If true, also runs sensitivity analysis on forecasted parameters.",
    )


class ForecastResult(BaseModel):
    """Forecast output for a single parameter."""
    parameter_path: str
    method_used: str
    historical_mean: float = 0
    historical_std: float = 0
    forecast_value: float = Field(0, description="Point forecast.")
    lower_bound: float = Field(0, description="Lower prediction interval bound.")
    upper_bound: float = Field(0, description="Upper prediction interval bound.")
    confidence_level: float = 0.95
    trend: str = Field("", description="'increasing', 'decreasing', 'stable', or 'volatile'.")
    trend_strength: float = Field(0, description="Absolute slope of trend line, normalized.")
    forecast_horizon: int = 1


class OptimizationResult(BaseModel):
    """Result of optimizing with forecasted values."""
    objective_name: str = ""
    objective_value: float = 0
    status: str = ""
    parameters_used: dict[str, float] = Field(
        default_factory=dict,
        description="Forecasted parameter values used for optimization.",
    )


class RiskAssessment(BaseModel):
    """Risk analysis of the prescriptive recommendation."""
    conservative_objective: float = Field(0, description="Objective if planning for upper bound.")
    moderate_objective: float = Field(0, description="Objective with point forecast.")
    aggressive_objective: float = Field(0, description="Objective if planning for lower bound.")
    sensitivity_summary: str = Field("", description="Which forecasted parameters are most critical.")
    feasibility_risk: str = Field(
        "",
        description="'low': all scenarios feasible. 'medium': some infeasible. 'high': most infeasible.",
    )


class Action(BaseModel):
    """A specific recommended action."""
    priority: int = Field(1, description="1 = highest priority.")
    action: str = Field(..., description="What to do.")
    reason: str = Field(..., description="Why this action matters.")
    impact: str = Field("", description="Expected impact.")


class PrescriptiveResponse(BaseModel):
    """
    Complete prescriptive intelligence response.
    Forecast + Optimization + Risk + Actionable Recommendations.
    """
    status: str = Field(..., description="'completed' or 'error'.")
    message: str
    forecasts: list[ForecastResult] = Field(default_factory=list)
    optimization: Optional[OptimizationResult] = None
    risk: Optional[RiskAssessment] = None
    actions: list[Action] = Field(default_factory=list)
    recommendation: str = Field("", description="Executive summary recommendation.")
    solve_time_seconds: float = 0
