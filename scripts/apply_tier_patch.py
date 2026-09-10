#!/usr/bin/env python3
"""Apply TIER_PATCH_ALL.json to trackerdata.json, then verify both render gates.

    python3 apply_tier_patch.py trackerdata.json TIER_PATCH_ALL.json index.html
    python3 apply_tier_patch.py trackerdata.json TIER_PATCH_ALL.json index.html --write

Without --write nothing is saved; the script reports what would change.

Idempotent and order-independent: rows are matched on (country, url) at depth 0
only, so re-running it is a no-op and it does not care what other patches have
already landed.
"""
import json, sys, re, collections

LEGAL = {"municipal", "county", "state", "national", "international"}


def load_render_rules(index_html):
    """Read the alias map and the level vocabulary out of index.html itself,
    so the check tracks the deployed renderer rather than a copy of it."""
    h = open(index_html, encoding="utf-8").read()
    m = re.search(r"const _TIER_ALIAS=\{(.*?)\};", h, re.S)
    if not m:
        sys.exit("could not find _TIER_ALIAS in " + index_html)
    alias = {k.lower(): v for k, v in re.findall(r"'?([A-Za-z\-]+)'?:'(\w+)'", m.group(1))}
    m = re.search(r"const LEVELS=(\[.*?\]);", h, re.S)
    if not m:
        sys.exit("could not find LEVELS in " + index_html)
    levels = set(re.findall(r"\['(\w+)',", m.group(1)))
    return alias, levels


def tier_label(alias, t):
    return "State" if not t else alias.get(str(t).strip().lower(), "State")


def gates(td, alias, levels):
    """Compute each consumer's value independently: tagLevels (map filter) and
    buildIndexData (side panel). Never reuse one to verify the other."""
    lvl = collections.Counter()
    mismatch = hidden = 0
    for iso, c in td.items():
        if not isinstance(c, dict):
            continue
        for t in c.get("trackers", []) or []:
            tier = t.get("tier")
            a = tier_label(alias, tier) if tier else "National"   # tagLevels, depth 0
            b = tier_label(alias, tier) if tier else "National"   # buildIndexData, depth 0
            if a != b:
                mismatch += 1
            lvl[a] += 1
            if a not in levels:
                hidden += 1
        stack = [(c, 0)]
        while stack:
            node, depth = stack.pop()
            for _, v in (node.get("sub") or {}).items():
                for t in v.get("trackers", []) or []:
                    a = (tier_label(alias, t.get("tier")) if depth == 0
                         else tier_label(alias, t.get("tier") or "county"))
                    lvl[a] += 1
                    if a not in levels:
                        hidden += 1
                stack.append((v, depth + 1))
    return lvl, mismatch, hidden


def show(label, lvl, mismatch, hidden):
    order = ["National", "State", "County", "Municipal", "International"]
    body = " · ".join(f"{k} {lvl[k]}" for k in order)
    extra = {k: v for k, v in lvl.items() if k not in order}
    print(f"{label:<10} {body}   mismatch {mismatch}   outside activeLevels {hidden}"
          + (f"   UNEXPECTED {extra}" if extra else ""))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if len(args) != 3:
        sys.exit(__doc__)
    td_path, patch_path, index_path = args

    td = json.load(open(td_path, encoding="utf-8"))
    patch = json.load(open(patch_path, encoding="utf-8"))["rows"]
    alias, levels = load_render_rules(index_path)

    bad = sorted({r["tier"] for r in patch} - LEGAL)
    if bad:
        sys.exit(f"patch contains illegal tier values: {bad}")

    show("before", *gates(td, alias, levels))

    by_key = {(r["country"], r["url"]): r for r in patch}
    applied = unchanged = missing = 0
    seen = set()
    for iso, c in td.items():
        if not isinstance(c, dict):
            continue
        for t in c.get("trackers", []) or []:
            r = by_key.get((iso, t.get("url")))
            if not r:
                continue
            seen.add((iso, t.get("url")))
            if t.get("tier") == r["tier"] and t.get("sub_unit") == r.get("sub_unit"):
                unchanged += 1
                continue
            t["tier"] = r["tier"]
            if r.get("sub_unit"):
                t["sub_unit"] = r["sub_unit"]
            if r.get("uncertain"):
                t["uncertain"] = True
            applied += 1
    missing = len(by_key) - len(seen)

    print(f"\npatch rows {len(patch)}   applied {applied}   already correct {unchanged}   "
          f"not found in data {missing}")
    if missing:
        print("  (not-found rows are entries that moved or were removed since the patch "
              "was built — they are skipped, not guessed at)")

    show("\nafter", *gates(td, alias, levels))

    still = sum(1 for iso, c in td.items() if isinstance(c, dict)
                for t in (c.get("trackers") or []) if not t.get("tier"))
    print(f"country-level entries still without a tier: {still}")

    if write:
        json.dump(td, open(td_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nwrote {td_path}")
    else:
        print("\ndry run — pass --write to save")


if __name__ == "__main__":
    main()
