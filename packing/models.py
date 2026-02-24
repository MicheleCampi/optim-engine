"""
OptimEngine — Bin Packing Data Models
Pydantic schemas for multi-dimensional bin packing with optional value maximization.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class PackingObjective(str, Enum):
    MINIMIZE_BINS = "minimize_bins"
    MAXIMIZE_VALUE = "maximize_value"
    MAXIMIZE_ITEMS = "maximize_items"
    BALANCE_LOAD = "balance_load"


class PackingStatus(str, Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    NO_SOLUTION = "no_solution"
    TIMEOUT = "timeout"
    ERROR = "error"


class Item(BaseModel):
    item_id: str = Field(..., description="Unique item identifier")
    name: Optional[str] = Field(None, description="Human-readable name")
    weight: int = Field(..., gt=0, description="Weight in weight units")
    volume: int = Field(0, ge=0, description="Volume in volume units (0 = ignore volume)")
    value: int = Field(1, ge=0, description="Value/priority for maximize_value objective")
    quantity: int = Field(1, ge=1, le=1000, description="Number of copies of this item")
    fragile: bool = Field(False, description="If True, cannot be stacked under other items")
    group: Optional[str] = Field(None, description="Group label for keeping related items together")


class Bin(BaseModel):
    bin_id: str = Field(..., description="Unique bin/container identifier")
    name: Optional[str] = Field(None, description="Human-readable name")
    weight_capacity: int = Field(..., gt=0, description="Maximum weight capacity")
    volume_capacity: int = Field(0, ge=0, description="Maximum volume capacity (0 = ignore)")
    max_items: Optional[int] = Field(None, ge=1, description="Max items per bin. None = no limit.")
    cost: int = Field(1, ge=0, description="Cost of using this bin (for minimize_bins)")
    quantity: int = Field(1, ge=1, le=100, description="Number of available copies of this bin type")


class PackingRequest(BaseModel):
    """
    Complete bin packing request.
    Send items with weight/volume and bins with capacity.
    The solver assigns items to bins optimally, minimizing bins used
    or maximizing total value packed, while respecting all constraints.
    """
    items: list[Item] = Field(..., min_length=1, max_length=1000)
    bins: list[Bin] = Field(..., min_length=1, max_length=100)
    objective: PackingObjective = Field(PackingObjective.MINIMIZE_BINS)
    max_solve_time_seconds: int = Field(30, ge=1, le=300)
    allow_partial: bool = Field(
        False, description="If True, solver can leave items unpacked when capacity is insufficient."
    )
    keep_groups_together: bool = Field(
        False, description="If True, items with same group label must go in the same bin."
    )

    @field_validator("items")
    @classmethod
    def validate_unique_item_ids(cls, v):
        ids = [item.item_id for item in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate item_id found")
        return v

    @field_validator("bins")
    @classmethod
    def validate_unique_bin_ids(cls, v):
        ids = [b.bin_id for b in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate bin_id found")
        return v


class PackedItem(BaseModel):
    item_id: str
    name: Optional[str] = None
    bin_id: str
    bin_name: Optional[str] = None
    weight: int
    volume: int
    value: int


class BinSummary(BaseModel):
    bin_id: str
    name: Optional[str] = None
    is_used: bool = False
    items_packed: int = Field(0, ge=0)
    weight_used: int = Field(0, ge=0)
    weight_capacity: int = Field(0, ge=0)
    weight_utilization_pct: float = Field(0, ge=0, le=100)
    volume_used: int = Field(0, ge=0)
    volume_capacity: int = Field(0, ge=0)
    volume_utilization_pct: float = Field(0, ge=0, le=100)
    total_value: int = Field(0, ge=0)
    item_ids: list[str] = Field(default_factory=list)


class PackingMetrics(BaseModel):
    bins_used: int = Field(0)
    bins_available: int = Field(0)
    items_packed: int = Field(0)
    items_unpacked: int = Field(0)
    unpacked_item_ids: list[str] = Field(default_factory=list)
    total_value_packed: int = Field(0)
    total_weight_packed: int = Field(0)
    total_volume_packed: int = Field(0)
    avg_weight_utilization_pct: float = Field(0)
    avg_volume_utilization_pct: float = Field(0)
    total_bin_cost: int = Field(0)
    solve_time_seconds: float = Field(...)


class PackingResponse(BaseModel):
    """
    Complete bin packing solver response.
    Contains item-to-bin assignments, per-bin summaries,
    and aggregate metrics.
    """
    status: PackingStatus
    message: str = Field(..., description="Human-readable status message")
    assignments: list[PackedItem] = Field(default_factory=list)
    bin_summaries: list[BinSummary] = Field(default_factory=list)
    metrics: Optional[PackingMetrics] = None
    unpacked_items: list[str] = Field(default_factory=list)
