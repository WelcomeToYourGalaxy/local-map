#!/usr/bin/env python3
"""Apply STATUS_PATCH.json to trackerdata.json.

    python3 apply_status_patch.py trackerdata.json STATUS_PATCH.json
    python3 apply_status_patch.py trackerdata.json STATUS_PATCH.json --write

Read this before running it
---------------------------
`status` is the one field in this data whose failure mode is invisibility. `trackerVisible`
drops any entry whose status is not `active` unless the historical toggle is on — and
`syncHistToggle` hides that toggle entirely while no entry has a status. Applying this patch
turns the toggle on for the first time, and simultaneously removes these entries from the
default view.

So a wrong `defunct` does not show a stale link. It hides a live organisation from every user.

What earns `defunct` here: the host failed to resolve on the Commander's machine twice, failed
again from an independent resolver, and failed in both `www.` forms. Nothing else. Every 403,
timeout, TLS error and stale deep link is deliberately left `active` — 403 means "not to you",
a timeout is a fact about the request, and a dead deep link on a live site is a link to fix,
not a body to bury.

Safety
------
- Refuses on any value outside active / dormant / defunct.
- Refuses to overwrite a status already set by hand.
- Matches on (country, url) at any depth; idempotent and order-independent.
- Reports how many entries leave the default view.
"""
import json, sys, collections

VALID = {"active", "dormant", "defunct"}


def walk(td):
    for iso, c in td.items():
        if not isinstance(c, dict):
            continue
        stack = [c]
        while stack:
            node = stack.pop()
            for t in node.get("trackers", []) or []:
                yield iso, t
            for _, v in (node.get("sub") or {}).items():
                stack.append(v)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if len(args) != 2:
        sys.exit(__doc__)
    td_path, patch_path = args

    td = json.load(open(td_path, encoding="utf-8"))
    rows = json.load(open(patch_path, encoding="utf-8"))["rows"]

    illegal = sorted({r["status"] for r in rows} - VALID)
    if illegal:
        sys.exit(f"patch contains values outside {sorted(VALID)}: {illegal}")

    by_key = {(r["country"], r["url"]): r["status"] for r in rows}

    clash = [(iso, t.get("url"), t["status"], by_key[(iso, t.get("url"))])
             for iso, t in walk(td)
             if t.get("status") and (iso, t.get("url")) in by_key
             and t["status"] != by_key[(iso, t.get("url"))]]
    if clash:
        for c in clash[:5]:
            print("  would overwrite a hand-set status:", c)
        sys.exit(f"refusing to patch: {len(clash)} entries already carry a different status")

    applied = unchanged = 0
    seen = set()
    for iso, t in walk(td):
        k = (iso, t.get("url"))
        if k not in by_key:
            continue
        seen.add(k)
        if t.get("status") == by_key[k]:
            unchanged += 1
        else:
            t["status"] = by_key[k]
            applied += 1

    after = collections.Counter(t.get("status") or "active" for _, t in walk(td))
    total = sum(after.values())
    hidden = total - after["active"]

    print(f"patch rows {len(rows)}   applied {applied}   already correct {unchanged}   "
          f"not found in data {len(by_key) - len(seen)}")
    print("\nstatus distribution")
    for k in ("active", "dormant", "defunct"):
        print(f"   {after.get(k,0):6d}   {k}")
    print(f"\n{hidden} of {total} entries leave the default view "
          f"({100*hidden/total:.1f}%). The historical toggle becomes visible for the first time.")

    if write:
        json.dump(td, open(td_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nwrote {td_path}")
    else:
        print("\ndry run — pass --write to save")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()


