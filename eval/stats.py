"""Statistics used by the Week 2 evaluation (W2.5, W2.6).

Standard library only. Every formula is the one from Module 2, Part 7:
  - accuracy with a 95% interval   (slide "How many test cases do you need?")
  - McNemar's paired test          (slide "Is prompt B really better than prompt A?")
  - Cohen's kappa                  (slide "Checking the judge against humans")

Run this file directly to check the formulas against the slide examples:
    python3 eval/stats.py
"""

import math


def accuracy_ci95(correct, n):
    """Accuracy p = correct / n with a 95% interval p +/- 1.96 * SE.

    SE = sqrt(p * (1 - p) / n). The interval is clipped to [0, 1].
    Returns (p, low, high). With n = 0 there is nothing to measure.
    """
    if n == 0:
        return None, None, None
    p = correct / n
    se = math.sqrt(p * (1 - p) / n)
    low = max(0.0, p - 1.96 * se)
    high = min(1.0, p + 1.96 * se)
    return p, low, high


def mcnemar(b, c):
    """McNemar's test for two prompts run on the same test cases.

    b = cases where A is right and B is wrong
    c = cases where A is wrong and B is right
    Cases where both are right or both are wrong carry no information.

    chi2 = (b - c)^2 / (b + c), 1 degree of freedom; above 3.84 the
    difference is significant at the 5% level.

    The chi-square approximation is weak when b + c is small, so we also
    report the exact two-sided binomial p-value: under "no difference",
    each disagreement is a fair coin flip.
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p_chi2": 1.0, "p_exact": 1.0, "significant_5pct": False}

    chi2 = (b - c) ** 2 / n
    # Survival function of chi-square with 1 degree of freedom
    p_chi2 = math.erfc(math.sqrt(chi2 / 2))

    # Exact test: probability of a split at least this uneven with a fair coin
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    p_exact = min(1.0, 2 * tail)

    return {
        "b": b,
        "c": c,
        "chi2": round(chi2, 4),
        "p_chi2": round(p_chi2, 4),
        "p_exact": round(p_exact, 4),
        "significant_5pct": chi2 > 3.84,
    }


def cohens_kappa(labels_a, labels_b):
    """Cohen's kappa between two raters who labeled the same items.

    po = observed agreement (share of items with the same label)
    pe = agreement expected by chance, from each rater's label frequencies
    kappa = (po - pe) / (1 - pe)

    Returns a dict with po, pe and kappa. kappa is None when pe = 1
    (both raters used a single identical label, so chance agreement is total
    and kappa is undefined).
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("Both raters must label the same number of items.")
    n = len(labels_a)
    if n == 0:
        raise ValueError("No labels to compare.")

    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    pe = 0.0
    for label in set(labels_a) | set(labels_b):
        share_a = labels_a.count(label) / n
        share_b = labels_b.count(label) / n
        pe += share_a * share_b

    kappa = None if pe == 1 else (po - pe) / (1 - pe)
    return {
        "n": n,
        "po": round(po, 4),
        "pe": round(pe, 4),
        "kappa": None if kappa is None else round(kappa, 4),
    }


def percentile(values, p):
    """Linearly interpolated percentile; p = 0.5 gives the median."""
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lower = int(k)
    upper = min(lower + 1, len(s) - 1)
    return s[lower] + (k - lower) * (s[upper] - s[lower])


if __name__ == "__main__":
    # Self-check against the worked examples on the Module 2 slides.
    p, low, high = accuracy_ci95(40, 50)
    print(f"accuracy 40/50 = {p:.2f}, 95% interval +/- {100 * (high - p):.1f} points (slide: 11.1)")

    print("McNemar b=3, c=15:", mcnemar(3, 15), "(slide: chi2 = 8.0, significant)")
    print("McNemar b=5, c=9: ", mcnemar(5, 9), "(slide: chi2 about 1.1, not significant)")

    # Slide table: judge good & human good 60, judge good & human bad 10,
    #              judge bad & human good 5,   judge bad & human bad 25
    judge = ["good"] * 60 + ["good"] * 10 + ["bad"] * 5 + ["bad"] * 25
    human = ["good"] * 60 + ["bad"] * 10 + ["good"] * 5 + ["bad"] * 25
    print("Cohen's kappa:", cohens_kappa(judge, human), "(slide: po = 0.85, pe = 0.56, kappa about 0.66)")
