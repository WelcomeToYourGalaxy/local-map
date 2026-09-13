#!/usr/bin/env python3
"""Add a `government` value to the KINDS vocabulary.

    python3 patch_index_kind_government.py index.html            # dry run
    python3 patch_index_kind_government.py index.html --write

Why
---
`KINDS` is a source-type taxonomy inherited from the judicial map. It has no value for a
government body. The two that get used instead both misdescribe one:

    structured    'Records & data'   Official court records, dockets, registries...
    institution   'Institutional'    Established NGOs, watchdogs, bar associations...

4,227 entries in the live data are `kind: institution` paired with `voice: official` — a kind
labelled "NGOs and watchdogs" and a voice meaning "published by the government or the body
itself". Ministries of finance, auditors-general and procurement agencies are filed under a
label that says they are NGOs.

`SKINDS` already carries the concept — `court` is labelled 'Government portal' — which is the
precedent for describing a government body in this taxonomy. This adds the matching kind.

What changes
------------
Three edits, all additive. No existing value moves, no existing entry changes bin.

1. `KINDS` gains `['government','Government body', ...]`, placed after `structured` so it sits
   with the other primary-source kinds in the facet.
2. `KIND2TIER` gains `government:'high'` — same trust as `structured` and `institution`, which
   is correct for a ministry or a registry and keeps every current entry's trust unchanged.
3. `_KIND_ALIAS` routes `gov`, `government`, `ministry`, `agency` and `authority` to it. Those
   previously fell back to `structured`; nothing in the data uses them, so nothing moves.

Populating the value is a separate data patch. This only makes the value exist — without it,
a data patch setting `kind: 'government'` would fail `activeKinds.has()` and take every entry
it touched off the map.

Requires patch_index_facet_aliases.py to have run first (edit 3 needs `_KIND_ALIAS`).
"""
import re, sys, subprocess, tempfile, os

EDITS = [
    ("KINDS vocabulary",
     "const KINDS=[['structured','Records & data','Official court records, dockets, registries and statistical dashboards \\u2014 the primary source.'],",
     "const KINDS=[['structured','Records & data','Official court records, dockets, registries and statistical dashboards \\u2014 the primary source.'],"
     "['government','Government body','Ministries, agencies, authorities, courts and other public bodies \\u2014 the institution itself, not a report about it.'],"),
    ("KIND2TIER",
     "const KIND2TIER={structured:'high',institution:'high',",
     "const KIND2TIER={structured:'high',government:'high',institution:'high',"),
    ("_KIND_ALIAS",
     "gov:'structured',government:'structured',",
     "gov:'government',government:'government',ministry:'government',agency:'government',authority:'government',"),
]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        sys.exit(__doc__)
    path = args[0]
    h = open(path, encoding="utf-8").read()

    for label, old, _ in EDITS:
        n = h.count(old)
        if n != 1:
            hint = ("  (run patch_index_facet_aliases.py first)"
                    if label == "_KIND_ALIAS" and n == 0 else "")
            sys.exit(f"expected exactly one {label} anchor; found {n} — not found or already "
                     f"patched{hint}")

    for label, old, new in EDITS:
        h = h.replace(old, new)
        print(f"  patched {label}")

    kinds = re.search(r"const KINDS=(\[.*?\]);\n", h, re.S).group(1)
    vals = re.findall(r"\['([^']+)',", kinds)
    k2t = dict(re.findall(r"(\w+):'(\w+)'", re.search(r"const KIND2TIER=\{(.*?)\};", h, re.S).group(1)))
    print(f"  KINDS is now {len(vals)} values: {', '.join(vals)}")
    missing = [v for v in vals if v not in k2t]
    if missing:
        sys.exit(f"KIND2TIER has no trust mapping for: {missing}")
    print("  every kind has a trust mapping")

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
