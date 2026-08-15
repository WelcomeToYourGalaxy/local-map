#!/usr/bin/env python3
"""patch_harvester_crs.py — make federated WFS return degrees, not metres.

THE BUG
-------
The WFS federation asks for features like this:

    {"service":"WFS","version":"1.1.0","request":"GetFeature",
     "typeName":nm,"outputFormat":ofmt,"maxFeatures":per_ds}

No srsName. So every server answers in its OWN native CRS, and most European
services publish in projected metres (EPSG:25830, 31370, 27700, 3857...). Those
coordinates then get written straight into projects.json as lat/lng, which is
how 82,303 records ended up at coordinates like 3129980, 17052115 — off the
map entirely.

THE FIX
-------
1. Ask for CRS84 explicitly: "urn:ogc:def:crs:OGC:1.3:CRS84". Not "EPSG:4326" —
   under WFS 1.1.0 the EPSG code is defined as LATITUDE FIRST, which is exactly
   how the other 16 records ended up transposed. CRS84 is always lon,lat.
2. Refuse anything still out of range at the point of emission, and swap the
   unambiguous transpositions. A server that ignores srsName should lose its
   features, not scatter them.

Idempotent.
"""
import re, sys

MARKER = "# crs-fix (patch_harvester_crs)"

GUARD = '''
# crs-fix (patch_harvester_crs)
# WFS servers answer in their own CRS unless told otherwise, and WFS 1.1.0
# defines EPSG:4326 as lat-first. CRS84 is unambiguous lon,lat degrees.
_WFS_CRS84 = "urn:ogc:def:crs:OGC:1.3:CRS84"


def _ll_ok(lat, lng):
    """A coordinate that cannot exist is a projection leak, not a place."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if abs(lat) <= 90 and abs(lng) <= 180:
        return (lat, lng)
    # unambiguous transposition: latitude cannot exceed 90, longitude can
    if abs(lat) <= 180 and abs(lng) <= 90:
        return (lng, lat)
    return None

'''


def patch(text):
    if MARKER in text:
        return text, "already patched"

    old_fetch = ('{"service": "WFS", "version": "1.1.0", "request": "GetFeature",\n'
                 '                         "typeName": nm, "outputFormat": ofmt, "maxFeatures": per_ds})')
    new_fetch = ('{"service": "WFS", "version": "1.1.0", "request": "GetFeature",\n'
                 '                         "typeName": nm, "outputFormat": ofmt,\n'
                 '                         "srsName": _WFS_CRS84, "maxFeatures": per_ds})')
    if old_fetch not in text:
        raise SystemExit("could not find the WFS GetFeature request — aborting")
    text = text.replace(old_fetch, new_fetch, 1)

    old_src = ('{"service": "WFS", "version": "1.1.0", "request": "GetFeature",\n'
               '                         "typeName": nm, "outputFormat": "application/json",\n'
               '                         "maxFeatures": 50})')
    new_src = ('{"service": "WFS", "version": "1.1.0", "request": "GetFeature",\n'
               '                         "typeName": nm, "outputFormat": "application/json",\n'
               '                         "srsName": _WFS_CRS84, "maxFeatures": 50})')
    if old_src in text:
        text = text.replace(old_src, new_src, 1)

    # emission guard: a server that ignores srsName loses its features
    old_ll = ("                    ll = _geom_center(f.get(\"geometry\") or {})\n"
              "                    if not ll:\n"
              "                        continue")
    new_ll = ("                    ll = _geom_center(f.get(\"geometry\") or {})\n"
              "                    if not ll:\n"
              "                        continue\n"
              "                    ll = _ll_ok(ll[0], ll[1])   # crs-fix\n"
              "                    if not ll:\n"
              "                        continue")
    if old_ll not in text:
        raise SystemExit("could not find the geometry centre call — aborting")
    text = text.replace(old_ll, new_ll, 1)

    text = text.replace("_WFS_KEEP = _re.compile(", GUARD + "\n_WFS_KEEP = _re.compile(", 1)
    return text, "patched"


def selftest():
    fails = []
    ns = {}
    exec(GUARD.replace("# crs-fix (patch_harvester_crs)\n", ""), ns)
    ok = ns["_ll_ok"]

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    eq(ok(51.5, -0.12), (51.5, -0.12), "ll/keeps-valid")
    eq(ok(98.6705, 59.0394), (59.0394, 98.6705), "ll/swaps-transposed")
    eq(ok(3129980.0, 17052115.0), None, "ll/drops-projected")
    eq(ok(None, 5), None, "ll/handles-none")
    eq(ok("51.5", "-0.12"), (51.5, -0.12), "ll/coerces-strings")
    eq(ok(0, 0), (0.0, 0.0), "ll/null-island-is-valid")

    sample = ('x = 1\n'
              '            gu = base + sep + urllib.parse.urlencode(\n'
              '                        {"service": "WFS", "version": "1.1.0", "request": "GetFeature",\n'
              '                         "typeName": nm, "outputFormat": ofmt, "maxFeatures": per_ds})\n'
              '                    ll = _geom_center(f.get("geometry") or {})\n'
              '                    if not ll:\n'
              '                        continue\n'
              '_WFS_KEEP = _re.compile(\n')
    out, st = patch(sample)
    eq(st, "patched", "patch/applies")
    eq('"srsName": _WFS_CRS84' in out, True, "patch/adds-srsname")
    req = out[out.index('"service": "WFS"'):out.index("maxFeatures")]
    eq('"srsName": _WFS_CRS84' in req, True, "patch/request-uses-crs84")
    eq('EPSG:4326' in req, False, "patch/request-avoids-lat-first-epsg")
    eq("_ll_ok(ll[0], ll[1])" in out, True, "patch/guards-emission")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("nothing"); fails.append("patch/missing-anchor not caught")
    except SystemExit:
        pass

    if fails:
        print("SELFTEST FAILED"); [print("  -", f) for f in fails]; return 1
    print("SELFTEST OK (13 checks)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "harvest_projects.py"
    t = open(path, encoding="utf-8").read()
    out, status = patch(t)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
