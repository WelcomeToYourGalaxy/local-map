#!/usr/bin/env python3
"""Apply KIND_GOVERNMENT_PATCH.json to trackerdata.json and report the facet effect.

    python3 apply_kind_patch.py trackerdata.json KIND_GOVERNMENT_PATCH.json index.html
    python3 apply_kind_patch.py trackerdata.json KIND_GOVERNMENT_PATCH.json index.html --write

Run patch_index_kind_government.py against index.html FIRST. Without it `government` is not in
the KINDS vocabulary, `activeKinds.has('government')` is false, and every entry this patch
touches disappears from the map and the index panel. The script checks for this and refuses.

Safety
------
- Refuses if any patch value is outside the KINDS vocabulary read from index.html.
- Refuses if any entry already carries a different kind that a human set deliberately —
  only `structured` and `institution`, the two defaults this patch is meant to correct, are
  overwritten.
- Matches on (country, url) at any depth, so it is idempotent and order-independent.
- Reports the trust distribution before and after; `government` maps to `high`, so nothing
  should move.
"""
import json, re, sys, collections

OVERWRITABLE = {"structured", "institution"}


def read_const(h, name, pattern):
    m = re.search(pattern, h, re.S)
    if not m:
        sys.exit(f"could not find {name} in index.html")
    return m.group(1)


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
    if len(args) != 3:
        sys.exit(__doc__)
    td_path, patch_path, index_path = args

    h = open(index_path, encoding="utf-8").read()
    KINDS = set(re.findall(r"\['([^']+)',", read_const(h, "KINDS", r"const KINDS=(\[.*?\]);\n")))
    K2T = dict(re.findall(r"(\w+):'(\w+)'", read_const(h, "KIND2TIER", r"const KIND2TIER=\{(.*?)\};")))

    td = json.load(open(td_path, encoding="utf-8"))
    rows = json.load(open(patch_path, encoding="utf-8"))["rows"]

    illegal = sorted({r["kind"] for r in rows} - KINDS)
    if illegal:
        sys.exit(f"{illegal} not in the KINDS vocabulary — run patch_index_kind_government.py "
                 "against index.html first")
    for v in {r["kind"] for r in rows}:
        if v not in K2T:
            sys.exit(f"KIND2TIER has no trust mapping for '{v}'")

    by_key = {(r["country"], r["url"]): r["kind"] for r in rows}

    clash = [(iso, t.get("url"), t.get("kind"))
             for iso, t in walk(td)
             if (iso, t.get("url")) in by_key
             and t.get("kind") and t["kind"] not in OVERWRITABLE
             and t["kind"] != by_key[(iso, t.get("url"))]]
    if clash:
        for c in clash[:5]:
            print("  would overwrite a deliberate value:", c)
        sys.exit(f"refusing to patch: {len(clash)} entries carry a kind outside "
                 f"{sorted(OVERWRITABLE)}")

    def trust():
        return collections.Counter(K2T.get(t.get("kind") or "structured", "high")
                                   for _, t in walk(td))

    before = trust()
    applied = unchanged = 0
    seen = set()
    for iso, t in walk(td):
        k = (iso, t.get("url"))
        if k not in by_key:
            continue
        seen.add(k)
        if t.get("kind") == by_key[k]:
            unchanged += 1
        else:
            t["kind"] = by_key[k]
            applied += 1
    after = trust()

    print(f"patch rows {len(rows)}   applied {applied}   already correct {unchanged}   "
          f"not found in data {len(by_key) - len(seen)}")
    print("\ntrust distribution")
    for k in sorted(set(before) | set(after)):
        flag = "" if before.get(k, 0) == after.get(k, 0) else "   CHANGED"
        print(f"   {before.get(k,0):6d} -> {after.get(k,0):6d}   {k}{flag}")

    kinds = collections.Counter(t.get("kind") or "structured" for _, t in walk(td))
    print("\nkind distribution")
    for k in sorted(KINDS):
        if kinds.get(k, 0):
            print(f"   {kinds[k]:6d}   {k}")
    print(f"   values in use: {sum(1 for k in KINDS if kinds.get(k,0))} of {len(KINDS)}")

    if write:
        json.dump(td, open(td_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nwrote {td_path}")
    else:
        print("\ndry run — pass --write to save")


if __name__ == "__main__":
    main()
