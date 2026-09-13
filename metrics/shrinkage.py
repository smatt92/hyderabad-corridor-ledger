"""Empirical-Bayes shrinkage toward the city mean.

A corridor with three bad samples should not top a "worst corridors" table.
Each corridor's estimate is pulled toward the city mean in proportion to how
little data it has. Raw and shrunk are both reported; ranking uses shrunk.

  normal_eb:         continuous indices (TTI, BTI, PTI). Normal-normal model,
                     between-corridor variance by the method of moments.
  beta_binomial_eb:  proportions (share of congested calls). Beta prior fitted
                     by the method of moments for unequal group sizes.
"""

import numpy as np
import pandas as pd


def normal_eb(n: pd.Series, mean: pd.Series, var: pd.Series) -> pd.DataFrame:
    """Shrink corridor means. n: values per corridor, var: their sample variance.

    Sampling variance of a corridor mean is var / n. Corridors with n = 1 use
    the pooled within-corridor variance. tau2 = max(0, var(means) - mean(var/n)).
    """
    n, mean, var = n.astype(float), mean.astype(float), var.astype(float)
    out = pd.DataFrame({"raw": mean})
    if len(mean) < 2:
        return out.assign(shrunk=mean, city_mean=mean.mean())

    has_var = var.notna()
    pooled = ((n - 1) * var)[has_var].sum() / (n - 1)[has_var].sum() if has_var.any() else np.nan
    sampling_var = var.where(has_var, pooled) / n
    if not np.isfinite(sampling_var).all():
        return out.assign(shrunk=np.nan, city_mean=np.nan)

    tau2 = max(0.0, float(mean.var(ddof=1) - sampling_var.mean()))
    total = sampling_var + tau2
    if (total <= 0).any():
        return out.assign(shrunk=mean, city_mean=mean.mean())

    weights = 1.0 / total
    city = float((weights * mean).sum() / weights.sum())
    b = sampling_var / total
    return out.assign(shrunk=b * city + (1 - b) * mean, city_mean=city)


def beta_binomial_eb(k: pd.Series, n: pd.Series) -> pd.DataFrame:
    """Shrink corridor proportions k/n with a method-of-moments beta prior.

    m = sum(k) / sum(n); s2 = sum(n (p - m)^2) / sum(n); a = K / sum(n)
    rho = (s2 / (m (1 - m)) - a) / (1 - a), and alpha + beta = 1/rho - 1.
    rho <= 0 means no detectable between-corridor spread: full pooling to m.
    """
    k, n = k.astype(float), n.astype(float)
    raw = k / n
    out = pd.DataFrame({"raw": raw})
    total = n.sum()
    m = float(k.sum() / total)
    corridors = len(n)
    if corridors < 2:
        return out.assign(shrunk=raw, city_mean=m)
    if m in (0.0, 1.0):
        return out.assign(shrunk=m, city_mean=m)

    a = corridors / total
    if a >= 1:
        return out.assign(shrunk=np.nan, city_mean=m)
    s2 = float((n * (raw - m) ** 2).sum() / total)
    rho = (s2 / (m * (1 - m)) - a) / (1 - a)
    if rho <= 0:
        return out.assign(shrunk=m, city_mean=m)
    if rho >= 1:
        return out.assign(shrunk=raw, city_mean=m)
    prior_n = 1 / rho - 1
    return out.assign(shrunk=(k + m * prior_n) / (n + prior_n), city_mean=m)
