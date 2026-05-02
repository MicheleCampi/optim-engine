"""
Random bin packing problem generator for load testing.

Three size classes calibrated for OptimEngine on Railway:
  - small:  ~50-200ms solve time, mostly OPTIMAL
  - medium: ~1-3s solve time, mix OPTIMAL/FEASIBLE
  - large:  ~5-15s solve time, mostly FEASIBLE/TIMEOUT (intentional)

Items/bins ratio controlled via fill_ratio (~0.75 by default) — feasible
by construction. Items have weight + value (knapsack-style); bins have
weight_capacity. Volume dimension omitted for now (added in v2 if needed).
"""
import random
from typing import Literal

SizeClass = Literal["small", "medium", "large"]

_SIZE_CONFIG = {
    "small":  {"items": (5, 10),   "bins": (2, 3),  "max_time": 5},
    "medium": {"items": (20, 40),  "bins": (4, 7),  "max_time": 10},
    "large":  {"items": (60, 120), "bins": (8, 15), "max_time": 20},
}

_FILL_RATIO = 0.75  # total item weight / total bin capacity


def random_packing(size_class: SizeClass = "small") -> dict:
    """
    Build a randomized but feasible bin packing problem.

    Returns a dict matching PackingRequest schema. Always feasible by
    construction (sum of item weights ≈ 0.75 * sum of bin capacities).
    """
    cfg = _SIZE_CONFIG[size_class]

    num_bins = random.randint(*cfg["bins"])
    bin_capacities = [random.randint(20, 80) for _ in range(num_bins)]
    total_capacity = sum(bin_capacities)
    bins = [
        {"bin_id": f"B{i+1}", "weight_capacity": cap}
        for i, cap in enumerate(bin_capacities)
    ]

    num_items = random.randint(*cfg["items"])
    target_weight = total_capacity * _FILL_RATIO
    avg_weight = max(1, int(target_weight / num_items))

    items = []
    for i in range(num_items):
        weight = max(1, random.randint(
            max(1, avg_weight // 2),
            max(2, avg_weight + avg_weight // 2),
        ))
        # Value loosely correlated with weight (knapsack-like) plus noise
        value = max(1, int(weight * random.uniform(0.8, 1.5)))
        items.append({
            "item_id": f"I{i+1}",
            "weight": weight,
            "value": value,
        })

    return {
        "items": items,
        "bins": bins,
        "max_solve_time_seconds": cfg["max_time"],
    }
