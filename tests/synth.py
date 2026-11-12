"""Synthetic raw-data builders (EPSG:2248 geometry, written as EPSG:4326 GeoJSON)."""
import geopandas as gpd
from shapely.geometry import Polygon, box

from adu.config import load_sources

X0, Y0 = 1284000.0, 473000.0  # near the pilot area, Maryland State Plane feet
CRS = "EPSG:2248"
RUN_CFG = {"pilot_bbox_lonlat": [-77.2, 38.9, -77.0, 39.0]}


def rect(x, y, w, h):
    return box(X0 + x, Y0 + y, X0 + x + w, Y0 + y + h)


class RawBuilder:
    def __init__(self, tmp_path):
        self.dir = tmp_path / "raw"
        self.dir.mkdir()
        self.s = load_sources()
        self.parcels, self.zoning, self.footprints, self.sdat = [], [], [], []
        self.zcta = [rect(-500, -500, 3000, 3000)]
        self.places = []
        self.towns = []

    def parcel(self, geom, oid, acct="00000001", district="07"):
        f = self.s["parcels"]["fields"]
        self.parcels.append({f["parcel_id"]: oid, f["sdat_account"]: acct, f["sdat_district"]: district, "geometry": geom})

    def zone(self, geom, code):
        self.zoning.append({self.s["zoning"]["fields"]["zone"]: code, "geometry": geom})

    def footprint(self, geom, status=""):
        self.footprints.append({self.s["footprints"]["fields"]["status"]: status, "geometry": geom})

    def sdat_row(self, acctid, living=1500.0, land_use="R", structure="C101", address="1 TEST ST"):
        f = self.s["sdat"]["fields"]
        self.sdat.append({f["sdat_account"]: acctid, f["land_use"]: land_use, f["structure"]: structure,
                          f["living_area"]: living, f["address"]: address, "geometry": None})

    def place(self, geom, name):
        self.places.append({self.s["places"]["fields"]["name"]: name, "geometry": geom})

    def write(self):
        def dump(rows, name, cols):
            gdf = gpd.GeoDataFrame(rows, columns=cols + ["geometry"], geometry="geometry", crs=CRS)
            gdf.to_crs("EPSG:4326").to_file(self.dir / f"{name}.geojson", driver="GeoJSON")

        f = self.s
        dump(self.parcels, "parcels", [f["parcels"]["fields"][k] for k in ("parcel_id", "sdat_account", "sdat_district")])
        dump(self.zoning, "zoning", [f["zoning"]["fields"]["zone"]])
        dump(self.footprints, "footprints", [f["footprints"]["fields"]["status"]])
        sd = gpd.GeoDataFrame(self.sdat, geometry=[rect(0, 0, 1, 1).centroid] * len(self.sdat), crs=CRS)
        sd.to_crs("EPSG:4326").to_file(self.dir / "sdat.geojson", driver="GeoJSON")
        dump([{f["zcta"]["fields"]["zcta"]: "20816", "geometry": g} for g in self.zcta], "zcta", [f["zcta"]["fields"]["zcta"]])
        dump(self.places, "places", [f["places"]["fields"]["name"]])
        return self.dir


def bowtie():
    return Polygon([(X0, Y0), (X0 + 100, Y0 + 100), (X0 + 100, Y0), (X0, Y0 + 100)])
