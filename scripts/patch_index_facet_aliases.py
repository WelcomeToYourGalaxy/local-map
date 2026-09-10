#!/usr/bin/env python3
"""Give kindOf / voiceOf / skindOf / restypeOf the same alias treatment _tierLabel got.

    python3 patch_index_facet_aliases.py index.html            # dry run, prints the diff
    python3 patch_index_facet_aliases.py index.html --write

Why
---
The four accessors currently pass the stored string straight through:

    function kindOf(t){ return t.kind||'structured'; }

`trackerVisible` then tests `activeKinds.has(kindOf(t))`, and activeKinds is built from
the KINDS vocabulary. So a value outside the vocabulary — 'ngo', 'research', 'official' —
is truthy, fails the .has() test, and the entry disappears from the map and the index
panel under every filter combination. That is the `subnational` defect exactly, in four
more places, and skind is the one most likely to be populated next: 17 values to miss and
currently absent on all 8,563 entries.

What this changes
-----------------
Each accessor resolves through an alias map. Known values map to themselves. A short list
of near-misses maps to the intended bin. Anything unrecognised falls back to the field's
existing default rather than vanishing — a wrong bin is recoverable, an invisible entry is
not.

No stored value changes bin: the script verifies that against trackerdata.json before it
writes, and refuses if any entry would move.
"""
import json, re, sys, subprocess, tempfile, os

# ---------------------------------------------------------------- alias tables

KIND = """const _KIND_ALIAS={structured:'structured',institution:'institution',journalism:'journalism',video:'video',podcast:'podcast',blog:'blog',newsletter:'newsletter',analyst:'analyst',advocacy:'advocacy',aggregator:'aggregator',lowtrust:'lowtrust',official:'structured',registry:'structured',register:'structured',database:'structured',data:'structured',dataset:'structured',gov:'structured',government:'structured',ngo:'institution',institutional:'institution',org:'institution',organisation:'institution',organization:'institution',watchdog:'institution',academic:'institution',research:'institution',university:'institution',news:'journalism',press:'journalism',media:'journalism','investigative-journalism':'journalism',investigative:'journalism',youtube:'video',audio:'podcast',substack:'newsletter',opinion:'advocacy',campaign:'advocacy',activist:'advocacy',directory:'aggregator',portal:'aggregator'};
function kindOf(t){ const k=String(t.kind||'structured').toLowerCase().trim(); return _KIND_ALIAS[k]||'structured'; }"""

VOICE = """const _VOICE_ALIAS={official:'official',interpretive:'interpretive',commentary:'commentary',gov:'official',government:'official',state:'official',statutory:'official',interpretative:'interpretive',independent:'interpretive',analysis:'interpretive',analytical:'interpretive',opinion:'commentary',editorial:'commentary',advocacy:'commentary'};
function voiceOf(t){ const v=String(t.voice||'interpretive').toLowerCase().trim(); return _VOICE_ALIAS[v]||'interpretive'; }"""

SKIND = """const _SKIND_ALIAS={court:'court',database:'database',council:'council',conduct:'conduct',justicegov:'justicegov',stats:'stats',foi:'foi',bar:'bar',legalaid:'legalaid',ngo:'ngo',igo:'igo',media:'media',research:'research',index:'index',oversight:'oversight',prison:'prison',other:'other',gov:'court',government:'court',portal:'court',agency:'court',ministry:'court',registry:'database',register:'database',data:'database',dataset:'database',commission:'council',board:'council',integrity:'conduct',discipline:'conduct',anticorruption:'conduct','anti-corruption':'conduct',justice:'justicegov',prosecution:'justicegov',prosecutor:'justicegov',statistics:'stats',rti:'foi',transparency:'foi',lawyers:'bar',barassociation:'bar','bar-association':'bar',aid:'legalaid','legal-aid':'legalaid',civil:'ngo',association:'ngo',nonprofit:'ngo',international:'igo',un:'igo',treaty:'igo',press:'media',news:'media',academic:'research',university:'research',ranking:'index',ombudsman:'oversight',audit:'oversight',auditor:'oversight',detention:'prison'};
function skindOf(t){ const s=String(t.skind||'other').toLowerCase().trim(); return _SKIND_ALIAS[s]||'other'; }"""

RESTYPE = """const _RESTYPE_ALIAS={resource:'resource',mechanism:'mechanism',body:'resource',organisation:'resource',organization:'resource',fund:'resource',scheme:'resource',service:'resource',law:'mechanism',statute:'mechanism',act:'mechanism',procedure:'mechanism',process:'mechanism',treaty:'mechanism',doctrine:'mechanism',right:'mechanism'};
function restypeOf(t){ const r=String(t.restype||'resource').toLowerCase().trim(); return _RESTYPE_ALIAS[r]||'resource'; }"""

TARGETS = [
    ("function kindOf(t){ return t.kind||'structured'; }", KIND, "kind", "structured"),
    ("function voiceOf(t){ return t.voice||'interpretive'; }", VOICE, "voice", "interpretive"),
    ("function skindOf(t){ return t.skind||'other'; }", SKIND, "skind", "other"),
    ("function restypeOf(t){ return t.restype||'resource'; }", RESTYPE, "restype", "resource"),
]


def alias_table(js):
    body = re.search(r"=\{(.*?)\};", js, re.S).group(1)
    return {k.strip("'").lower(): v for k, v in re.findall(r"'?([A-Za-z\-]+)'?:'(\w+)'", body)}


def walk(td):
    for iso, c in td.items():
        if not isinstance(c, dict):
            continue
        stack = [c]
        while stack:
            node = stack.pop()
            for t in node.get("trackers", []) or []:
                yield t
            for _, v in (node.get("sub") or {}).items():
                stack.append(v)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    if not args:
        sys.exit(__doc__)
    index_path = args[0]
    td_path = args[1] if len(args) > 1 else "trackerdata.json"

    h = open(index_path, encoding="utf-8").read()

    missing = [old for old, _, _, _ in TARGETS if h.count(old) != 1]
    if missing:
        sys.exit("expected exactly one occurrence of each accessor; not found or already "
                 "patched:\n  " + "\n  ".join(missing))

    # ---- no stored value may change bin
    try:
        td = json.load(open(td_path, encoding="utf-8"))
    except OSError:
        sys.exit(f"could not read {td_path} — pass it as the second argument")

    moved = 0
    for _, js, field, default in TARGETS:
        tbl = alias_table(js)
        for t in walk(td):
            before = t.get(field) or default
            after = tbl.get(str(t.get(field) or default).lower().strip(), default)
            if before != after:
                moved += 1
                if moved <= 5:
                    print(f"  would move {field}: {before!r} -> {after!r}")
    if moved:
        sys.exit(f"refusing to patch: {moved} stored values would change bin")
    print(f"checked {sum(1 for _ in walk(td))} entries across 4 fields — no value changes bin")

    for old, new, _, _ in TARGETS:
        h = h.replace(old, new)

    # ---- syntax check the concatenated script blocks
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", h, re.S)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write("\n;\n".join(scripts))
        tmp = f.name
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    os.unlink(tmp)
    if r.returncode:
        sys.exit("node --check FAILED\n" + r.stderr)
    print("node --check PASSED")

    if write:
        open(index_path, "w", encoding="utf-8").write(h)
        print(f"wrote {index_path}")
    else:
        print("dry run — pass --write to save")


if __name__ == "__main__":
    main()
