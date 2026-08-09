"""Comparison operators. POC scope (§2.3, §4 step 2).

Every operator takes the same 4 args -- the previous and current value of each
side -- so the engine can dispatch them all through one dict with no special
cases. Point-in-time ops just ignore the `_prev` args.
"""


def crosses_above(l_prev: float, l_cur: float, r_prev: float, r_cur: float) -> bool:
    return l_prev <= r_prev and l_cur > r_cur


def crosses_below(l_prev: float, l_cur: float, r_prev: float, r_cur: float) -> bool:
    return l_prev >= r_prev and l_cur < r_cur


def greater(l_prev: float, l_cur: float, r_prev: float, r_cur: float) -> bool:
    return l_cur > r_cur


def less(l_prev: float, l_cur: float, r_prev: float, r_cur: float) -> bool:
    return l_cur < r_cur
