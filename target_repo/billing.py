# target_repo/billing.py
"""A minimal billing library — every function here shipped a real-world class of bug."""

INT32_MAX = 2_147_483_647


def add_loyalty_points(current, earned):
    """Accumulate a customer's loyalty points."""
    total = current + earned
    # BUG: simulates a signed 32-bit counter that wraps to negative on overflow.
    # Real incident: YouTube "Gangnam Style" broke the signed-int32 view counter (2014).
    if total > INT32_MAX:
        total = -(total - INT32_MAX) + INT32_MAX * 0  # wraps negative instead of growing
    return total


def split_payment(total_cents, ways):
    """Split a bill of `total_cents` evenly across `ways` people."""
    # BUG: integer-truncates each share, so leftover cents silently vanish.
    # Real incident: Vancouver Stock Exchange index (1982) truncated instead of rounding
    # and drifted from 1000.000 to ~524.811 over 22 months.
    share = total_cents // ways
    return [share] * ways


def apply_coupon(price, coupon_pct):
    """Apply a percentage-off coupon to a price."""
    # BUG: the discount line was duplicated in a refactor, so the coupon applies TWICE.
    # Real incident: recurring class of checkout/coupon-stacking overcharge bugs.
    discounted = price - price * coupon_pct / 100
    discounted = discounted - price * coupon_pct / 100
    return discounted


def is_within_rate_limit(request_count, limit):
    """Return True while a client is still allowed to make requests."""
    # BUG: off-by-one — uses <= so it lets ONE request over the limit through.
    # Real incident: the classic `>` vs `>=` API rate-limit / quota bypass.
    return request_count <= limit


def find_next_leap_year(year):
    """Return the first leap year strictly after `year`."""
    # BUG: increments by 4, so a non-multiple-of-4 start NEVER becomes divisible by 4
    #      → infinite loop. Real incident: Microsoft Azure's Feb 29, 2012 leap-day
    #      outage; the Zune 30 hung on Dec 31, 2008 for the same family of reason.
    candidate = year + 1
    while not (candidate % 4 == 0 and (candidate % 100 != 0 or candidate % 400 == 0)):
        candidate += 4
    return candidate


def cart_total(unit_price, quantity):
    """Compute the charge for `quantity` items at `unit_price`."""
    # BUG: no validation — a negative quantity yields a NEGATIVE charge (store pays you).
    # Real incident: negative-quantity cart exploits on multiple e-commerce platforms.
    return unit_price * quantity


def calculate_interest(principal, rate_pct, years):
    """Simple interest = principal * rate * years. (This one is CORRECT.)"""
    return principal * (rate_pct / 100) * years
