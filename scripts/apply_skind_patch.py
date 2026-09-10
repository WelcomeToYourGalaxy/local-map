#!/usr/bin/env python3
"""Apply SKIND_PATCH_PARTIAL.json to trackerdata.json and report the facet effect.

    python3 apply_skind_patch.py trackerdata.json SKIND_PATCH_PARTIAL.json index.html
    python3 apply_skind_patch.py trackerdata.json SKIND_PATCH_PARTIAL.json index.html --write

Without --write nothing is saved.

Unlike the tier patch this is a proposal, not a correction: `skind` is currently absent on
every entry, so nothing in the file is wrong today — the facet is simply carrying no
information. The patch fills 1,449 entries where the name matched one unambiguous pattern
and leaves the rest at 'other'.

Safety
------
- Refuses if any patch row carries a value outside the SKINDS vocabulary read from index.html.
- Refuses if any entry already has a skind that the patch would change. Only absent fields
  are filled, so a later hand-written value always wins over this one.
- Matches on (country, url) at any depth, so it is idempotent and order-independent.
"""
import json, re, sys, collections

def vocab(index_html, name):
    h = open(index_html, encoding="utf-8").read()
    m = re.search(r"const " + name + r"\s*=\s*(\[.*?\]);\n", h, re.S)
    if not m:
        sys.exit(f"could not find {name} in {index_html}")
    return set(re.findall(r"\['([^']+)',", m.group(1)))

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

def media_ks(k, s):
    """Mirror of mediaKS in index.html — the only consumer of skind besides the facet
    and the popup sub-grouping."""
    k = k or "structured"; s = s or "other"
    if k == "video": return "video"
    if k == "podcast": return "podcast"
    if k in ("newsletter", "blog"): return "blog"
    if k == "journalism": return "investigative"
    if s == "media": return "news"
    if s == "research": return "research"
    if s in ("database", "stats", "index"): return "database"
    return "portal"

def facets(td):
    sk, md = collections.Counter(), collections.Counter()
    for _, t in walk(td):
        s = t.get("skind") or "other"
        sk[s] += 1
        md[media_ks(t.get("kind"), s)] += 1
    return sk, md

def show(title, before, after, voc):
    print(f"\n{title}")
    for k in sorted(voc):
        b, a = before.get(k, 0), after.get(k, 0)
        if b or a:
            print(f"   {b:6d} -> {a:6d}   {k}")
    pb = sum(1 for k in voc if before.get(k, 0))
    pa = sum(1 for k in voc if after.get(k, 0))
    print(f"   pills populated: {pb} -> {pa} of {len(voc)}")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if len(args) != 3:
        sys.exit(__doc__)
    td_path, patch_path, index_path = args

    SKINDS = vocab(index_path, "SKINDS")
    MEDIA = vocab(index_path, "MEDIA")
    td = json.load(open(td_path, encoding="utf-8"))
    rows = json.load(open(patch_path, encoding="utf-8"))["rows"]

    illegal = sorted({r["skind"] for r in rows} - SKINDS)
    if illegal:
        sys.exit(f"patch contains values outside the SKINDS vocabulary: {illegal}")

    by_key = {(r["country"], r["url"]): r["skind"] for r in rows}

    clash = [(iso, t.get("url"), t["skind"], by_key[(iso, t.get("url"))])
             for iso, t in walk(td)
             if t.get("skind") and (iso, t.get("url")) in by_key
             and t["skind"] != by_key[(iso, t.get("url"))]]
    if clash:
        for c in clash[:5]:
            print("  would overwrite", c)
        sys.exit(f"refusing to patch: {len(clash)} entries already carry a different skind")

    sk_b, md_b = facets(td)

    applied = unchanged = 0
    seen = set()
    for iso, t in walk(td):
        k = (iso, t.get("url"))
        if k not in by_key:
            continue
        seen.add(k)
        if t.get("skind") == by_key[k]:
            unchanged += 1
        else:
            t["skind"] = by_key[k]
            applied += 1

    sk_a, md_a = facets(td)

    print(f"patch rows {len(rows)}   applied {applied}   already correct {unchanged}   "
          f"not found in data {len(by_key) - len(seen)}")
    show("skind facet", sk_b, sk_a, SKINDS)
    show("media facet", md_b, md_a, MEDIA)

    if write:
        json.dump(td, open(td_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nwrote {td_path}")
    else:
        print("\ndry run — pass --write to save")

if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # piping into head closes stdout early; not an error
        sys.stderr.close()
