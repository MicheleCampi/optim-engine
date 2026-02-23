"""
OptimEngine — Routing Data Models
Pydantic schemas for the CVRPTW (Capacitated Vehicle Routing Problem with Time Windows).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class RoutingObjective(str, Enum):
    MINIMIZE_TOTAL_DISTANCE = "minimize_total_distance"
    MINIMIZE_TOTAL_TIME = "minimize_total_time"
    MINIMIZE_VEHICLES = "minimize_vehicles"
    BALANCE_ROUTES = "balance_routes"


class RoutingStatus(str, Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    NO_SOLUTION = "no_solution"
    TIMEOUT = "timeout"
    ERROR = "error"


class Location(BaseModel):
    location_id: str = Field(..., description="Unique location identifier")
    name: Optional[str] = Field(None, description="Human-readable name")
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    demand: int = Field(0, ge=0, description="Demand units to deliver")
    service_time: int = Field(0, ge=0, description="Time spent at location for service")
    time_window_start: int = Field(0, ge=0, description="Earliest arrival time")
    time_window_end: Optional[int] = Field(None, ge=0, description="Latest arrival time")
    pickup: int = Field(0, ge=0, description="Units to pick up")


class Vehicle(BaseModel):
    vehicle_id: str = Field(..., description="Unique vehicle identifier")
    name: Optional[str] = Field(None)
    capacity: int = Field(..., gt=0, description="Maximum load capacity")
    start_location: Optional[str] = Field(None)
    end_location: Optional[str] = Field(None)
    max_travel_time: Optional[int] = Field(None, ge=0)
    max_travel_distance: Optional[int] = Field(None, ge=0)
    cost_per_distance: int = Field(1, ge=0)
    cost_per_time: int = Field(0, ge=0)
    fixed_cost: int = Field(0, ge=0)


class DistanceEntry(BaseModel):
    from_id: str = Field(..., description="Source location ID")
    to_id: str = Field(..., description="Destination location ID")
    distance: int = Field(..., ge=0)
    travel_time: Optional[int] = Field(None, ge=0)


class RoutingRequest(BaseModel):
    """
    Complete vehicle routing request.
    Send a depot, locations to visit, vehicles with capacity, and optionally
    a custom distance/time matrix. The solver assigns locations to vehicle
    routes and determines visit order to minimize the chosen objective
    while respecting capacity and time window constraints.
    """
    depot_id: str = Field(..., description="Location ID of the depot")
    locations: list[Location] = Field(..., min_length=1, max_length=1000)
    vehicles: list[Vehicle] = Field(..., min_length=1, max_length=100)
    distance_matrix: Optional[list[DistanceEntry]] = Field(None)
    objective: RoutingObjective = Field(RoutingObjective.MINIMIZE_TOTAL_DISTANCE)
    max_solve_time_seconds: int = Field(30, ge=1, le=300)
    allow_drop_visits: bool = Field(False, description="Allow skipping infeasible locations")
    drop_penalty: int = Field(10000, ge=0)

    @field_validator("locations")
    @classmethod
    def validate_unique_location_ids(cls, v):
        ids = [loc.location_id for loc in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate location_id found")
        return v

    @field_validator("vehicles")
    @classmethod
    def validate_unique_vehicle_ids(cls, v):
        ids = [veh.vehicle_id for veh in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate vehicle_id found")
        return v


class RouteStop(BaseModel):
    location_id: str
    name: Optional[str] = None
    arrival_time: int = Field(..., ge=0)
    departure_time: int = Field(..., ge=0)
    load_after: int = Field(..., ge=0)
    demand_served: int = Field(0, ge=0)
    wait_time: int = Field(0, ge=0)


class VehicleRoute(BaseModel):
    vehicle_id: str
    name: Optional[str] = None
    stops: list[RouteStop] = Field(default_factory=list)
    total_distance: int = Field(0, ge=0)
    total_time: int = Field(0, ge=0)
    total_load: int = Field(0, ge=0)
    num_stops: int = Field(0, ge=0)
    is_used: bool = Field(False)


class RoutingMetrics(BaseModel):
    total_distance: int = Field(0)
    total_time: int = Field(0)
    total_demand_served: int = Field(0)
    vehicles_used: int = Field(0)
    vehicles_available: int = Field(0)
    locations_served: int = Field(0)
    locations_dropped: int = Field(0)
    dropped_location_ids: list[str] = Field(default_factory=list)
    avg_route_distance: float = Field(0)
    avg_route_load_pct: float = Field(0)
    max_route_distance: int = Field(0)
    max_route_time: int = Field(0)
    solve_time_seconds: float = Field(...)


class RoutingResponse(BaseModel):
    """
    Complete routing solver response.
    Contains optimized routes per vehicle, aggregate metrics,
    and solver diagnostics.
    """
    status: RoutingStatus
    message: str = Field(..., description="Human-readable status message")
    routes: list[VehicleRoute] = Field(default_factory=list)
    metrics: Optional[RoutingMetrics] = None
    dropped_locations: list[str] = Field(default_factory=list)
