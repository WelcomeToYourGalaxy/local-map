#!/usr/bin/env python3
"""
coverage_report.py — totals per tag per level of government, worldwide.

WHY TIER AND NOT NESTING DEPTH
The file marks level in TWO places and they disagree. Nesting depth gives national /
admin-1 / admin-2. The `tier` field gives subnational / county / municipal. Counting by
depth alone MISSES THE MUNICIPAL LAYER ENTIRELY, because municipal entries are marked by
tier, not by being nested three deep.
This report resolves level as: TIER IF PRESENT, DEPTH OTHERWISE. That is the only way to
see the municipal row at all.

A CORRECTION TO THIS TOOL'S OWN EARLIER BEHAVIOUR
It previously flagged EVERY depth/tier disagreement as an anomaly, and reported 30. On
inspection those were three classes, and only two were defects (both since fixed):
  * CLASS A - national/global funders wrongly tiered subnational: a real defect, fixed.
  * CLASS B - entries nested at county depth but tiered subnational: a real defect, fixed;
    it had undercounted the county layer by nine.
  * CLASS C - NATIONAL ENTRIES CARRYING A LOCAL TIER. NOT A DEFECT. These are nationally
    established mechanisms that a citizen accesses at their district or commune - Luxembourg's
    Pacte Nature, Brazil's Defensoria Publica, Japan's municipal green-space designations,
    legal aid district offices in six countries. The entry belongs at the country node
    because the mechanism is national; the tier says WHICH LEVEL THE READER WILL DEAL WITH,
    and someone filtering for "municipal" SHOULD find Pacte Nature.
    THE TOOL WAS WRONG, NOT THE DATA. Class C is now counted at its tier and reported
    separately as "national mechanisms exercised locally", not as an anomaly.
Run with `--anomalies` to list any remaining genuine disagreements.

Usage:
  python3 coverage_report.py trackerdata.json
  python3 coverage_report.py trackerdata.json --anomalies
"""
import json, sys
from collections import Counter, defaultdict

DEPTH_NAME = {0: "national", 1: "admin-1", 2: "admin-2", 3: "admin-3"}
# tier values map onto the level names used in the report
TIER_NAME = {"subnational": "admin-1", "county": "county", "municipal": "municipal"}
ORDER = ["national", "admin-1", "county", "municipal", "admin-2", "admin-3"]


def level_of(tracker, depth):
    """tier wins where present; depth is the fallback."""
    t = tracker.get("tier")
    if t in TIER_NAME:
        return TIER_NAME[t]
    return DEPTH_NAME.get(depth, "admin-3")


def collect(d):
    per = defaultdict(Counter)
    entries = Counter()
    anomalies = []
    local = []
    for iso, c in d.items():
        def w(n, depth, path):
            for t in n.get("trackers", []):
                lv = level_of(t, depth)
                entries[lv] += 1
                for tg in t.get("tags", []):
                    per[tg][lv] += 1
                tier = t.get("tier")
                if depth == 0 and tier in TIER_NAME:
                    # CLASS C: a national mechanism exercised locally - correct, not an error
                    local.append((path, tier, t.get("name", "")[:44]))
                elif depth >= 2 and tier == "subnational":
                    anomalies.append(("deep-but-admin1", path, tier,
                                      t.get("name", "")[:44]))
            for k, s in n.get("sub", {}).items():
                w(s, depth + 1, path + "/" + k)
        w(c, 0, iso)
    return per, entries, anomalies, local


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "trackerdata.json"
    show_anom = "--anomalies" in sys.argv
    d = json.load(open(src, encoding="utf-8"))
    per, entries, anomalies, local = collect(d)

    levels = [l for l in ORDER if entries[l] or any(per[t][l] for t in per)]
    w = max(len(k) for k in per)
    head = f"{'tag':{w}}" + "".join(f"{l:>11}" for l in levels) + f"{'TOTAL':>9}"
    print(head)
    print("-" * len(head))
    tot = Counter()
    for tag, counts in sorted(per.items(), key=lambda kv: -sum(kv[1].values())):
        t = sum(counts.values())
        row = f"{tag:{w}}" + "".join(f"{counts[l]:>11}" for l in levels) + f"{t:>9}"
        for l in levels:
            tot[l] += counts[l]
        tot["T"] += t
        print(row)
    print("-" * len(head))
    print(f"{'TOTAL TAG APPLICATIONS':{w}}"
          + "".join(f"{tot[l]:>11}" for l in levels) + f"{tot['T']:>9}")
    print(f"{'ENTRIES (distinct)':{w}}"
          + "".join(f"{entries[l]:>11}" for l in levels)
          + f"{sum(entries.values()):>9}")

    print(f"\nnational mechanisms exercised locally: {len(local)}  (counted at their tier)")
    if show_anom:
        for path, tier, name in local:
            print(f"   {path:6} tier={tier:11} {name}")
    print(f"level-marking anomalies: {len(anomalies)}"
          + ("" if show_anom else "   (run with --anomalies to list)"))
    if show_anom:
        for kind, path, tier, name in anomalies:
            print(f"   {kind:18} {path:22} tier={tier:12} {name}")


if __name__ == "__main__":
    main()
