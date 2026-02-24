"""
OptimEngine — Bin Packing Solver
Multi-dimensional bin packing via OR-Tools CP-SAT.

Supports:
  - Weight and volume constraints
  - Multiple bin types with different capacities
  - Item quantities (multiple copies)
  - Value maximization or bin minimization
  - Group constraints (keep related items together)
  - Partial packing for over-constrained problems
"""

import time
from ortools.sat.python import cp_model

from .models import (
    PackingRequest, PackingResponse, PackingStatus, PackingObjective,
    PackedItem, BinSummary, PackingMetrics,
)


def _expand_items(request: PackingRequest) -> list[dict]:
    """Expand items with quantity > 1 into individual items."""
    expanded = []
    for item in request.items:
        for q in range(item.quantity):
            suffix = f"_{q}" if item.quantity > 1 else ""
            expanded.append({
                "item_id": f"{item.item_id}{suffix}",
                "original_id": item.item_id,
                "name": item.name,
                "weight": item.weight,
                "volume": item.volume,
                "value": item.value,
                "group": item.group,
            })
    return expanded


def _expand_bins(request: PackingRequest) -> list[dict]:
    """Expand bins with quantity > 1 into individual bins."""
    expanded = []
    for b in request.bins:
        for q in range(b.quantity):
            suffix = f"_{q}" if b.quantity > 1 else ""
            expanded.append({
                "bin_id": f"{b.bin_id}{suffix}",
                "original_id": b.bin_id,
                "name": b.name,
                "weight_capacity": b.weight_capacity,
                "volume_capacity": b.volume_capacity,
                "max_items": b.max_items,
                "cost": b.cost,
            })
    return expanded


def solve_packing(request: PackingRequest) -> PackingResponse:
    """Solve a bin packing problem using OR-Tools CP-SAT."""
    t0 = time.time()

    try:
        items = _expand_items(request)
        bins = _expand_bins(request)
        n_items = len(items)
        n_bins = len(bins)

        if n_items == 0:
            return PackingResponse(
                status=PackingStatus.ERROR,
                message="No items to pack."
            )
        if n_bins == 0:
            return PackingResponse(
                status=PackingStatus.ERROR,
                message="No bins available."
            )

        model = cp_model.CpModel()

        # ── Variables ──
        # x[i][j] = 1 if item i is assigned to bin j
        x = {}
        for i in range(n_items):
            for j in range(n_bins):
                x[(i, j)] = model.new_bool_var(f"x_{i}_{j}")

        # y[j] = 1 if bin j is used
        y = {}
        for j in range(n_bins):
            y[j] = model.new_bool_var(f"y_{j}")

        # packed[i] = 1 if item i is packed (for partial packing)
        packed = {}
        for i in range(n_items):
            packed[i] = model.new_bool_var(f"packed_{i}")

        # ── Constraints ──

        # Each item assigned to at most one bin
        for i in range(n_items):
            bin_assignments = [x[(i, j)] for j in range(n_bins)]
            model.add(sum(bin_assignments) == packed[i])

        # If not allowing partial packing, all items must be packed
        if not request.allow_partial:
            for i in range(n_items):
                model.add(packed[i] == 1)

        # Weight capacity per bin
        for j in range(n_bins):
            model.add(
                sum(items[i]["weight"] * x[(i, j)] for i in range(n_items))
                <= bins[j]["weight_capacity"]
            )

        # Volume capacity per bin (if specified)
        for j in range(n_bins):
            if bins[j]["volume_capacity"] > 0:
                model.add(
                    sum(items[i]["volume"] * x[(i, j)] for i in range(n_items))
                    <= bins[j]["volume_capacity"]
                )

        # Max items per bin (if specified)
        for j in range(n_bins):
            if bins[j]["max_items"] is not None:
                model.add(
                    sum(x[(i, j)] for i in range(n_items))
                    <= bins[j]["max_items"]
                )

        # Link y[j] to x: if any item in bin j, y[j] = 1
        for j in range(n_bins):
            for i in range(n_items):
                model.add(y[j] >= x[(i, j)])
            model.add(y[j] <= sum(x[(i, j)] for i in range(n_items)))

        # Group constraints: items with same group go to same bin
        if request.keep_groups_together:
            groups = {}
            for i, item in enumerate(items):
                if item["group"]:
                    groups.setdefault(item["group"], []).append(i)

            for group_name, group_items in groups.items():
                if len(group_items) > 1:
                    first = group_items[0]
                    for other in group_items[1:]:
                        for j in range(n_bins):
                            model.add(x[(first, j)] == x[(other, j)])

        # ── Objective ──
        if request.objective == PackingObjective.MINIMIZE_BINS:
            model.minimize(sum(bins[j]["cost"] * y[j] for j in range(n_bins)))

        elif request.objective == PackingObjective.MAXIMIZE_VALUE:
            model.maximize(
                sum(items[i]["value"] * packed[i] for i in range(n_items))
            )

        elif request.objective == PackingObjective.MAXIMIZE_ITEMS:
            model.maximize(sum(packed[i] for i in range(n_items)))

        elif request.objective == PackingObjective.BALANCE_LOAD:
            # Minimize max weight utilization across used bins
            max_load = model.new_int_var(0, max(b["weight_capacity"] for b in bins) * 100, "max_load")
            for j in range(n_bins):
                cap = bins[j]["weight_capacity"]
                if cap > 0:
                    load_pct = model.new_int_var(0, 10000, f"load_pct_{j}")
                    total_weight = sum(items[i]["weight"] * x[(i, j)] for i in range(n_items))
                    model.add(load_pct * cap == total_weight * 100).only_enforce_if(y[j])
                    model.add(load_pct == 0).only_enforce_if(y[j].Not())
                    model.add(max_load >= load_pct)
            model.minimize(max_load)

        # ── Solve ──
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = request.max_solve_time_seconds
        solver.parameters.num_workers = 4
        solver.parameters.log_search_progress = False

        status = solver.solve(model)
        solve_time = time.time() - t0

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            solver_status = PackingStatus.OPTIMAL if status == cp_model.OPTIMAL else PackingStatus.FEASIBLE

            # Extract assignments
            assignments = []
            bin_items = {j: [] for j in range(n_bins)}

            for i in range(n_items):
                for j in range(n_bins):
                    if solver.value(x[(i, j)]) == 1:
                        assignments.append(PackedItem(
                            item_id=items[i]["original_id"],
                            name=items[i]["name"],
                            bin_id=bins[j]["original_id"],
                            bin_name=bins[j]["name"],
                            weight=items[i]["weight"],
                            volume=items[i]["volume"],
                            value=items[i]["value"],
                        ))
                        bin_items[j].append(i)
                        break

            # Unpacked items
            unpacked = []
            for i in range(n_items):
                if solver.value(packed[i]) == 0:
                    unpacked.append(items[i]["original_id"])

            # Bin summaries
            bin_summaries = []
            total_bin_cost = 0
            weight_utils = []
            volume_utils = []

            for j in range(n_bins):
                is_used = solver.value(y[j]) == 1
                packed_indices = bin_items[j]
                w_used = sum(items[i]["weight"] for i in packed_indices)
                v_used = sum(items[i]["volume"] for i in packed_indices)
                val = sum(items[i]["value"] for i in packed_indices)
                w_cap = bins[j]["weight_capacity"]
                v_cap = bins[j]["volume_capacity"]
                w_pct = round(w_used / w_cap * 100, 1) if w_cap > 0 else 0
                v_pct = round(v_used / v_cap * 100, 1) if v_cap > 0 else 0

                if is_used:
                    total_bin_cost += bins[j]["cost"]
                    weight_utils.append(w_pct)
                    if v_cap > 0:
                        volume_utils.append(v_pct)

                bin_summaries.append(BinSummary(
                    bin_id=bins[j]["original_id"],
                    name=bins[j]["name"],
                    is_used=is_used,
                    items_packed=len(packed_indices),
                    weight_used=w_used,
                    weight_capacity=w_cap,
                    weight_utilization_pct=w_pct,
                    volume_used=v_used,
                    volume_capacity=v_cap,
                    volume_utilization_pct=v_pct,
                    total_value=val,
                    item_ids=[items[i]["original_id"] for i in packed_indices],
                ))

            n_used = sum(1 for s in bin_summaries if s.is_used)
            metrics = PackingMetrics(
                bins_used=n_used,
                bins_available=n_bins,
                items_packed=len(assignments),
                items_unpacked=len(unpacked),
                unpacked_item_ids=unpacked,
                total_value_packed=sum(a.value for a in assignments),
                total_weight_packed=sum(a.weight for a in assignments),
                total_volume_packed=sum(a.volume for a in assignments),
                avg_weight_utilization_pct=round(sum(weight_utils) / len(weight_utils), 1) if weight_utils else 0,
                avg_volume_utilization_pct=round(sum(volume_utils) / len(volume_utils), 1) if volume_utils else 0,
                total_bin_cost=total_bin_cost,
                solve_time_seconds=round(solve_time, 3),
            )

            msg_parts = [
                f"{'Optimal' if solver_status == PackingStatus.OPTIMAL else 'Feasible'} packing found in {solve_time:.2f}s.",
                f"{n_used}/{n_bins} bins used.",
                f"{len(assignments)}/{n_items} items packed.",
            ]
            if unpacked:
                msg_parts.append(f"{len(unpacked)} items unpacked.")

            return PackingResponse(
                status=solver_status,
                message=" ".join(msg_parts),
                assignments=assignments,
                bin_summaries=bin_summaries,
                metrics=metrics,
                unpacked_items=unpacked,
            )

        elif status == cp_model.INFEASIBLE:
            return PackingResponse(
                status=PackingStatus.NO_SOLUTION,
                message="No feasible packing found. Total item weight/volume exceeds bin capacity. Try adding bins or enabling allow_partial=True."
            )
        else:
            return PackingResponse(
                status=PackingStatus.TIMEOUT,
                message=f"Solver timed out after {request.max_solve_time_seconds}s. Try increasing time limit or reducing problem size."
            )

    except Exception as e:
        return PackingResponse(
            status=PackingStatus.ERROR,
            message=f"Packing solver error: {str(e)}"
        )
