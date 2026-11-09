import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from adu.sample import select_sample


def make_df():
    rows = []

    def add(status, reason=None, flags="", k=1):
        for _ in range(k):
            rows.append({"parcel_id": f"p{len(rows):03d}", "status": status,
                         "reason": reason, "flags": flags})

    add("fits", k=40)
    add("no_fit", "no_pocket", k=6)
    add("no_fit", "pocket_too_small", k=8)
    add("no_fit", "coverage_exhausted", k=1)
    add("uncertain", "pocket_too_small", "missing_living_area", k=10)
    add("uncertain", None, "odd_shape", k=30)
    add("flagged_town", None, "", k=5)
    add("ineligible", "not_sfd", k=20)
    df = pd.DataFrame(rows)
    return gpd.GeoDataFrame(df, geometry=[box(0, 0, 1, 1)] * len(df), crs=2248)


def test_size_at_most_n():
    for n in (10, 40, 100):
        assert len(select_sample(make_df(), n=n)) <= n


def test_all_strata_present():
    s = select_sample(make_df(), n=40)
    assert set(s.status) >= {"fits", "uncertain", "flagged_town", "no_fit"}
    nf = s[s.status == "no_fit"]
    assert nf.groupby("reason").size().min() >= 1
    assert set(nf.reason) == {"no_pocket", "pocket_too_small", "coverage_exhausted"}
    assert (nf.reason == "no_pocket").sum() >= 3
    assert (s.status == "flagged_town").sum() >= 3
    assert s["flags"].str.contains("odd_shape").any()
    assert (s.status == "ineligible").sum() == 0
    assert ((s.status == "uncertain") | s["flags"].str.contains("odd_shape")).sum() <= 20


def test_deterministic_and_seed_sensitive():
    a = list(select_sample(make_df(), seed=3).parcel_id)
    assert a == list(select_sample(make_df(), seed=3).parcel_id)
    assert a != list(select_sample(make_df(), seed=4).parcel_id)
    assert len(set(a)) == len(a)
