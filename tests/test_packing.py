"""Tests for OptimEngine Bin Packing Solver."""

import pytest
from packing.models import (
    PackingRequest, Item, Bin, PackingObjective, PackingStatus,
)
from packing.engine import solve_packing


def make_simple_request(
    num_items=5, item_weight=10, num_bins=3, bin_capacity=30, **kwargs
) -> PackingRequest:
    items = [
        Item(item_id=f"item_{i}", name=f"Item {i}", weight=item_weight, value=i + 1)
        for i in range(num_items)
    ]
    bins = [
        Bin(bin_id=f"bin_{j}", name=f"Bin {j}", weight_capacity=bin_capacity)
        for j in range(num_bins)
    ]
    return PackingRequest(
        items=items, bins=bins, max_solve_time_seconds=10, **kwargs
    )


class TestBasicPacking:
    def test_simple_packing(self):
        resp = solve_packing(make_simple_request(5, 10, 3, 30))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.items_packed == 5

    def test_single_item_single_bin(self):
        req = PackingRequest(
            items=[Item(item_id="a", weight=5)],
            bins=[Bin(bin_id="b1", weight_capacity=10)],
        )
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.items_packed == 1
        assert resp.metrics.bins_used == 1

    def test_all_items_assigned(self):
        resp = solve_packing(make_simple_request(4, 10, 2, 30))
        assert resp.metrics.items_unpacked == 0

    def test_assignments_have_correct_fields(self):
        resp = solve_packing(make_simple_request(3, 10, 2, 30))
        for a in resp.assignments:
            assert a.item_id is not None
            assert a.bin_id is not None
            assert a.weight > 0


class TestCapacity:
    def test_weight_not_exceeded(self):
        resp = solve_packing(make_simple_request(6, 10, 3, 25))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        for bs in resp.bin_summaries:
            if bs.is_used:
                assert bs.weight_used <= bs.weight_capacity

    def test_forces_multiple_bins(self):
        resp = solve_packing(make_simple_request(4, 10, 3, 25))
        assert resp.metrics.bins_used >= 2

    def test_infeasible_without_partial(self):
        req = make_simple_request(5, 20, 1, 10)
        resp = solve_packing(req)
        assert resp.status == PackingStatus.NO_SOLUTION

    def test_volume_constraint(self):
        items = [
            Item(item_id=f"i{i}", weight=5, volume=15) for i in range(4)
        ]
        bins = [
            Bin(bin_id="b1", weight_capacity=100, volume_capacity=30),
            Bin(bin_id="b2", weight_capacity=100, volume_capacity=30),
        ]
        req = PackingRequest(items=items, bins=bins, max_solve_time_seconds=10)
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.bins_used == 2
        for bs in resp.bin_summaries:
            if bs.is_used:
                assert bs.volume_used <= bs.volume_capacity


class TestObjectives:
    def test_minimize_bins(self):
        resp = solve_packing(make_simple_request(
            3, 10, 5, 50, objective=PackingObjective.MINIMIZE_BINS
        ))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.bins_used == 1

    def test_maximize_value(self):
        items = [
            Item(item_id="cheap", weight=50, value=1),
            Item(item_id="expensive", weight=10, value=100),
        ]
        bins = [Bin(bin_id="b1", weight_capacity=30)]
        req = PackingRequest(
            items=items, bins=bins,
            objective=PackingObjective.MAXIMIZE_VALUE,
            allow_partial=True, max_solve_time_seconds=10,
        )
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        packed_ids = [a.item_id for a in resp.assignments]
        assert "expensive" in packed_ids
        assert "cheap" not in packed_ids

    def test_maximize_items(self):
        items = [
            Item(item_id="big", weight=80, value=1),
            Item(item_id="small1", weight=10, value=1),
            Item(item_id="small2", weight=10, value=1),
            Item(item_id="small3", weight=10, value=1),
        ]
        bins = [Bin(bin_id="b1", weight_capacity=35)]
        req = PackingRequest(
            items=items, bins=bins,
            objective=PackingObjective.MAXIMIZE_ITEMS,
            allow_partial=True, max_solve_time_seconds=10,
        )
        resp = solve_packing(req)
        assert resp.metrics.items_packed == 3

    def test_balance_load(self):
        resp = solve_packing(make_simple_request(
            6, 10, 3, 30, objective=PackingObjective.BALANCE_LOAD
        ))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)


class TestPartialPacking:
    def test_partial_allowed(self):
        req = make_simple_request(5, 20, 1, 30, allow_partial=True)
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.items_unpacked > 0
        assert len(resp.unpacked_items) > 0

    def test_partial_packs_as_many_as_possible(self):
        items = [Item(item_id=f"i{i}", weight=10) for i in range(5)]
        bins = [Bin(bin_id="b1", weight_capacity=30)]
        req = PackingRequest(
            items=items, bins=bins, allow_partial=True, max_solve_time_seconds=10, objective=PackingObjective.MAXIMIZE_ITEMS,
        )
        resp = solve_packing(req)
        assert resp.metrics.items_packed == 3


class TestQuantities:
    def test_item_quantity(self):
        items = [Item(item_id="widget", weight=10, quantity=4)]
        bins = [Bin(bin_id="box", weight_capacity=25, quantity=2)]
        req = PackingRequest(items=items, bins=bins, max_solve_time_seconds=10)
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.items_packed == 4
        assert resp.metrics.bins_used == 2

    def test_bin_quantity(self):
        items = [Item(item_id=f"i{i}", weight=10) for i in range(6)]
        bins = [Bin(bin_id="box", weight_capacity=25, quantity=3)]
        req = PackingRequest(items=items, bins=bins, max_solve_time_seconds=10)
        resp = solve_packing(req)
        assert resp.metrics.bins_used == 3


class TestGroups:
    def test_groups_together(self):
        items = [
            Item(item_id="a1", weight=5, group="A"),
            Item(item_id="a2", weight=5, group="A"),
            Item(item_id="b1", weight=5, group="B"),
        ]
        bins = [
            Bin(bin_id="box1", weight_capacity=15),
            Bin(bin_id="box2", weight_capacity=15),
        ]
        req = PackingRequest(
            items=items, bins=bins, keep_groups_together=True, max_solve_time_seconds=10,
        )
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        a_bins = set()
        for a in resp.assignments:
            if a.item_id in ("a1", "a2"):
                a_bins.add(a.bin_id)
        assert len(a_bins) == 1


class TestMaxItems:
    def test_max_items_per_bin(self):
        items = [Item(item_id=f"i{i}", weight=1) for i in range(6)]
        bins = [
            Bin(bin_id="b1", weight_capacity=100, max_items=3),
            Bin(bin_id="b2", weight_capacity=100, max_items=3),
        ]
        req = PackingRequest(items=items, bins=bins, max_solve_time_seconds=10)
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        for bs in resp.bin_summaries:
            if bs.is_used:
                assert bs.items_packed <= 3


class TestEdgeCases:
    def test_exact_fit(self):
        items = [Item(item_id="i1", weight=50)]
        bins = [Bin(bin_id="b1", weight_capacity=50)]
        resp = solve_packing(PackingRequest(items=items, bins=bins))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.bins_used == 1

    def test_many_bins_few_items(self):
        items = [Item(item_id="i1", weight=10)]
        bins = [Bin(bin_id=f"b{j}", weight_capacity=20) for j in range(5)]
        resp = solve_packing(PackingRequest(
            items=items, bins=bins, objective=PackingObjective.MINIMIZE_BINS,
        ))
        assert resp.metrics.bins_used == 1

    def test_metrics_consistency(self):
        resp = solve_packing(make_simple_request(6, 10, 3, 25))
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        m = resp.metrics
        assert m.items_packed + m.items_unpacked == 6
        assert m.solve_time_seconds > 0


class TestInputValidation:
    def test_duplicate_item_ids(self):
        with pytest.raises(Exception):
            PackingRequest(
                items=[Item(item_id="x", weight=1), Item(item_id="x", weight=2)],
                bins=[Bin(bin_id="b", weight_capacity=10)],
            )

    def test_duplicate_bin_ids(self):
        with pytest.raises(Exception):
            PackingRequest(
                items=[Item(item_id="i", weight=1)],
                bins=[Bin(bin_id="b", weight_capacity=10), Bin(bin_id="b", weight_capacity=20)],
            )

    def test_zero_weight_rejected(self):
        with pytest.raises(Exception):
            Item(item_id="bad", weight=0)

    def test_zero_capacity_rejected(self):
        with pytest.raises(Exception):
            Bin(bin_id="bad", weight_capacity=0)


class TestRealisticScenario:
    def test_warehouse_packing(self):
        """Simulate packing products into shipping containers."""
        items = [
            Item(item_id="laptop", name="Laptop Box", weight=3, volume=8, value=1200, quantity=10),
            Item(item_id="monitor", name="Monitor Box", weight=8, volume=25, value=500, quantity=5),
            Item(item_id="keyboard", name="Keyboard Pack", weight=1, volume=3, value=80, quantity=20),
            Item(item_id="server", name="Server Rack", weight=30, volume=60, value=5000, quantity=2),
        ]
        bins = [
            Bin(bin_id="pallet_small", name="Small Pallet", weight_capacity=50, volume_capacity=100, cost=10, quantity=5),
            Bin(bin_id="pallet_large", name="Large Pallet", weight_capacity=100, volume_capacity=200, cost=20, quantity=3),
        ]
        req = PackingRequest(
            items=items, bins=bins,
            objective=PackingObjective.MINIMIZE_BINS,
            max_solve_time_seconds=15,
        )
        resp = solve_packing(req)
        assert resp.status in (PackingStatus.OPTIMAL, PackingStatus.FEASIBLE)
        assert resp.metrics.items_packed == 37
        assert resp.metrics.items_unpacked == 0
        for bs in resp.bin_summaries:
            if bs.is_used:
                assert bs.weight_used <= bs.weight_capacity
                if bs.volume_capacity > 0:
                    assert bs.volume_used <= bs.volume_capacity
