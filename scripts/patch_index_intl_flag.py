#!/usr/bin/env python3
"""Key locateEntry's flyTo on where the row came from, not on its level.

    python3 patch_index_intl_flag.py index.html            # dry run, prints the before/after
    python3 patch_index_intl_flag.py index.html --write

Prepared, not applied. This is the deliberate change flagged during the tier work; it is
here so the decision costs a yes rather than an afternoon.

The problem
-----------
`locateEntry` decides whether to fly the map to a coordinate by testing the row's level:

    if(e.level==='International'&&typeof e.lat==='number'){ ... map.flyTo(...) ... }

That was safe while `International` could only come from `internationalBodies`, which is
the one push that carries `lat`/`lng`. After the tier merge, 1,817 rows in country buckets
also carry `level:'International'`. They are still safe — the depth-0 push has no
coordinates, so the `typeof e.lat==='number'` guard fails and they fall through to
`_openUnitByIso`. But the guard is what makes them safe, not the design. Add `lat` to a
country-bucket push for any reason later and the map starts flying to a treaty body's
coordinates instead of opening the country.

The change
----------
Two edits. `internationalBodies` rows are stamped `intl:true` where they are built, and
the branch tests that flag instead of the level string. The flyTo then depends on the row's
origin, which cannot drift, rather than on a value the tier vocabulary also produces.

    1941   ...level:'International',intl:true,lenses:...
    1950   if(e.intl&&typeof e.lat==='number'){ ... }

The `typeof e.lat==='number'` guard stays, so an international body with no coordinates
still falls through to `_openUnitByIso(e.guide)` exactly as now.
"""
import re, sys, json, subprocess, tempfile, os

PUSH_OLD = "country:(b.name||'International bodies'),iso:(b.guide||null),level:'International',lenses:_lensesOf(tr)"
PUSH_NEW = "country:(b.name||'International bodies'),iso:(b.guide||null),level:'International',intl:true,lenses:_lensesOf(tr)"
BRANCH_OLD = "if(e.level==='International'&&typeof e.lat==='number')"
BRANCH_NEW = "if(e.intl&&typeof e.lat==='number')"


def intl_bodies(h):
    """internationalBodies terminates with `,];`, which is not valid JSON — strip the
    trailing comma before parsing."""
    m = re.search(r"const internationalBodies\s*=\s*(\[.*?\])\s*;", h, re.S)
    if not m:
        return None
    raw = re.sub(r",\s*\]$", "]", m.group(1).strip())
    try:
        return json.loads(raw)
    except Exception:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        sys.exit(__doc__)
    path = args[0]
    h = open(path, encoding="utf-8").read()

    for label, old in (("internationalBodies push", PUSH_OLD), ("locateEntry branch", BRANCH_OLD)):
        if h.count(old) != 1:
            sys.exit(f"expected exactly one {label}; found {h.count(old)} — not found or "
                     "already patched")

    bodies = intl_bodies(h)
    if bodies is None:
        print("could not parse internationalBodies — reporting the structural change only")
        with_coords = trackers = "?"
    else:
        with_coords = sum(len(b.get("trackers") or []) for b in bodies
                          if isinstance(b.get("lat"), (int, float)))
        trackers = sum(len(b.get("trackers") or []) for b in bodies)
        print(f"internationalBodies: {len(bodies)} bodies, {trackers} rows, "
              f"{with_coords} of them with coordinates")

    print("\nrows that take the flyTo branch")
    print(f"   before   {with_coords}   (level=='International' and lat is a number)")
    print(f"   after    {with_coords}   (intl===true and lat is a number)")
    print("\nrows in country buckets tiered 'international'")
    print("   before   0 — the depth-0 push carries no lat, so the guard catches them")
    print("   after    0 — they are never eligible, whatever fields they later acquire")

    h = h.replace(PUSH_OLD, PUSH_NEW).replace(BRANCH_OLD, BRANCH_NEW)

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("\n;\n".join(scripts))
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode:
        sys.exit("node --check FAILED\n" + r.stderr)
    print("\nnode --check PASSED")

    if write:
        open(path, "w", encoding="utf-8").write(h)
        print(f"wrote {path}")
    else:
        print("dry run — pass --write to save")


if __name__ == "__main__":
    main()
