"""Pick the stratified pilot sample shown in the verification viewer."""
import geopandas as gpd
import numpy as np
import pandas as pd

MIN_PER_STRATUM = 3


def _take(rng: np.random.RandomState, df: gpd.GeoDataFrame, k: int) -> gpd.GeoDataFrame:
    k = max(0, min(k, len(df)))
    return df.iloc[sorted(rng.choice(len(df), size=k, replace=False))]


def select_sample(fit_df: gpd.GeoDataFrame, n: int = 40, seed: int = 0) -> gpd.GeoDataFrame:
    """Stratified, deterministic sample of at most n parcels.

    Strata: every no_fit reason (>= 3 each), flagged_town (>= 3), then
    uncertain / odd_shape parcels (up to n/2, split between odd_shape and the
    rest), and the remainder filled with fits. Ineligible parcels are never shown.
    A `stratum` column records why each parcel was picked.
    """
    df = fit_df.sort_values("parcel_id").reset_index(drop=True)
    rng = np.random.RandomState(seed)
    chosen: list[gpd.GeoDataFrame] = []

    def pick(frame, k, label):
        got = _take(rng, frame, k)
        chosen.append(got.assign(stratum=label))

    for reason, grp in df[df.status == "no_fit"].groupby("reason", dropna=False):
        pick(grp, MIN_PER_STRATUM, f"no_fit:{reason}")
    pick(df[df.status == "flagged_town"], MIN_PER_STRATUM, "flagged_town")
    reserved = sum(len(c) for c in chosen)

    odd = df["flags"].fillna("").str.contains("odd_shape")
    pool = df[(df.status.isin(["uncertain"]) | odd) & ~df.status.isin(
        ["ineligible", "flagged_town", "no_fit"])]
    pool_odd, pool_rest = pool[odd[pool.index]], pool[~odd[pool.index]]
    cap = max(0, min(n // 2, n - reserved))
    k_odd = min(len(pool_odd), cap // 2)
    k_rest = min(len(pool_rest), cap - k_odd)
    k_odd = min(len(pool_odd), cap - k_rest)
    pick(pool_odd, k_odd, "odd_shape")
    pick(pool_rest, k_rest, "uncertain")

    used = {pid for c in chosen for pid in c.parcel_id}
    fits = df[(df.status == "fits") & ~df.parcel_id.isin(used)]
    pick(fits, n - sum(len(c) for c in chosen), "fits")

    out = gpd.GeoDataFrame(pd.concat(chosen, ignore_index=True), geometry="geometry", crs=df.crs)
    return out.sort_values("parcel_id").reset_index(drop=True)
