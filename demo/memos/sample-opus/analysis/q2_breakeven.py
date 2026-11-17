"""Q2: how far churn must fall for a rollback to 299 RUB to keep revenue.

Inputs from sources/S001.md (monthly) and S002.md (prices 299 / 349).
Simplification: ARPU scales with the price ratio 299/349 (everyone on the family plan);
steady-state paying base is proportional to 1 / churn at equal inflow.
"""

price_old, price_new = 299, 349
arpu_oct, users_oct, churn_oct = 334, 42300, 6.8
arpu_jul, users_jul = 289, 44100

ratio = price_old / price_new
print(f"price cut: {1 - ratio:.1%}")
arpu_rollback = arpu_oct * ratio
print(f"ARPU after rollback (scaled): ~{arpu_rollback:.0f} RUB")

rev_oct = users_oct * arpu_oct
rev_jul = users_jul * arpu_jul
print(f"revenue Oct 2026 ~{rev_oct / 1e6:.2f}M, Jul 2026 ~{rev_jul / 1e6:.2f}M RUB")

# 1) keep October revenue: base must grow by 349/299
users_needed = rev_oct / arpu_rollback
print(f"users needed to keep Oct revenue: ~{users_needed:.0f} (+{users_needed / users_oct - 1:.1%})")
churn_needed = churn_oct * ratio
print(f"steady-state churn needed to keep Oct revenue: <= {churn_needed:.2f}% (from {churn_oct}%)")

# 2) keep July revenue (the brief's floor)
users_floor = rev_jul / arpu_rollback
print(f"users needed for July revenue floor: ~{users_floor:.0f} ({users_floor / users_oct - 1:+.1%} vs Oct)")
