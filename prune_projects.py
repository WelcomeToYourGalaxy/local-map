#!/usr/bin/env python3
"""
prune_projects.py — remove map layers that were ingested as if they were projects.

THE FAILURE MODE
----------------
ArcGIS Hub and Socrata publish *datasets*, not projects. When a harvested
feature has no usable per-feature name, the ingester falls back to the DATASET
title, so a single environmental-assessment layer becomes hundreds of identical
pins — e.g. "Diagnostico Ambiental da Fiscalizacao - Fatores de Pressao (2023)".
Because the features are grid-cell or sample-point centroids, they render as a
visible lattice, which is the tell the user sees.

Two independent detectors, deliberately conservative:
  A. LATTICE     same name+source, >=8 points, dominant regular spacing on both
                 axes. Real projects are never evenly spaced.
  B. LAYER TITLE dataset-shaped title (trailing "(YYYY)", survey/inventory/
                 zoning vocabulary in EN/PT/ES) AND repeated >=REPEAT times.
                 The repeat requirement is what stops it eating real projects
                 that merely have a year in the name.

Nothing is deleted silently: every removal is written to a report with the
detector that caught it, so a wrong call is visible and reversible.

USAGE
  python3 prune_projects.py --in projects.json --out projects.json \\
      --report prune_report.json [--dry-run]
  python3 prune_projects.py --selftest
"""

import argparse
import collections
import json
import re
import sys

# Layer/dataset vocabulary. English, Portuguese, Spanish, French.
LAYER_WORDS = re.compile(
    r"\b("
    r"diagn[oó]stic[oa]s?|fatores?\s+de\s+press[aã]o|invent[aá]ri[oa]s?|"
    r"zoneamento|zonificaci[oó]n|monitoramento|monitoreo|"
    r"uso\s+e\s+ocupa[cç][aã]o|cobertura\s+vegetal|base\s+cartogr[aá]fica|"
    r"malha\s+\w+|grade\s+de|camadas?|"
    r"inventory|land\s*cover|landcover|basemap|base\s+map|"
    r"survey\s+points?|sample\s+points?|monitoring\s+(sites?|points?|network)|"
    r"census\s+blocks?|parcels?\s+layer|zoning\s+districts?|"
    r"couverture|donn[ée]es\s+de"
    r")\b", re.I)

YEAR_TAIL = re.compile(r"\(\s*(19|20)\d{2}\s*\)\s*$")

# Regulator survey and diagnostic products: not proposals, not sites. The
# harvester's _SURVEY_LAYER filter now refuses these at ingest, so any already
# in the file are dropped rather than renamed - otherwise the data contradicts
# the ingester that produced it.
SURVEY_TITLE = re.compile(
    r"(diagn[o\u00f3]stic|fatores? ?de ?press|fiscaliza|monitoramento|monitoreo|"
    r"invent[a\u00e1]ri|inventario|zoneamento|zonificaci|potencialidades|riscos|"
    r"uso ?e ?ocupa|cobertura ?vegetal|zoning districts?|concesiones de agua|"
    r"socioambiental|base ?cartogr)", re.I)

DEFAULT_REPEAT = 8
DEFAULT_MIN_STEP = 0.0005     # ~55 m; below this it is coordinate noise
DEFAULT_DOMINANCE = 0.6       # share of gaps that must equal the modal gap


def _axis_regular(values, min_step, dominance):
    vals = sorted(set(round(v, 6) for v in values))
    if len(vals) < 4:
        return False
    gaps = [round(vals[i + 1] - vals[i], 6) for i in range(len(vals) - 1)]
    step, n = collections.Counter(gaps).most_common(1)[0]
    return step >= min_step and (n / len(gaps)) >= dominance


def is_lattice(items, repeat=DEFAULT_REPEAT, min_step=DEFAULT_MIN_STEP,
               dominance=DEFAULT_DOMINANCE):
    """True when points sit on a regular grid — i.e. cell centroids, not sites."""
    pts = [i for i in items if i.get("lat") is not None and i.get("lng") is not None]
    if len(pts) < repeat:
        return False
    return (_axis_regular([p["lat"] for p in pts], min_step, dominance)
            and _axis_regular([p["lng"] for p in pts], min_step, dominance))


def is_layer_title(name, count, repeat=DEFAULT_REPEAT):
    """True when the title reads as a dataset AND it repeats like one."""
    if not name or count < repeat:
        return False
    return bool(LAYER_WORDS.search(name) or YEAR_TAIL.search(name))


def coords_collapsed(items, tol=0.0002):
    """True when a whole group sits on one point (a dataset centroid) rather
    than on distinct real locations."""
    pts = [(round(i["lat"], 4), round(i["lng"], 4)) for i in items
           if i.get("lat") is not None]
    return len(set(pts)) <= max(1, len(pts) // 50)


def relabel(item):
    """A real feature that inherited its dataset's title. Keep the point, fix
    the name — deleting it would throw away a genuine permit or site.

    The replacement must still identify the pin: bare "New construction" on 611
    markers is no more useful than the dataset title it replaced. Keep the type,
    the place if the record has one, and the year if the title carried one."""
    typ = (item.get("type") or "").strip()
    place = str(item.get("state") or "").strip()
    # `type` sometimes carries the dataset title too; never echo it back, and
    # never repeat the place twice.
    if typ and (SURVEY_TITLE.search(typ) or YEAR_TAIL.search(typ) or len(typ) > 60):
        typ = ""
    bits = [typ or "Project"]
    if place and place.lower() not in bits[0].lower():
        bits.append(place)
    name = " — ".join(bits)
    m = re.search(r"(19|20)\d{2}", str(item.get("name") or ""))
    if m:
        name += f" ({m.group(0)})"
    return name


def analyse(projects, repeat=DEFAULT_REPEAT):
    groups = collections.defaultdict(list)
    for idx, p in enumerate(projects):
        groups[(p.get("name"), p.get("source"))].append(idx)

    drop, rename, findings = set(), {}, []
    for (name, source), idxs in groups.items():
        items = [projects[i] for i in idxs]
        why = action = None
        if is_lattice(items, repeat):
            why, action = "lattice", "drop"
        elif name and SURVEY_TITLE.search(name) and len(idxs) >= repeat:
            why, action = "survey_layer", "drop"
        elif is_layer_title(name, len(idxs), repeat):
            why = "layer_title"
            # Distinct real coordinates => real features with a borrowed title.
            # Collapsed coordinates => the dataset itself, pinned once per row.
            action = "drop" if coords_collapsed(items) else "relabel"
        if not why:
            continue
        findings.append({"name": name, "source": source, "count": len(idxs),
                         "detector": why, "action": action,
                         "sample_url": items[0].get("url", "")})
        if action == "drop":
            drop.update(idxs)
        else:
            for i in idxs:
                rename[i] = relabel(projects[i])
    findings.sort(key=lambda f: -f["count"])
    return drop, rename, findings


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    # a 4x4 grid of cell centroids at 0.01 deg
    grid = [{"lat": -3.0 + 0.01 * r, "lng": -60.0 + 0.01 * c}
            for r in range(4) for c in range(4)]
    eq(is_lattice(grid), True, "lattice/detects-grid")

    # real projects: irregular positions, same name
    import random
    random.seed(7)
    scatter = [{"lat": -3 + random.random(), "lng": -60 + random.random()}
               for _ in range(20)]
    eq(is_lattice(scatter), False, "lattice/spares-scatter")

    # tight cluster (same site, GPS jitter) must not be called a grid
    jitter = [{"lat": -3 + 0.00001 * i, "lng": -60 + 0.00001 * i} for i in range(30)]
    eq(is_lattice(jitter), False, "lattice/spares-jitter")

    eq(is_lattice(grid[:5]), False, "lattice/needs-repeat")

    eq(is_layer_title("Diagnóstico Ambiental da Fiscalização - "
                      "Fatores de Pressão (2023)", 40), True, "title/pt-dataset")
    eq(is_layer_title("Inventário Florestal (2019)", 12), True, "title/inventario")
    eq(is_layer_title("Land Cover 2020", 30), True, "title/landcover")
    eq(is_layer_title("Diagnóstico Ambiental (2023)", 3), False, "title/needs-repeat")
    eq(is_layer_title("Ferrovia de Integração Oeste-Leste", 41), False,
       "title/spares-real-repeated-project")
    eq(is_layer_title("Belo Monte Dam (2011)", 1), False, "title/spares-single")
    eq(is_layer_title("Upgrade of Rechnaya substation", 20), False,
       "title/spares-upgrade-word")
    eq(is_layer_title("State Route 46 - Antelope Grade Section", 20), False,
       "title/spares-grade-word")

    projects = [{"name": "Grid Layer (2023)", "source": "arcgis_hub",
                 "lat": -3 + 0.01 * r, "lng": -60 + 0.01 * c}
                for r in range(4) for c in range(4)]
    projects.append({"name": "Real Dam", "source": "gem", "lat": -5, "lng": -55})
    drop, rename, findings = analyse(projects)
    eq(len(drop), 16, "analyse/drops-grid-only")
    eq(findings[0]["count"], 16, "analyse/report-count")

    # real permits carrying a dataset title: relabel, never delete
    permits = [{"name": "Building Permits for New Construction (2023)",
                "source": "arcgis_hub", "type": "New construction",
                "state": "Massachusetts",
                "lat": 42.0 + random.random(), "lng": -71.0 - random.random()}
               for i in range(20)]
    d2, r2, f2 = analyse(permits)
    eq(len(d2), 0, "analyse/keeps-real-permits")
    eq(len(r2), 20, "analyse/relabels-real-permits")
    eq(sorted(r2.values())[0], "New construction — Massachusetts (2023)",
       "analyse/relabel-text")
    eq(relabel({"type": "New construction", "name": "Permits (2020)"}),
       "New construction (2020)", "relabel/keeps-year-without-state")
    eq(relabel({"name": "no year here"}), "Project", "relabel/fallback")
    eq(relabel({"type": "New construction", "state": "Massachusetts",
                "name": "Building Permits for New Construction (2023)"}),
       "New construction — Massachusetts (2023)", "reheal/recovers-year")
    eq(relabel({"type": "Diagnóstico Ambiental da Fiscalização - Fatores",
                "state": "Brazil", "name": "x (2023)"}),
       "Project — Brazil (2023)", "relabel/refuses-dataset-title-as-type")
    eq(relabel({"type": "Permit / development (Canada)", "state": "Canada",
                "name": "zoning districts"}),
       "Permit / development (Canada)", "relabel/no-duplicate-place")
    eq(bool(SURVEY_TITLE.search("Diagnóstico Socioambiental - Riscos")), True,
       "survey/detects-diagnostic")
    eq(bool(SURVEY_TITLE.search("Building Permits for New Construction (2020)")),
       False, "survey/spares-real-permits")
    eq(f2[0]["action"], "relabel", "analyse/action-relabel")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (25 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="projects.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--report", default="prune_report.json")
    ap.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    ap.add_argument("--reheal", action="store_true",
                    help="re-derive names for records already relabelled, using orig_name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    with open(args.inp) as fh:
        data = json.load(fh)
    projects = data["projects"] if isinstance(data, dict) else data

    if args.reheal:
        # An earlier relabel wrote a bare type ("New construction") over the
        # dataset title and kept the original in orig_name. The year is still
        # recoverable from there, so re-derive rather than leave 611 identical
        # pins. Only touches records that already carry orig_name.
        healed = 0
        for p in projects:
            if not p.get("orig_name"):
                continue
            better = relabel({**p, "name": p["orig_name"]})
            if better != p.get("name"):
                p["name"] = better
                healed += 1
        print(f"rehealed {healed} previously relabelled records")
        if args.out and not args.dry_run:
            if isinstance(data, dict):
                data["projects"] = projects
            with open(args.out, "w") as fh:
                json.dump(data if isinstance(data, dict) else projects, fh,
                          ensure_ascii=False, separators=(",", ":"))
            print(f"wrote {args.out}")
        return 0

    drop, rename, findings = analyse(projects, args.repeat)
    kept = []
    for i, p in enumerate(projects):
        if i in drop:
            continue
        if i in rename:
            p = dict(p, name=rename[i], orig_name=p.get("name"))
        kept.append(p)

    with open(args.report, "w") as fh:
        json.dump({"input_count": len(projects), "dropped": len(drop),
                   "relabelled": sum(1 for p in kept if p.get("orig_name")),
                   "kept": len(kept),
                   "groups": findings},
                  fh, indent=1, ensure_ascii=False)

    relabelled = sum(1 for p in kept if p.get("orig_name"))
    if relabelled != len(rename):
        print(f"warning: planned {len(rename)} relabels but wrote {relabelled}",
              file=sys.stderr)
    print(f"input {len(projects)} | dropped {len(drop)} | "
          f"relabelled {relabelled} | kept {len(kept)}")
    for f in findings[:15]:
        print(f"  {f['count']:6d}  {f['action']:8s} {f['detector']:11s} "
              f"{f['source']:18s} {str(f['name'])[:44]}")
    print(f"report -> {args.report}")

    if args.dry_run or not args.out:
        print("(dry run — nothing written)")
        return 0

    if isinstance(data, dict):
        data["projects"] = kept
        data.setdefault("_meta", {})["count"] = len(kept)
        data["_meta"]["pruned"] = len(drop)
    else:
        data = kept
    with open(args.out, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
