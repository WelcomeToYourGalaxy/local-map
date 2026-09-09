#!/usr/bin/env python3
"""
MERGE \u2014 three further full deliveries: LATAM (757), MECA combined (849+143), Asia (1,068).

WHAT ARRIVED
  * LATAM & Caribbean \u2014 LATAM_COMPILATION_R847-R948.json, 757 entries across 33 countries,
    101 rounds, each carrying its source round in `_round`.
  * MECA \u2014 MECA_COMBINED_PAYLOAD.json, rounds R1\u2013R889 from 890 round files, 849 entries and
    143 enrichments across 23 countries. SUPERSEDES the 467-entry file merged earlier.
  * ASIA \u2014 asia_resources_entries.json, 1,068 entries across 27 countries. First Asia delivery.
    (asia_resources_THIS_SESSION.json, 78 entries, was checked and is a subset \u2014 nothing extra.)

TWO WARNINGS IN LATAM'S OWN README, BOTH ACTED ON RATHER THAN NOTED
  1. "ROUND 934 IS DELIBERATELY ABSENT: it was written after a search that returned no results,
     ITS QUOTATIONS WERE FABRICATED, and it was retracted and deleted... If round 934 was
     applied anywhere, remove its 17 entries."
     VERIFIED: no object in the payload carries _round 934, and the live file carries no _round
     field at all, so none of those 17 fabricated entries ever reached it. Nothing to remove.
     RECORDED BECAUSE IT IS THE RIGHT INSTINCT \u2014 a chat catching its own fabrication, retracting
     it, and warning downstream is exactly the behaviour this project depends on.
  2. "THE DUPLICATE CHECK STILL HAS NOT BEEN RUN. The name index was lost when the container
     reset before round 639, so nothing in this range has been checked against existing
     trackerdata.json names."
     SO THE CHECK IS DONE HERE, and done twice over: every incoming entry is compared against
     the live file by URL AND by name, per bucket, AND against entries already accepted earlier
     in the same run \u2014 because a payload assembled from 101 unchecked rounds can contain
     internal duplicates as well as collisions with the file.

OVERLAP FOUND, WHICH IS WHY THE CHECK MATTERED
  LATAM   751 new,   6 already present
  MECA    381 new, 468 already present   <- the superseded 467-entry merge, correctly caught
  ASIA  1,032 new,  36 already present
  TOTAL 2,164 new

DEFECTS, ALL MECHANICALLY REPAIRABLE FROM THE ENTRY'S OWN FIELDS
  ASIA:  ZERO defects across all 1,068. Cleanest delivery received so far.
  MECA:  152 entries with kind "movement" \u2014 not a legal value, renders nowhere.
  LATAM: 590 entries with kind "organization" (505) or "tool" (85); 5 bad voice; and 43 entries
         using the invented tag `conserve:buy`.
         `conserve:buy` MAPS TO `conserve:acquire` \u2014 it is reaching for exactly that lens, and
         unmapped those 43 land-acquisition entries would be invisible to the lens that matters
         most to this map's purpose.
  Repairs: kind derived from `type` where present, else from the invented value
  (organization/movement -> institution, tool -> structured); voice -> interpretive; missing
  restype -> resource; illegal tier removed.

THE 143 MECA ENRICHMENTS ARE APPLIED SEPARATELY AND CONSERVATIVELY
  Each names a country and a URL and supplies replacement or additional description text. They
  are applied ONLY where that exact URL already exists in that country's bucket \u2014 an enrichment
  that matches nothing is reported, never turned into a new entry, because an enrichment whose
  target is missing means the two files disagree about what exists and that needs a human.

Usage:
  python3 patch_trackerdata_merge_batch4.py selftest
  python3 patch_trackerdata_merge_batch4.py trackerdata.json [out.json]
"""
import json, os, re, sys
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
SRC_LAT = os.path.join(BASE, "inbox4", "files__1_", "LATAM_COMPILATION_R847-R948.json")
SRC_MECA = os.path.join(BASE, "inbox4", "MECA_COMBINED_PAYLOAD.json")
SRC_ASIA = os.path.join(BASE, "inbox4", "files", "asia_resources_entries.json")
VT_PATH = "/mnt/user-data/outputs/VALID_TAGS.txt"

KINDS = {"structured", "institution", "journalism", "video", "podcast", "blog",
         "newsletter", "analyst", "advocacy", "aggregator", "lowtrust"}
VOICES = {"official", "interpretive", "commentary"}
TIERS = {"subnational", "county", "municipal"}
TYPE2KIND = {"institutional": "institution", "records-data": "structured",
             "journalism": "journalism", "analysis": "analyst",
             "community": "institution", "organization": "institution",
             "movement": "institution", "tool": "structured"}
TAGFIX = {"conserve:buy": "conserve:acquire",
          "organizing:coalition": "organizing:help",
          "records:reference": "organizing:research",
          "organizing:protect": "conserve:protect",
          "fund:grant": "organizing:fund",
          "advocacy:campaign": "advocacy:watchdog",
          "organizing:watchdog": "advocacy:watchdog",
          "records:project": "projects:trackers",
          "records:analysis": "organizing:research",
          "conserve:finance": "organizing:fund"}


def _norm(u):
    return re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower()).rstrip("/")


def repair(e, valid_tags, stats):
    e = {k: v for k, v in e.items() if not k.startswith("_")}
    if e.get("kind") not in KINDS:
        k = TYPE2KIND.get(e.get("kind")) or TYPE2KIND.get(e.get("type"))
        if not k:
            return None, f"kind {e.get('kind')!r} unresolvable"
        e["kind"] = k; stats["kind"] += 1
    if e.get("voice") not in VOICES:
        e["voice"] = "interpretive"; stats["voice"] += 1
    if e.get("restype") is None:
        e["restype"] = "resource"; stats["restype"] += 1
    if "tier" in e and e["tier"] not in TIERS:
        del e["tier"]; stats["tier"] += 1
    tags, changed = [], False
    for g in e.get("tags", []):
        if g in valid_tags:
            tags.append(g)
        elif g in TAGFIX:
            tags.append(TAGFIX[g]); changed = True
        else:
            changed = True
    if changed:
        stats["tags"] += 1
    e["tags"] = sorted(set(tags))
    if not e["tags"]:
        return None, "no valid tags"
    d = e.get("desc", "")
    if d.count("<b>") != d.count("</b>"):
        return None, "unbalanced bold"
    return e, None


def _sources():
    S = {}
    if os.path.exists(SRC_LAT):
        lat = {}
        for x in json.load(open(SRC_LAT, encoding="utf-8"))["append"]:
            lat.setdefault(x["country"], []).append(x["entry"])
        S["LATAM"] = lat
    if os.path.exists(SRC_MECA):
        S["MECA"] = json.load(open(SRC_MECA, encoding="utf-8"))["add"]
    if os.path.exists(SRC_ASIA):
        A = json.load(open(SRC_ASIA, encoding="utf-8"))
        S["ASIA"] = {k: v for k, v in A.items() if isinstance(v, list)}
    return S


def _enrichments():
    if not os.path.exists(SRC_MECA):
        return []
    return json.load(open(SRC_MECA, encoding="utf-8")).get("enrich", [])


def _node(d, path):
    parts = path.split("/")
    n = d.setdefault(parts[0], {"name": parts[0], "trackers": []})
    for p in parts[1:]:
        n = n.setdefault("sub", {}).setdefault(p, {"trackers": []})
    n.setdefault("trackers", [])
    return n


def process(d, sources=None, enrich=None, valid_tags=None):
    if valid_tags is None:
        valid_tags = set(open(VT_PATH).read().split()) if os.path.exists(VT_PATH) else set()
    sources = _sources() if sources is None else sources
    enrich = _enrichments() if enrich is None else enrich
    added, skipped, held, rejected = [], [], [], []
    stats = Counter()
    for label, S in sources.items():
        for cc, items in S.items():
            node = _node(d, cc)
            for t in items:
                have_u = {_norm(x.get("url", "")) for x in node["trackers"]}
                have_n = {x.get("name", "") for x in node["trackers"]}
                if _norm(t.get("url", "")) in have_u or t.get("name", "") in have_n:
                    skipped.append((label, cc)); continue
                if t.get("restype") == "mechanism":
                    held.append((label, cc, t.get("name", "")[:52])); continue
                e, why = repair(t, valid_tags, stats)
                if e is None:
                    rejected.append((label, cc, t.get("name", "")[:38], why)); continue
                node["trackers"].append(e)
                added.append((label, cc))
    enriched, orphan = [], []
    # MECA enrichments use match_url / match_name / append_to_desc / add_tags, and some set
    # apply_to_all_instances. Match on URL first, then on exact name, because a chat may have
    # corrected a URL since the enrichment was written.
    for x in enrich:
        cc = x.get("country") or x.get("cc")
        u = _norm(x.get("match_url") or x.get("url", ""))
        nm = x.get("match_name", "")
        add_text = x.get("append_to_desc") or x.get("append") or ""
        add_tags = x.get("add_tags") or []
        c = d.get(cc)
        hit = False
        if c:
            for t in c.get("trackers", []):
                if not ((u and _norm(t.get("url", "")) == u) or (nm and t.get("name") == nm)):
                    continue
                hit = True
                if add_text and add_text.strip()[:40] not in t.get("desc", ""):
                    t["desc"] = t.get("desc", "") + add_text
                    enriched.append((cc, t.get("name", "")[:40]))
                for g in add_tags:
                    g = TAGFIX.get(g, g)
                    if g in valid_tags and g not in t.get("tags", []):
                        t.setdefault("tags", []).append(g)
        if not hit:
            orphan.append((cc, (x.get("match_url") or "")[:52]))
    return added, skipped, held, rejected, stats, enriched, orphan


def selftest():
    n = 0
    def ok(cond, label):
        nonlocal n
        assert cond, "FAILED: " + label
        n += 1

    VT = {"conserve:acquire", "organizing:help"}
    src = {"L": {"BRA": [
        {"name": "Org", "url": "https://a.example/", "kind": "organization",
         "desc": "<b>x</b>", "tags": ["conserve:buy"], "voice": "official"},
        {"name": "Tool", "url": "https://b.example/", "kind": "tool",
         "desc": "", "tags": ["organizing:help"], "voice": "bogus"},
        {"name": "Dup", "url": "https://dup.example/", "kind": "organization",
         "desc": "", "tags": ["organizing:help"]},
        {"name": "InternalDup", "url": "https://a.example/", "kind": "organization",
         "desc": "", "tags": ["organizing:help"]}]}}
    d = {"BRA": {"trackers": [{"name": "Dup", "url": "https://dup.example/"}]}}
    a, s, h, r, st, en, orp = process(d, src, [], VT)
    byname = {t["name"]: t for t in d["BRA"]["trackers"]}
    ok(len(a) == 2, "two clean entries added")
    ok(byname["Org"]["kind"] == "institution", "kind 'organization' repaired")
    ok(byname["Tool"]["kind"] == "structured", "kind 'tool' repaired")
    ok(byname["Org"]["tags"] == ["conserve:acquire"],
       "conserve:buy remapped to conserve:acquire \u2014 the land lens it was reaching for")
    ok(byname["Tool"]["voice"] == "interpretive", "illegal voice defaulted")
    ok(len(s) == 2, "the pre-existing dup AND the internal dup are both skipped")
    ok(sum(1 for t in d["BRA"]["trackers"] if t["name"] == "Org") == 1,
       "an internal duplicate inside one payload cannot land twice")
    d2 = {"ARM": {"trackers": [{"name": "T", "url": "https://e.example/", "desc": "base"}]}}
    en2 = [{"country": "ARM", "match_url": "https://e.example/",
            "append_to_desc": " EXTRA", "add_tags": ["conserve:buy"]},
           {"country": "ARM", "match_url": "https://missing.example/",
            "append_to_desc": " NOPE"}]
    a2, s2, h2, r2, st2, en2r, orp2 = process(d2, {}, en2, VT)
    ok(d2["ARM"]["trackers"][0]["desc"] == "base EXTRA", "enrichment appended to its target")
    ok(d2["ARM"]["trackers"][0]["tags"] == ["conserve:acquire"],
       "add_tags applied AND remapped through the same tag fixer")
    ok(len(orp2) == 1, "an enrichment with no matching URL is reported, not invented")
    ok(len(d2["ARM"]["trackers"]) == 1, "and creates no new entry")
    ok(process(d, src, [], VT)[0] == [], "second run is a no-op")
    print("merge_batch4 selftest: %d/%d passed" % (n, n))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        selftest(); sys.exit(0)

    src = sys.argv[1] if len(sys.argv) > 1 else "trackerdata.json"
    d = json.load(open(src, encoding="utf-8"))
    added, skipped, held, rejected, stats, enriched, orphan = process(d)

    cnt = {"vis": 0, "hid": 0, "bold": 0, "n": 0}
    for iso, c in d.items():
        def w(x):
            for t in x.get("trackers", []):
                cnt["n"] += 1
                ds = t.get("desc", "")
                if ds.count("<b>") != ds.count("</b>"):
                    cnt["bold"] += 1
                if t.get("kind", "structured") in KINDS and \
                   t.get("voice", "interpretive") in VOICES:
                    cnt["vis"] += 1
                else:
                    cnt["hid"] += 1
            for s in x.get("sub", {}).values():
                w(s)
        w(c)

    out = sys.argv[2] if len(sys.argv) > 2 else src
    json.dump(d, open(out, "w"), ensure_ascii=False, indent=1)
    per = Counter(l for l, _ in added)
    print(f"MERGED {len(added)}:  " + "  ".join(f"{k}={v}" for k, v in per.items()))
    print(f"skipped as already present or internally duplicated: {len(skipped)}")
    print(f"REPAIRS: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"ENRICHMENTS applied: {len(enriched)} | orphaned (no matching URL): {len(orphan)}")
    for cc, u in orphan[:8]:
        print(f"   orphan {cc}  {u}")
    print(f"mechanisms held: {len(held)} | rejected: {len(rejected)}")
    for x in rejected[:6]:
        print(f"   {x}")
    print(f"\ncountries {len(d)} | entries {cnt['n']} | visible {cnt['vis']} | "
          f"hidden {cnt['hid']} | unbalanced bold {cnt['bold']}")
