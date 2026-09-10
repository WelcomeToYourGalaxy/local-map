#!/usr/bin/env python3
"""Fix the three tier defects in the level machinery.

    python3 patch_index_tier_levels.py index.html            # dry run
    python3 patch_index_tier_levels.py index.html --write

Three edits:

1. `_tierLabel` blind-capitalises the stored value, so `subnational` becomes `'Subnational'`,
   which is not one of the five strings in `LEVELS`. `activeLevels` is built from `LEVELS`,
   so `activeLevels.has('Subnational')` is false under every filter combination and the entry
   is invisible on the map and in the side panel. Replaced with an alias map; unknown values
   fall back to a bin instead of vanishing.

2. `tagLevels` hardcodes `t._lvl='National'` for every depth-0 entry, so `tier` is never read
   at country level — which is where 7,508 of the 8,563 entries live. Now reads it, defaulting
   to National when absent.

3. `buildIndexData` hardcodes `level:'National'` in the same place, for the side panel and the
   level-pill counts. Fixed the same way, computed inline from `tr.tier` rather than read from
   `t._lvl`, because `levelCounts()` can call `buildIndexData()` before `tagLevels()` has run.

Refuses to double-apply. Runs `node --check` on the concatenated script blocks before writing.
"""
import re, sys, subprocess, tempfile, os

ALIAS = """const _TIER_ALIAS={subnational:'State','sub-national':'State',provincial:'State',province:'State',region:'State',regional:'State',state:'State',district:'County',departmental:'County',county:'County',city:'Municipal',commune:'Municipal',local:'Municipal',municipal:'Municipal',national:'National',supranational:'International',global:'International',international:'International'};
function _tierLabel(t){ if(!t) return 'State'; const k=String(t).toLowerCase().trim(); return _TIER_ALIAS[k] || 'State'; }"""

EDITS = [
    ("_tierLabel",
     "function _tierLabel(t){ if(!t) return 'State'; return t.charAt(0).toUpperCase()+t.slice(1); }",
     ALIAS),
    ("tagLevels depth-0",
     "(c.trackers||[]).forEach(t=>{ t._lvl='National'; });",
     "(c.trackers||[]).forEach(t=>{ t._lvl = t.tier ? _tierLabel(t.tier) : 'National'; });"),
    ("buildIndexData depth-0",
     "(c.trackers||[]).forEach(tr=>INDEXDATA.push({name:tr.name,url:tr.url,country:cn,iso:iso,level:'National',",
     "(c.trackers||[]).forEach(tr=>INDEXDATA.push({name:tr.name,url:tr.url,country:cn,iso:iso,level:(tr.tier?_tierLabel(tr.tier):'National'),"),
]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        sys.exit(__doc__)
    path = args[0]
    h = open(path, encoding="utf-8").read()

    for label, old, _ in EDITS:
        if h.count(old) != 1:
            sys.exit(f"expected exactly one {label} anchor; found {h.count(old)} — "
                     "not found or already patched")

    for label, old, new in EDITS:
        h = h.replace(old, new)
        print(f"  patched {label}")

    left = h.count("level:'National'")
    print(f"  remaining hardcoded level:'National': {left}")

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("\n;\n".join(scripts))
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode:
        sys.exit("node --check FAILED\n" + r.stderr)
    print("  node --check PASSED")

    if write:
        open(path, "w", encoding="utf-8").write(h)
        print(f"wrote {path}")
    else:
        print("dry run — pass --write to save")


if __name__ == "__main__":
    main()
