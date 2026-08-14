"""isogate.py — is this coordinate inside this country, and which admin-1?

projects.json carries no country field, so a Turkish headline could match a
Chilean project. This closes that hole using the cgaz admin-1 boundaries the
repo already hosts. Country membership = inside any of its admin-1 polygons,
which also yields the region name, so wire's `region` can be checked too.

Boundaries are fetched on demand and cached; only ISOs actually needed are
downloaded.
"""
import json, os, urllib.request

BASE = ("https://raw.githubusercontent.com/WelcomeToYourGalaxy/"
        "cgaz-boundaries/main/{iso}.geojson")


def _rings(geom):
    t = geom.get("type")
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return geom["coordinates"]
    return []


def _bbox(polys):
    xs, ys = [], []
    for poly in polys:
        for x, y in poly[0]:
            xs.append(x); ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            xint = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xint:
                inside = not inside
    return inside


def _in_poly(x, y, poly):
    if not _in_ring(x, y, poly[0]):
        return False
    return not any(_in_ring(x, y, hole) for hole in poly[1:])


class IsoGate:
    def __init__(self, cache_dir="boundary_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._loaded = {}

    def _load(self, iso):
        if iso in self._loaded:
            return self._loaded[iso]
        path = os.path.join(self.cache_dir, f"{iso}.geojson")
        if not os.path.exists(path):
            try:
                urllib.request.urlretrieve(BASE.format(iso=iso), path)
            except Exception:
                self._loaded[iso] = None
                return None
        try:
            gj = json.load(open(path))
        except Exception:
            self._loaded[iso] = None
            return None
        units = []
        for f in gj.get("features", []):
            polys = _rings(f.get("geometry") or {})
            if not polys:
                continue
            units.append((f.get("properties", {}).get("shapeName", ""),
                          _bbox(polys), polys))
        self._loaded[iso] = units
        return units

    def locate(self, iso, lat, lng):
        """Return admin-1 name if the point is in this country, else None."""
        units = self._load(iso)
        if not units:
            return None
        for name, bb, polys in units:
            if bb and not (bb[0] <= lng <= bb[2] and bb[1] <= lat <= bb[3]):
                continue
            for poly in polys:
                if _in_poly(lng, lat, poly):
                    return name or ""
        return None

    def in_country(self, iso, lat, lng):
        return self.locate(iso, lat, lng) is not None
