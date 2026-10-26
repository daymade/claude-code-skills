#!/usr/bin/env python3
"""Calculate a batch's capacity ceiling and duration from a measured pilot; no cleanup."""
import argparse
import json
import math


def positive(v, name, zero=False):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or (not zero and v == 0):
        raise ValueError(name + ' must be a finite ' + ('nonnegative' if zero else 'positive') + ' number')
    return v


def assess(v):
    if not isinstance(v, dict):
        raise ValueError('input must be an object')
    free = positive(v['available_bytes'], 'available_bytes', True)
    target = positive(v['target_available_bytes'], 'target_available_bytes')
    count = positive(v['remaining_items'], 'remaining_items', True)
    pilot = positive(v['pilot_items'], 'pilot_items')
    seconds = positive(v['pilot_seconds'], 'pilot_seconds')
    if int(count) != count or int(pilot) != pilot:
        raise ValueError('item counts must be integers')
    upper = v['reclaim_upper_bytes']
    if upper is not None:
        upper = positive(upper, 'reclaim_upper_bytes', True)
    gap = max(0, target-free)
    if gap == 0:
        decision = 'watermark_met_sustainability_unverified'
    elif upper is None:
        decision = 'gain_unknown_do_not_claim_gap_closed'
    elif upper < gap:
        decision = 'upper_bound_insufficient_find_additional_authorized_route'
    else:
        decision = 'ceiling_only_measure_actual_available_after_batch'
    return dict(remaining_gap_bytes=gap, reclaim_upper_bytes=upper,
                upper_bound_remaining_gap_bytes=None if upper is None else max(0, gap-upper),
                estimated_remaining_seconds=count*seconds/pilot,
                decision=decision, physical_release_bytes=None,
                authorization_granted=False, capacity_goal_complete=False,
                limits='Pilot workload may differ. An upper bound is not guaranteed release; no sustained growth rate was measured.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', help='JSON with available_bytes, target_available_bytes, remaining_items, pilot_items, pilot_seconds, reclaim_upper_bytes (number or explicit null)')
    a = p.parse_args()
    try:
        with open(a.input) as f:
            print(json.dumps(assess(json.load(f)), indent=2))
    except (KeyError, ValueError, TypeError, OSError) as e:
        p.exit(2, str(e)+'\n')


if __name__ == '__main__':
    main()
