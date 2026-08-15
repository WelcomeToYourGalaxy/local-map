#!/usr/bin/env python3
"""
merge_trackerdata.py — restore entries lost when a stale baseline overwrote main.

SITUATION
---------
The live trackerdata.json was written back from a copy that predated a large
national build-out. 1,996 entries present in a later copy are absent from live;
416 entries added since exist only on live. Neither file is a superset.

WHAT THIS DOES
--------------
A union merge keyed on (node path, normalised URL):
  - entries in BOTH   -> LIVE version wins (it is the newer edit, and other
                         chats may have retagged or rewritten it)
  - LIVE only         -> kept untouched
  - RESTORE only      -> re-inserted at its original node path
Node structure (country -> sub -> sub) is created as needed but never removed.

Nothing is deleted. The output is always a superset of live, so the worst case
is that a stale entry comes back, not that a good one disappears.

A full report is written before the merged file, so the diff can be reviewed
and reversed.

USAGE
  python3 merge_trackerdata.py --live trackerdata.json \\
      --restore trackerdata_patched.json --out trackerdata.json \\
      --report merge_report.json [--dry-run]
  python3 merge_trackerdata.py --selftest
"""

import argparse
import collections
import json
import sys


def norm_url(url):
    return (url or "").strip().rstrip("/").lower()


def walk(node, path, out):
    """Collect {(path, norm_url): entry} and remember every node path seen."""
    for e in node.get("trackers", []) or []:
        out[(path, norm_url(e.get("url")))] = e
    for name, child in (node.get("sub") or {}).items():
        walk(child, path + (name,), out)


def index(doc):
    entries = {}
    for iso, node in doc.items():
        walk(node, (iso,), entries)
    return entries


def ensure_node(doc, path):
    """Return the node at path, creating intermediate nodes if missing."""
    iso = path[0]
    node = doc.setdefault(iso, {"trackers": []})
    for name in path[1:]:
        node = node.setdefault("sub", {}).setdefault(name, {"trackers": []})
    node.setdefault("trackers", [])
    return node


def merge(live, restore):
    live_idx = index(live)
    rest_idx = index(restore)

    only_live = set(live_idx) - set(rest_idx)
    only_rest = set(rest_idx) - set(live_idx)
    both = set(live_idx) & set(rest_idx)

    restored = []
    for key in sorted(only_rest):
        path, _ = key
        ensure_node(live, path)["trackers"].append(rest_idx[key])
        restored.append({"path": "/".join(path),
                         "name": rest_idx[key].get("name"),
                         "url": rest_idx[key].get("url")})

    report = {
        "live_entries_before": len(live_idx),
        "restore_entries": len(rest_idx),
        "in_both_live_wins": len(both),
        "live_only_kept": len(only_live),
        "restored": len(only_rest),
        "live_entries_after": len(live_idx) + len(only_rest),
        "restored_by_country": dict(collections.Counter(
            r["path"].split("/")[0] for r in restored).most_common()),
        "restored_entries": restored,
    }
    return live, report


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    live = {
        "USA": {"trackers": [{"url": "https://a.org/", "name": "A live"}],
                "sub": {"Ohio": {"trackers": [
                    {"url": "https://ohio.gov", "name": "Ohio live"}]}}},
        "FRA": {"trackers": [{"url": "https://new.fr", "name": "New only live"}]},
    }
    restore = {
        "USA": {"trackers": [{"url": "https://a.org", "name": "A stale"},
                             {"url": "https://b.org", "name": "B restored"}],
                "sub": {"Ohio": {"trackers": [
                            {"url": "https://ohio.gov/", "name": "Ohio stale"}]},
                        "Iowa": {"trackers": [
                            {"url": "https://iowa.gov", "name": "Iowa restored"}]}}},
        "DEU": {"trackers": [{"url": "https://de.de", "name": "DE restored"}]},
    }

    merged, rep = merge(json.loads(json.dumps(live)), restore)

    eq(rep["restored"], 3, "merge/restores-missing")
    eq(rep["live_only_kept"], 1, "merge/keeps-live-only")
    eq(rep["in_both_live_wins"], 2, "merge/both-counted")

    names = {e["name"] for e in merged["USA"]["trackers"]}
    eq("A live" in names, True, "merge/live-version-wins")
    eq("A stale" in names, False, "merge/stale-version-dropped")
    eq("B restored" in names, True, "merge/restores-entry")

    ohio = {e["name"] for e in merged["USA"]["sub"]["Ohio"]["trackers"]}
    eq(ohio, {"Ohio live"}, "merge/trailing-slash-is-same-entry")
    eq(merged["USA"]["sub"]["Iowa"]["trackers"][0]["name"], "Iowa restored",
       "merge/creates-missing-subnode")
    eq(merged["DEU"]["trackers"][0]["name"], "DE restored",
       "merge/creates-missing-country")
    eq(merged["FRA"]["trackers"][0]["name"], "New only live",
       "merge/untouched-country")

    # merged must be a superset of live: nothing lost, ever
    before = set(index(live))
    after = set(index(merged))
    eq(before <= after, True, "merge/superset-of-live")

    # idempotent: merging again changes nothing
    again, rep2 = merge(json.loads(json.dumps(merged)), restore)
    eq(rep2["restored"], 0, "merge/idempotent")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (12 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", default="trackerdata.json")
    ap.add_argument("--restore", required=False)
    ap.add_argument("--out", default="")
    ap.add_argument("--report", default="merge_report.json")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.restore:
        print("error: --restore required", file=sys.stderr)
        return 2

    live = json.load(open(args.live))
    restore = json.load(open(args.restore))
    merged, report = merge(live, restore)

    json.dump(report, open(args.report, "w"), indent=1, ensure_ascii=False)

    print(f"live before   : {report['live_entries_before']}")
    print(f"restore file  : {report['restore_entries']}")
    print(f"in both       : {report['in_both_live_wins']} (live version kept)")
    print(f"live only     : {report['live_only_kept']} (untouched)")
    print(f"RESTORED      : {report['restored']}")
    print(f"live after    : {report['live_entries_after']}")
    print("restored by country:")
    for iso, n in list(report["restored_by_country"].items())[:15]:
        print(f"  {iso}: {n}")
    print(f"report -> {args.report}")

    if args.dry_run or not args.out:
        print("(dry run — nothing written)")
        return 0

    json.dump(merged, open(args.out, "w"), ensure_ascii=False,
              separators=(",", ":"))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
