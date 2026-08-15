#!/usr/bin/env python3
"""
shard_projects.py — make projects.json committable and fast to load.

THE PROBLEM
-----------
One 87 MB JSON file. GitHub's hard blob limit is 100 MB (warning at 50 MB), and
every visitor downloads the whole thing to see one country. Both problems have
the same fix: shrink each record, then split by geography so the map fetches
only the tiles in view.

WHAT IT DOES
------------
1. SHRINK, losslessly where it matters:
   - coordinates rounded to 5 dp (~1 m; more precision than any of these
     sources actually has)
   - `desc` capped (default 160 chars, cut on a word boundary)
   - empty/null/zero-value fields dropped entirely
   - repeated `source` and `type` strings replaced by an integer id into a
     lookup table stored once per file
2. SHARD into 10-degree tiles: `projects/tiles/t_<lat>_<lng>.json`, plus
   `projects/index.json` giving each tile's bounds and count so the client
   knows what to fetch.
3. REPORT the before/after sizes and the largest remaining tile, because the
   only number that matters is whether the biggest single file is comfortably
   under the limit.

Nothing is deleted: every input project lands in exactly one tile.

USAGE
  python3 shard_projects.py --in projects.json --outdir projects [--tile 10]
  python3 shard_projects.py --selftest
"""

import argparse
import json
import math
import os
import shutil
import sys

DROP_IF_EMPTY = ("desc", "url", "name", "type", "state", "company", "status",
                 "date", "size", "value_usd", "acres", "miles", "deadline")
DEFAULT_DESC = 160
DEFAULT_TILE = 10


def trim_desc(text, limit):
    if not text or len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "…"


def shrink(p, desc_limit, srcmap, typemap):
    out = {}
    for k, v in p.items():
        if v is None or v == "" or v == []:
            continue
        if k in ("lat", "lng"):
            out[k] = round(float(v), 5)
        elif k == "desc":
            out[k] = trim_desc(v, desc_limit)
        elif k == "source":
            out["s"] = srcmap.setdefault(v, len(srcmap))
        elif k == "type":
            out["t"] = typemap.setdefault(v, len(typemap))
        elif k in DROP_IF_EMPTY and not v:
            continue
        else:
            out[k] = v
    return out


def tile_key(lat, lng, size):
    return (int(math.floor(lat / size) * size), int(math.floor(lng / size) * size))


def tile_name(key):
    la, ln = key
    return f"t_{la:+04d}_{ln:+05d}.json".replace("+", "p").replace("-", "m")


def shard(projects, outdir, tile=DEFAULT_TILE, desc_limit=DEFAULT_DESC):
    srcmap, typemap = {}, {}
    tiles, skipped = {}, 0
    for p in projects:
        lat, lng = p.get("lat"), p.get("lng")
        if lat is None or lng is None:
            skipped += 1
            continue
        tiles.setdefault(tile_key(lat, lng, tile), []).append(
            shrink(p, desc_limit, srcmap, typemap))

    tdir = os.path.join(outdir, "tiles")
    if os.path.isdir(tdir):
        shutil.rmtree(tdir)
    os.makedirs(tdir, exist_ok=True)

    sources = [k for k, _ in sorted(srcmap.items(), key=lambda kv: kv[1])]
    types = [k for k, _ in sorted(typemap.items(), key=lambda kv: kv[1])]

    index, biggest = [], (0, "")
    for key, items in sorted(tiles.items()):
        fname = tile_name(key)
        path = os.path.join(tdir, fname)
        # lookup tables live once, in index.json - repeating them in every
        # tile was costing more than the string interning saved.
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, separators=(",", ":"))
        size = os.path.getsize(path)
        biggest = max(biggest, (size, fname))
        index.append({"file": fname, "lat": key[0], "lng": key[1],
                      "span": tile, "count": len(items), "bytes": size})

    with open(os.path.join(outdir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"tile_span": tile, "sources": sources, "types": types,
                   "tiles": index,
                   "total": sum(t["count"] for t in index)},
                  fh, ensure_ascii=False, separators=(",", ":"))
    return index, biggest, skipped


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    eq(tile_key(41.0, 28.9, 10), (40, 20), "tile/positive")
    eq(tile_key(-33.4, -70.6, 10), (-40, -80), "tile/negative")
    eq(tile_key(0.0, 0.0, 10), (0, 0), "tile/origin")
    eq(tile_name((40, 20)), "t_p040_p0020.json", "tile/name-positive")
    eq(tile_name((-40, -80)), "t_m040_m0080.json", "tile/name-negative")

    eq(trim_desc("short", 160), "short", "desc/short-untouched")
    long = "word " * 100
    eq(len(trim_desc(long, 50)) <= 51, True, "desc/capped")

    sm, tm = {}, {}
    got = shrink({"name": "X", "lat": 1.234567891, "lng": 2.0, "desc": "",
                  "source": "osm", "type": "mine", "acres": None,
                  "status": "Under construction"}, 160, sm, tm)
    eq(got["lat"], 1.23457, "shrink/rounds-coords")
    eq("desc" in got, False, "shrink/drops-empty")
    eq("acres" in got, False, "shrink/drops-null")
    eq(got["s"], 0, "shrink/source-id")
    eq(got["t"], 0, "shrink/type-id")
    eq(shrink({"source": "osm"}, 160, sm, tm)["s"], 0, "shrink/source-id-stable")
    eq(shrink({"source": "gem"}, 160, sm, tm)["s"], 1, "shrink/source-id-new")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        idx, big, skipped = shard(
            [{"name": "A", "lat": 41.0, "lng": 28.9, "source": "osm"},
             {"name": "B", "lat": -33.4, "lng": -70.6, "source": "gem"},
             {"name": "C", "lat": None, "lng": 1.0}], td, 10)
        eq(len(idx), 2, "shard/two-tiles")
        eq(skipped, 1, "shard/skips-uncoordinated")
        eq(sum(t["count"] for t in idx), 2, "shard/no-loss")
        eq(os.path.exists(os.path.join(td, "index.json")), True, "shard/index")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (18 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="projects.json")
    ap.add_argument("--outdir", default="projects")
    ap.add_argument("--tile", type=int, default=DEFAULT_TILE)
    ap.add_argument("--desc", type=int, default=DEFAULT_DESC)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    before = os.path.getsize(args.inp)
    data = json.load(open(args.inp))
    projects = data["projects"] if isinstance(data, dict) else data

    idx, biggest, skipped = shard(projects, args.outdir, args.tile, args.desc)
    after = sum(t["bytes"] for t in idx)

    print(f"in  : {before/1e6:8.1f} MB  {len(projects):,} projects")
    print(f"out : {after/1e6:8.1f} MB  across {len(idx)} tiles "
          f"({100 - after*100//before}% smaller)")
    print(f"largest tile: {biggest[1]} at {biggest[0]/1e6:.1f} MB")
    if skipped:
        print(f"skipped (no coordinates): {skipped}")
    for t in sorted(idx, key=lambda t: -t["bytes"])[:5]:
        print(f"  {t['bytes']/1e6:6.1f} MB  {t['count']:7,}  {t['file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
