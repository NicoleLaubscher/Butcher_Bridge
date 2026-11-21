"""Deterministic procurement evaluator. No network/database dependencies."""
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

def D(value):
    return Decimal(str(value))

def money(v):
    return float(D(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

def evaluate(orders, offers, tiers, reserved=None, min_fill=0.95, as_of=None):
    """Only committed, same product+specification+needed date+area+window are compatible.
    Supplier capacity is shared across reserved windows. One supplier must fill an entire batch.
    Strictly reject equal-cost or worse group orders; retain noneligible offers for explanation.
    """
    as_of = as_of or date.today()
    reserved = reserved or {}
    groups = defaultdict(list)
    for o in orders:
        if o['status'] != 'committed':
            continue
        key = (o['window_id'], o['product_id'], str(o['needed_date']), o['delivery_area'])
        groups[key].append(o)
    outputs=[]
    for (window,product,need,area), batch in groups.items():
        q = sum(D(o['quantity_kg']) for o in batch)
        baseline = sum(D(o['quantity_kg'])*D(o['baseline_price_per_kg']) + D(o['baseline_logistics_cost']) for o in batch)
        base_trips = sum(int(o['baseline_trips']) for o in batch)
        base_distance = sum(D(o['baseline_distance_km']) for o in batch)
        ranked=[]
        for offer in offers:
            if offer['product_id'] != product or not offer['active']:
                continue
            reasons=[]
            available = D(offer['capacity_kg']) - sum(D(v) for (offer_id, reserved_window),v in reserved.items() if offer_id == offer['id'] and reserved_window != window)
            if available < q: reasons.append('Insufficient unreserved capacity')
            if offer['service_area'].casefold() != area.casefold(): reasons.append('Outside service area')
            days_available = (date.fromisoformat(need) - as_of).days
            if days_available < 0 or int(offer['lead_days']) > days_available: reasons.append('Lead time exceeds required date')
            if D(offer['fill_rate']) < D(min_fill): reasons.append('Below minimum expected fill rate')
            eligible_tiers = [t for t in tiers if t['offer_id']==offer['id'] and D(t['min_quantity_kg'])<=q]
            best_tier=max(eligible_tiers,key=lambda t:D(t['min_quantity_kg'])) if eligible_tiers else None
            if best_tier is None: reasons.append('No qualifying price tier')
            total=None
            if best_tier:
                total=q*D(best_tier['price_per_kg'])+D(offer['fixed_delivery'])+q*D(offer['variable_delivery_per_kg'])+D(offer['handling_cost'])
            ranked.append({'offer_id':offer['id'],'supplier':offer['supplier_name'], 'eligible':not reasons,
                'reasons':reasons,'total_cost':money(total) if total is not None else None,
                'cost_per_kg':money(total/q) if total is not None else None,
                'tier_min_kg':float(best_tier['min_quantity_kg']) if best_tier else None,
                'available_kg':float(available), 'delivery_trips':int(offer['coordinated_trips']),
                'distance_km':float(offer['coordinated_distance_km'])})
            
        
        feasible = [v for v in ranked if v['eligible']]
        winner = min(feasible, key=lambda x: x['total_cost']) if feasible else None

        # Count distinct participating retailers, not just orders.
        retailer_count = len({o['retailer_id'] for o in batch})

        
        if not winner:
            decision = 'REJECT_NO_FEASIBLE_SUPPLIER'
            reason = (
                'No eligible supplier satisfies the procurement requirements. '
                'Retailers should retain their existing procurement arrangements.'
            )

        elif retailer_count == 1:
            if D(winner['total_cost']) < baseline:
                decision = 'INDIVIDUAL_BETTER_QUOTE'
                reason = (
                    'Only one retailer is participating. A cheaper feasible '
                    'supplier quotation is available. Recommend individual '
                    'procurement from this supplier. This is not aggregation.'
                )
            else:
                decision = 'INDIVIDUAL_KEEP_BASELINE'
                reason = (
                    'Only one retailer is participating. The retailer should '
                    'retain its existing procurement arrangement because it '
                    'is cheaper than or equal in cost to the alternative '
                    'supplier quotation. This is not aggregation.'
                )

        elif D(winner['total_cost']) >= baseline:
            decision = 'REJECT_NOT_CHEAPER'
            reason = (
                'Multi-retailer aggregation does not reduce total delivered '
                'procurement cost. Retailers should retain their existing '
                'procurement arrangements.'
            )

        else:
            decision = 'ACCEPT'
            reason = (
                'Genuine multi-retailer aggregation is feasible and lowers '
                'total delivered procurement cost compared with existing '
                'arrangements.'
            )

        
         # Calculate supplier group cost
        group_cost = (
            D(winner['total_cost']) if winner else None
        )

        # Allocate supplier costs to participating orders
        allocated = []

        if winner:
            shares = []

            for o in batch[:-1]:
                shares.append(
                    D(str(money(
                        group_cost * D(o['quantity_kg']) / q
                    )))
                )

            shares.append(group_cost - sum(shares))

            allocated = [
                {
                    'order_id': o['id'],
                    'retailer': o['retailer_name'],
                    'allocated_cost': money(c)
                }
                for o, c in zip(batch, shares)
            ]

        # Raw percentage difference between baseline and supplier quote
        savings_pct = (
            money((baseline - group_cost) / baseline * 100)
            if group_cost is not None and baseline > 0
            else None
        )

        # Savings associated with the recommended decision
        recommended_savings_pct = (
            money((baseline - group_cost) / baseline * 100)
            if decision in (
                'ACCEPT',
                'INDIVIDUAL_BETTER_QUOTE'
            )
            and group_cost is not None
            and baseline > 0
            else 0.0
        )

        # Return procurement evaluation results
        outputs.append({
            'window_id': window,
            'product_id': product,
            'needed_date': need,
            'area': area,
            'quantity_kg': float(q),
            'orders': len(batch),
            'retailer_count': retailer_count,
            'baseline_total': money(baseline),
            'baseline_cost_per_kg': money(baseline / q),
            'baseline_trips': base_trips,
            'baseline_distance_km': float(base_distance),
            'offers': ranked,
            'best': winner,
            'decision': decision,
            'reason': reason,
            'savings_pct': savings_pct,
            'recommended_savings_pct': recommended_savings_pct,
            'allocated_costs': allocated,
            'evidence_type': (
                'primary'
                if all(
                    o['evidence_type'] == 'primary'
                    for o in batch
                )
                else 'mixed_or_simulated'
            )
        })

    return outputs
        

        
        
           
