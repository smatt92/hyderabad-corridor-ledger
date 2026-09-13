import pandas as pd
import pytest

from metrics.shrinkage import beta_binomial_eb, normal_eb


def series(values, index=("a", "b", "c")):
    return pd.Series(values, index=list(index), dtype=float)


def test_normal_eb_equal_counts():
    # sampling var = 1/10 = 0.1 each; var(means) = 1.0; tau2 = 0.9
    # equal weights -> city = 2.0; B = 0.1 / 1.0 = 0.1
    out = normal_eb(series([10, 10, 10]), series([1.0, 2.0, 3.0]), series([1.0, 1.0, 1.0]))
    assert out["city_mean"].iloc[0] == pytest.approx(2.0)
    assert out["shrunk"].tolist() == pytest.approx([1.1, 2.0, 2.9])
    assert out["raw"].tolist() == [1.0, 2.0, 3.0]


def test_normal_eb_three_bad_samples_do_not_top_the_table():
    idx = ("steady_low", "steady_high", "few_bad")
    n = series([1000, 1000, 2], idx)
    mean = series([1.0, 2.5, 3.0], idx)
    var = series([4.0, 4.0, 4.0], idx)
    out = normal_eb(n, mean, var)

    v = [4 / 1000, 4 / 1000, 4 / 2]
    grand = (1.0 + 2.5 + 3.0) / 3
    var_means = ((1.0 - grand) ** 2 + (2.5 - grand) ** 2 + (3.0 - grand) ** 2) / 2
    tau2 = var_means - sum(v) / 3
    w = [1 / (vi + tau2) for vi in v]
    city = (w[0] * 1.0 + w[1] * 2.5 + w[2] * 3.0) / sum(w)
    b = [vi / (vi + tau2) for vi in v]
    expected = [b[i] * city + (1 - b[i]) * m for i, m in enumerate([1.0, 2.5, 3.0])]

    assert out["shrunk"].tolist() == pytest.approx(expected)
    assert out.loc["few_bad", "raw"] > out.loc["steady_high", "raw"]
    assert out.loc["few_bad", "shrunk"] < out.loc["steady_high", "shrunk"]  # ranking flips


def test_beta_binomial_eb_partial_pooling():
    # m = 150/300 = 0.5; s2 = (100*0.16 + 100*0.16)/300 = 32/300; a = 3/300
    # rho = (32/75 - 0.01) / 0.99 = 5/11.88; prior_n = 11.88/5 - 1 = 1.376
    out = beta_binomial_eb(series([10, 90, 50]), series([100, 100, 100]))
    assert out["city_mean"].iloc[0] == pytest.approx(0.5)
    assert out["shrunk"].tolist() == pytest.approx([10.688 / 101.376, 90.688 / 101.376, 0.5])


def test_beta_binomial_eb_full_pooling_when_spread_is_just_noise():
    # m = 35/114; the spread is below binomial noise, so rho <= 0
    out = beta_binomial_eb(series([2, 30, 3]), series([4, 100, 10]))
    assert out["shrunk"].tolist() == pytest.approx([35 / 114] * 3)
    assert out["raw"].tolist() == pytest.approx([0.5, 0.3, 0.3])
