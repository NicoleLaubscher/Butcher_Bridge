"""Choose whole-batch offers subject to shared unreserved capacity."""

from math import prod


MAX_EXACT_COMBINATIONS = 100_000


def plan_offers(batches, available_kg):
    """Return chosen offer IDs by batch index, or None if the search is too large.

    Each batch supplies its quantity and a mapping of individually feasible
    offer IDs to strictly positive savings. A missing index uses its baseline.
    The caller supplies batches in a stable order for cost ties.
    """
    choices = [
        (index, quantity, sorted(savings.items(), key=lambda item: (-item[1], item[0])))
        for index, (quantity, savings) in enumerate(batches)
        if savings
    ]

    # If all individual minima fit together, their sum is already optimal.
    remaining = available_kg.copy()
    independent_plan = {}
    for index, quantity, options in choices:
        offer_id, _ = options[0]
        remaining[offer_id] -= quantity
        if remaining[offer_id] < 0:
            break
        independent_plan[index] = offer_id
    else:
        return independent_plan

    if prod(len(options) + 1 for _, _, options in choices) > MAX_EXACT_COMBINATIONS:
        return None

    remaining = available_kg.copy()
    best_savings = 0
    best_plan = {}
    selected = {}

    def search(position, savings):
        nonlocal best_savings, best_plan
        if position == len(choices):
            if savings > best_savings:
                best_savings = savings
                best_plan = selected.copy()
            return

        index, quantity, options = choices[position]
        for offer_id, saving in options:
            capacity = remaining[offer_id]
            if capacity < quantity:
                continue
            remaining[offer_id] = capacity - quantity
            selected[index] = offer_id
            search(position + 1, savings + saving)
            del selected[index]
            remaining[offer_id] = capacity

        # The existing procurement baseline requires no capacity from these offers.
        search(position + 1, savings)

    search(0, 0)
    return best_plan
