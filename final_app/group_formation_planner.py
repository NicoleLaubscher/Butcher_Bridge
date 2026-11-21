"""Bounded exact search over disjoint retailer groups and shared offer capacity."""

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction


class GroupPlanningLimit(Exception):
    """The retailer-group search exhausted a configured budget."""


@dataclass(frozen=True)
class GroupPlanningLimits:
    max_retailers_per_bucket: int = 8
    max_quote_evaluations: int = 5_000
    max_search_nodes: int = 100_000

    def __post_init__(self):
        limits = (self.max_retailers_per_bucket, self.max_quote_evaluations, self.max_search_nodes)
        if any(type(limit) is not int or limit < 0 for limit in limits):
            raise ValueError("Retailer grouping limits must be nonnegative integers.")


@dataclass(frozen=True)
class GroupOffer:
    members: int  # Bit mask with one bit per retailer bundle in the request.
    offer_id: int
    quantity_kg: Decimal
    savings: Decimal


@dataclass
class _SearchNode:
    uncovered: int
    savings: Fraction
    savings_bound: Fraction
    choices: Iterator[GroupOffer | None]
    entered_by: tuple[GroupOffer, Decimal] | None = None


def _member_bits(mask):
    while mask:
        bit = mask & -mask
        yield bit
        mask ^= bit


def plan_groups(candidates, available_kg, max_search_nodes):
    """Return the cheapest assignment's supplier groups, or raise on the node limit."""
    by_member = defaultdict(list)
    member_bounds = defaultdict(Fraction)
    exact_savings = {}
    for candidate in candidates:
        savings = Fraction(candidate.savings)
        exact_savings[candidate] = savings
        # Divide a group's savings among its members to bound the remaining savings.
        share = savings / candidate.members.bit_count()
        for bit in _member_bits(candidate.members):
            by_member[bit].append(candidate)
            member_bounds[bit] = max(member_bounds[bit], share)

    if not by_member:
        return []

    for options in by_member.values():
        options.sort(key=lambda offer: (-exact_savings[offer], offer.members, offer.offer_id))
    group_bounds = {
        mask: sum(member_bounds[bit] for bit in _member_bits(mask))
        for mask in {candidate.members for candidate in exact_savings}
    }

    remaining = available_kg.copy()
    selected = []
    best_plan = []
    best_savings = Fraction(0)
    visited_nodes = 0

    def choices(uncovered):
        first = uncovered & -uncovered
        for option in by_member[first]:
            if (option.members & uncovered == option.members
                    and option.quantity_kg <= remaining[option.offer_id]):
                yield option
        yield None  # Retain the retailer bundle's baseline.

    def visit(uncovered, savings, bound, entered_by=None):
        nonlocal visited_nodes
        visited_nodes += 1
        if visited_nodes > max_search_nodes:
            raise GroupPlanningLimit(f"The search node limit of {max_search_nodes:,} was exceeded.")
        return _SearchNode(uncovered, savings, bound, choices(uncovered), entered_by)

    stack = [visit(sum(by_member), Fraction(0), sum(member_bounds.values()))]
    exhausted = object()
    while stack:
        node = stack[-1]
        if not node.uncovered:
            if node.savings > best_savings:
                best_savings = node.savings
                best_plan = selected.copy()
        elif node.savings + node.savings_bound > best_savings:
            option = next(node.choices, exhausted)
            if option is None:
                first = node.uncovered & -node.uncovered
                stack.append(visit(node.uncovered ^ first, node.savings,
                                   node.savings_bound - member_bounds[first]))
                continue
            if option is not exhausted:
                capacity = remaining[option.offer_id]
                remaining[option.offer_id] = capacity - option.quantity_kg
                selected.append(option)
                stack.append(visit(
                    node.uncovered ^ option.members,
                    node.savings + exact_savings[option],
                    node.savings_bound - group_bounds[option.members],
                    (option, capacity),
                ))
                continue

        stack.pop()
        if node.entered_by is not None:
            option, capacity = node.entered_by
            remaining[option.offer_id] = capacity
            selected.pop()

    return best_plan
