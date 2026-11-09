"""Command line entry point: python -m adu run --area pilot|full [--from STAGE]."""
import argparse
import sys
from pathlib import Path

import geopandas as gpd

from adu.classify import classify_stage
from adu.fetch import fetch_all
from adu.fit import fit_stage
from adu.prepare import prepare

STAGES = ("fetch", "prepare", "classify", "fit")
RAW_NAMES = ("parcels", "zoning", "footprints", "sdat", "zcta", "places")
PREPARED = ("parcels_prepared.parquet", "footprints.parquet", "parcels_neighbors.parquet")
INPUTS = {
    "fetch": lambda area: [],
    "prepare": lambda area: [Path("data/raw") / area / f"{n}.geojson" for n in RAW_NAMES],
    "classify": lambda area: [Path("data/interim") / area / n for n in PREPARED],
    "fit": lambda area: [Path("data/interim") / area / n
                         for n in ("parcels_classified.parquet", *PREPARED[1:])],
}


def print_summary(area: str) -> None:
    df = gpd.read_parquet(Path("data/interim") / area / "parcels_fit.parquet")
    table = df.groupby(["status", "reason"], dropna=False).size().rename("count")
    print(table.to_string())
    print(f"total  {len(df)}")


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    area = args.area
    todo = STAGES[STAGES.index(args.start):]
    missing = [p for p in INPUTS[todo[0]](area) if not p.exists()]
    if missing:
        parser.error(f"--from {todo[0]} needs missing input(s): " + ", ".join(map(str, missing)))

    raw_dir, out_dir = Path("data/raw") / area, Path("data/interim") / area
    for stage in todo:
        print(f"== {stage}")
        if stage == "fetch":
            have_all = all((raw_dir / f"{n}.geojson").exists() for n in RAW_NAMES)
            if have_all and not args.force_fetch:
                print("using existing raw data")
            else:
                fetch_all(area, force=args.force_fetch)
        elif stage == "prepare":
            out_dir.mkdir(parents=True, exist_ok=True)
            prepare(raw_dir, out_dir, area)
        elif stage == "classify":
            classify_stage(area)
        else:
            fit_stage(area)
    print_summary(area)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="adu")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the pipeline stages")
    run.add_argument("--area", choices=("pilot", "full"), required=True)
    run.add_argument("--from", dest="start", choices=STAGES, default="fetch",
                     help="skip the stages before this one and use their existing outputs")
    run.add_argument("--force-fetch", action="store_true", help="re-download raw data")
    viewer = sub.add_parser("viewer", help="build the aerial verification viewer")
    viewer.add_argument("--area", choices=("pilot", "full"), default="pilot")
    args = parser.parse_args(argv)
    if args.command == "run":
        _run(args, parser)
    elif args.command == "viewer":
        from adu.viewer import build_viewer

        out = build_viewer(args.area)
        print(f"wrote {out}/index.html and {out}/sample.geojson")
        print("serve with: python -m http.server 8000")
        print("then open:  http://localhost:8000/viewer/")


if __name__ == "__main__":
    main(sys.argv[1:])
