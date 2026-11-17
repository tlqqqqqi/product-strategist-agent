"""Q1 range: share of the Aug-Oct 2026 excess churn explained by the May 2026 promo cohort.

Inputs from sources/S001.md, S002.md and S004.md.
Reading A: sheet cohorts = users who joined in May 2026.
Reading B: sheet cohorts = the whole May 2026 base split by acquisition channel.
The promo launched in May 2026 (S002), so in both readings the promo row is people who joined
in May and whose first charge was in August; the readings differ for non-promo rows only.
Timing variants for the promo loss of 21.4% by month 3:
  upper: the whole loss happened at the first charge in August;
  lower: the loss is spread evenly over three months, one third in August.
Only the loss above the baseline churn rate counts as excess.
"""

baseline = (4.1 + 4.0 + 4.3) / 3
promo_n, promo_pct = 9800, 21.4
aug_excess = 44100 * (5.9 - baseline) / 100
total_excess = 779.4 + 1105.4 + 1162.6  # from S004, Aug + Sep + Oct

extra_rate = promo_pct - baseline
promo_extra = promo_n * extra_rate / 100
print(f"promo loss above baseline (May cohort): ~{promo_extra:.0f}")

upper_aug = promo_extra
lower_aug = promo_extra / 3
print(f"upper: share of August excess: {min(upper_aug / aug_excess, 1):.0%} (raw {upper_aug / aug_excess:.2f}x)")
print(f"lower: share of August excess: {lower_aug / aug_excess:.0%}")
print(f"upper: share of Aug-Oct excess: {upper_aug / total_excess:.0%}")
print(f"lower: share of Aug-Oct excess: {lower_aug / total_excess:.0%}")
print("range for the May promo cohort alone, Aug-Oct excess: "
      f"{lower_aug / total_excess:.0%}-{upper_aug / total_excess:.0%}")
