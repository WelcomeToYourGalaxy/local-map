#!/usr/bin/env python3
"""
CORRECTION \u2014 apply MECA's own audit: remove 9 entries, add 2 that were missing.

THIS RESOLVES THE REVIEWER ACTION I FLAGGED AND COULD NOT PERFORM
The previous MECA delivery (474 entries) carried a warning in its own README: "The R84 and R116
drift-audit drop lists (9 entries) are NOT machine-applied here... and must be applied by the
reviewer before publication." Those round files were not uploaded, so THE 9 WERE MERGED.
The new delivery has them applied and ships the list: MECA_REMOVED_BY_AUDIT.json, 9 entries,
total_after 467. Its note explains why they were missed: "Both audits stored their lists under
'entries_the_reviewer_should_reconsider' -> 'drop', not 'do_not_add'."

THE 9 REMOVALS, AND WHY THE AUDIT DROPPED THEM
They are not errors of fact. They are entries the MECA chat judged too thin or too indirect
once it saw them together, and each carries the audit's own note on what the country retains:
  TKM R67   CAREC regional environmental centre    "leaves Turkmenistan three foreign grant portals"
  BHR R78   ARC-WH UNESCO centre, Manama           "leaves Bahrain one foreign grant portal"
  ARM R80   Armenia Tree Project                   "Armenia retains seven entries"
  AZE R82   REC Caucasus
  IRQ R112  ARC-WH
  YEM R113  ARC-WH
  PSE R113  ARC-WH
  SYR R114  World Heritage Fund International Assistance
  IRN R115  Ramsar Montreux Record
FOUR OF THE NINE ARE THE SAME BODY (ARC-WH) FILED IN FOUR COUNTRIES, and two more are regional
centres. THE AUDIT WAS REMOVING A REGIONAL BODY REPEATED ACROSS ITS MEMBER STATES \u2014 which is a
judgement this map's own rules support: a heritage-nomination centre is not an ally a community
enlists to stop a development.
REMOVAL IS BY (country, URL) PAIR, NOT BY URL ALONE, because the same URL legitimately appears
in several countries and only the audited ones go.

THE 2 ADDITIONS
  OMN  mohup.gov.om e-services
  KGZ  gosreg.gov.kg
Present in the corrected file and absent from the earlier one.

EVERYTHING ELSE IN THE NEW ARCHIVES WAS CHECKED AND CONTAINS NOTHING UNMERGED:
  * EUROPE_..._THIS_SESSION_CANDIDATES.json (137) \u2014 entirely a subset of the compiled 811.
  * AFRICA compilation_rows.json (45) \u2014 every URL already in their trackerdata.json.
  * MECA_ALL_ENTRIES.csv and .html \u2014 the same 467 entries in other formats, no extra URLs.
  * AFRICA placeholder_worklist.json (448) \u2014 NOT entries. It is a QA worklist of placeholder
    fragments ("a named director", host, entry) classed DEC/ACT/UNK, listing text that still
    needs replacing with specifics. Useful to that chat; nothing to merge.

Usage:
  python3 patch_trackerdata_meca_audit.py selftest
  python3 patch_trackerdata_meca_audit.py trackerdata.json [out.json]
"""
import json, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_REMOVED = os.path.join(BASE, "inbox3", "MECA_REMOVED_BY_AUDIT.json")
SRC_NEW = os.path.join(BASE, "inbox3", "MECA_ALL_ENTRIES.json")
SRC_OLD = os.path.join(BASE, "inbox2", "files__1_", "MECA_ALL_ENTRIES.json")
KINDS = {"structured", "institution", "journalism", "video", "podcast", "blog",
         "newsletter", "analyst", "advocacy", "aggregator", "lowtrust"}
VOICES = {"official", "interpretive", "commentary"}
TYPE2KIND = {"institutional": "institution", "records-data": "structured",
             "journalism": "journalism", "analysis": "analyst",
             "community": "institution"}


def _norm(u):
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower()).rstrip("/")


def _load():
    rem, adds = [], []
    if os.path.exists(SRC_REMOVED):
        rem = [(x["cc"], _norm(x["url"])) for x in
               json.load(open(SRC_REMOVED, encoding="utf-8"))["removed"]]
    if os.path.exists(SRC_NEW) and os.path.exists(SRC_OLD):
        new = json.load(open(SRC_NEW, encoding="utf-8"))["entries_by_country"]
        old = json.load(open(SRC_OLD, encoding="utf-8"))["entries_by_country"]
        oldu = {(cc, _norm(e.get("url"))) for cc, v in old.items() for e in v}
        for cc, items in new.items():
            for e in items:
                if (cc, _norm(e.get("url"))) not in oldu:
                    adds.append((cc, e))
    return rem, adds


def process(d, rem=None, adds=None):
    if rem is None or adds is None:
        rem, adds = _load()
    removed, added, notfound = [], [], []
    for cc, u in rem:
        c = d.get(cc)
        if not c:
            notfound.append((cc, u)); continue
        keep, gone = [], False
        for t in c.get("trackers", []):
            if _norm(t.get("url")) == u:
                gone = True
                removed.append((cc, t.get("name", "")[:52]))
            else:
                keep.append(t)
        c["trackers"] = keep
        if not gone:
            notfound.append((cc, u))
    for cc, e in adds:
        c = d.setdefault(cc, {"name": cc, "trackers": []})
        c.setdefault("trackers", [])
        if _norm(e.get("url")) in {_norm(t.get("url")) for t in c["trackers"]}:
            continue
        x = {k: v for k, v in e.items() if not k.startswith("_")}
        if x.get("kind") not in KINDS:
            x["kind"] = TYPE2KIND.get(x.get("type"), "institution")
        if x.get("voice") not in VOICES:
            x["voice"] = "interpretive"
        x.setdefault("restype", "resource")
        c["trackers"].append(x)
        added.append((cc, x.get("name", "")[:48]))
    return removed, added, notfound


def selftest():
    n = 0
    def ok(cond, label):
        nonlocal n
        assert cond, "FAILED: " + label
        n += 1

    rem = [("TKM", "carececo.org/en/main/about/history"),
           ("BHR", "arcwh.org/who-we-are")]
    adds = [("OMN", {"name": "New OMN", "url": "https://mohup.gov.om/x",
                     "type": "community", "kind": "movement", "desc": "",
                     "tags": ["organizing:help"]})]
    d = {"TKM": {"trackers": [
             {"name": "CAREC", "url": "https://carececo.org/en/main/about/history/"},
             {"name": "Keep me", "url": "https://keep.example/"}]},
         "BHR": {"trackers": [{"name": "ARC-WH", "url": "https://www.arcwh.org/who-we-are"}]},
         "IRQ": {"trackers": [{"name": "ARC-WH", "url": "https://www.arcwh.org/who-we-are"}]},
         "OMN": {"trackers": []}}
    r, a, nf = process(d, rem, adds)
    ok(len(r) == 2, "both audited entries removed")
    ok(len(d["TKM"]["trackers"]) == 1 and
       d["TKM"]["trackers"][0]["name"] == "Keep me",
       "only the audited URL goes; the rest of the country is untouched")
    ok(len(d["IRQ"]["trackers"]) == 1,
       "THE SAME URL IN AN UNAUDITED COUNTRY SURVIVES \u2014 removal is by (country, URL) pair")
    ok(len(a) == 1, "the new entry is added")
    ok(d["OMN"]["trackers"][0]["kind"] == "institution",
       "kind 'movement' is repaired on the way in")
    ok(d["OMN"]["trackers"][0]["restype"] == "resource", "restype defaulted")
    ok(process(d, rem, adds)[0] == [], "second run removes nothing further")
    ok(process(d, rem, adds)[1] == [], "and adds nothing further")
    print("meca_audit selftest: %d/%d passed" % (n, n))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest(); sys.exit(0)

    src = sys.argv[1] if len(sys.argv) > 1 else "trackerdata.json"
    d = json.load(open(src, encoding="utf-8"))
    removed, added, notfound = process(d)
    # dict counter: nonlocal cannot bind a module-level name. Seventh time this session,
    # and py_compile caught it, which is why that check runs before anything else.
    tot = {"n": 0}
    for iso, c in d.items():
        def w(x):
            tot["n"] += len(x.get("trackers", []))
            for s in x.get("sub", {}).values():
                w(s)
        w(c)
    json.dump(d, open(sys.argv[2] if len(sys.argv) > 2 else src, "w"),
              ensure_ascii=False, indent=1)
    print(f"REMOVED per MECA audit ({len(removed)}):")
    for cc, nm in removed:
        print(f"   {cc}  {nm}")
    print(f"ADDED ({len(added)}): {added or 'none'}")
    print(f"not found (already absent): {notfound or 'none'}")
    print(f"countries {len(d)} | entries {tot['n']}")
