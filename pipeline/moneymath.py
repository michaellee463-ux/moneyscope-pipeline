"""Money-math helpers. All numbers shown on screen must come from these
functions (or directly from a cited source), never from mental math."""
from decimal import Decimal, ROUND_HALF_UP


def payoff(balance, apr_pct, payment, max_months=1200):
    """Fixed monthly payment on a revolving balance. Interest = APR/12 on
    the balance each month (monthly compounding approximation)."""
    bal = Decimal(str(balance))
    r = Decimal(str(apr_pct)) / Decimal(100) / Decimal(12)
    pay = Decimal(str(payment))
    months, interest, paid = 0, Decimal(0), Decimal(0)
    while bal > 0:
        i = (bal * r).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if pay <= i:
            raise ValueError("payment never covers interest")
        bal += i
        interest += i
        p = min(pay, bal)
        bal -= p
        paid += p
        months += 1
        if months > max_months:
            raise ValueError("too long")
    return {"months": months, "interest": float(interest), "total_paid": float(paid)}


def future_value_daily(amount_per_day, annual_rate_pct, years):
    """Deposit amount_per_day*365/12 monthly, compounded monthly."""
    m = Decimal(str(amount_per_day)) * Decimal(365) / Decimal(12)
    r = Decimal(str(annual_rate_pct)) / Decimal(100) / Decimal(12)
    bal = Decimal(0)
    for _ in range(int(years * 12)):
        bal = bal * (1 + r) + m
    return float(bal)


if __name__ == "__main__":
    import json
    out = {p: payoff(1000, 22.36, p) for p in (1000, 100, 50, 35)}
    print(json.dumps(out, indent=1))
