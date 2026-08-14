#!/usr/bin/env python3
"""
geolocate_wire.py — attach coordinates to wire items that are about a PLACE

RULES (as specified)
--------------------
1. LOCAL ONLY. An item is mapped only when it resolves to a county/municipal
   unit or to an explicit point. Items that resolve no finer than international,
   national or state/admin-1 level are NOT mapped — they stay in the feed only.
   wire.json carries iso + region (admin-1), which is exactly the level we
   refuse, so a match must come from a *project* or a named settlement.
2. NO METAPHORS. "gold mine" in a retirement-account story and "pipeline" in a
   drug-delivery story are the same words doing different work. Items whose
   subject-matter keyword appears only in a figurative context are dropped.
3. NO GUESSING. A coordinate is attached only from a matched project record.
   Nothing is geocoded by name lookup or invented.

USAGE
  python3 geolocate_wire.py --wire wire.json --projects projects.json \\
      --out wire_geo.json --report wire_geo_report.json
  python3 geolocate_wire.py --selftest
"""

import argparse
import collections
import json
import re
import sys
import unicodedata

try:
    from isogate import IsoGate
except ImportError:  # gate is optional; without it, country cannot be checked
    IsoGate = None

# ---------------------------------------------------------------------------
# rule 2 — metaphor rejection
# ---------------------------------------------------------------------------
# Each pattern is a *figurative* use of a term this map cares about literally.
# Written as term-in-context, not bare term, so real stories survive.

METAPHOR = [
    # gold mine / goldmine — wealth, data, opportunity
    r"\b(a|the)\s+gold\s?mine\s+(of|for)\b",
    r"\b(data|information|content|marketing|retirement|tax|savings|investment|"
    r"recruit\w*|talent|treasure)\s+gold\s?mine\b",
    r"\bgold\s?mine\s+(of\s+(data|information|insight|opportunit|content))\b",
    # pipeline — sales, drugs, talent, software, education
    r"\b(sales|deal|revenue|talent|hiring|recruit\w*|candidate|customer|"
    r"drug|clinical|therapeutic|vaccine|product|innovation|content|"
    r"development|devops|ci/cd|data|build|school[- ]to[- ]prison|"
    r"education|apprentice\w*|leadership|project)\s+pipeline\b",
    r"\bpipeline\s+of\s+(deals|talent|candidates|drugs|products|projects|"
    r"customers|opportunities|reforms)\b",
    r"\bdrug\s+delivery\b",
    # mining — data, crypto, text
    r"\b(data|text|bitcoin|crypto\w*|token|process)\s+mining\b",
    r"\bmining\s+(the\s+)?(data|archives?|records?|texts?|literature)\b",
    # drilling / fracking figurative
    r"\bdrill(ing)?\s+down\s+(in)?to\b",
    # extraction figurative
    r"\b(rent|value|data|feature|attention)[- ]extraction\b",
    # landfill/toxic figurative
    r"\btoxic\s+(work\w*|culture|masculinity|relationship|positivity|"
    r"discourse|fandom|behaviou?r)\b",
    # "dam" as verb/idiom and "reservoir of"
    r"\breservoir\s+of\s+(goodwill|talent|support|knowledge|anger)\b",
    # carbon/energy market chatter rather than a project
    r"\b(stock|share|equity|bond|etf|index|earnings|dividend|ipo)\b.*"
    r"\b(mining|energy|oil|gas)\s+(stock|share|sector|company|giant)\b",
]
METAPHOR_RE = [re.compile(p, re.I) for p in METAPHOR]


def is_metaphor(text):
    return any(rx.search(text or "") for rx in METAPHOR_RE)


# Sector/market chatter with no site attached. These never map even if a
# project name coincidentally matches.
NON_SITE = re.compile(
    r"\b(shares?\s+(rose|fell|slid|gained)|stock\s+market|wall\s+street|"
    r"quarterly\s+(results|earnings)|profit\s+warning|analysts?\s+(say|expect)|"
    r"price\s+target|market\s+cap|index\s+fund|"
    r"industry\s+outlook|sector\s+report|global\s+demand\s+for)\b", re.I)


# ---------------------------------------------------------------------------
# rule 1 — level gate
# ---------------------------------------------------------------------------
ALLOWED_LEVELS = ("county", "municipal", "point")

# Words that mark an item as national/international in scope. If the only
# geography an item offers is one of these, it is refused.
SUPRA_LOCAL = re.compile(
    r"\b(nationwide|nationally|national\s+(government|policy|plan|ban|target)|"
    r"federal\s+(government|policy|court|agency)|countrywide|"
    r"across\s+the\s+country|statewide|state[- ]wide|province[- ]wide|"
    r"eu[- ]wide|europe[- ]wide|global(ly)?|worldwide|international\s+"
    r"(community|agreement|treaty))\b", re.I)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "project", "projects",
    "plan", "plans", "new", "site", "area", "county", "city", "town", "village",
    "district", "region", "state", "national", "park", "river", "lake", "valley",
    "north", "south", "east", "west", "upper", "lower", "de", "la", "el", "los",
    "das", "dos", "del", "van", "der", "und", "der", "die", "les", "des",
    "construction", "development", "permit", "building", "works", "scheme",
}


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def tokens(text, minlen=4):
    return {w for w in re.findall(r"[a-z0-9]+", norm(text))
            if len(w) >= minlen and w not in STOP}


def distinctive(name):
    """Tokens of a project name that could identify it in a headline."""
    return tokens(name)


# A project name identifies a place only if it is specific. One-word names
# ("Building", "Commercial") and very long dataset titles match everything.
MIN_NAME_TOKENS = 2
MAX_NAME_TOKENS = 8
# A token shared by more than this many projects is generic ("mine", "road")
# and cannot pin a headline to one site.
RARE_MAX_DF = 60


def build_index(projects, min_token_len=4):
    """token -> project indices, plus each project's token set. Coordinates
    required; generic or unusably long names discarded."""
    kept, toksets = [], []
    for p in projects:
        if p.get("lat") is None or p.get("lng") is None:
            continue
        toks = distinctive(p.get("name", ""))
        if not (MIN_NAME_TOKENS <= len(toks) <= MAX_NAME_TOKENS):
            continue
        kept.append(p)
        toksets.append(toks)
    idx = collections.defaultdict(list)
    for n, toks in enumerate(toksets):
        for t in toks:
            idx[t].append(n)
    return idx, kept, toksets


def match_item(item, idx, projects, toksets, min_overlap=3,
               max_candidates=400, gate=None):
    """Return (project, score) or (None, reason)."""
    text = f"{item.get('title','')} {item.get('snippet','')}"
    if is_metaphor(text):
        return None, "metaphor"
    if NON_SITE.search(text):
        return None, "sector_or_market"

    toks = tokens(text)
    if not toks:
        return None, "no_tokens"

    # Only rare tokens can seed a candidate. "mine", "road", "plant" cannot.
    counts = collections.Counter()
    for t in toks:
        hits = idx.get(t)
        if not hits or len(hits) > RARE_MAX_DF:
            continue
        for i in hits:
            counts[i] += 1
    if not counts:
        return None, "no_project_match"

    # A candidate only wins if EVERY distinctive token of the project name
    # appears in the headline — partial overlap is what produced the false
    # positives ("German ... Explosive" matching an army training facility).
    best, score = None, 0
    for i, _ in counts.most_common(50):
        need = toksets[i]
        if need <= toks and len(need) >= min_overlap and len(need) > score:
            best, score = i, len(need)
    if best is None:
        return None, "weak_match"

    proj = projects[best]
    iso = item.get("iso")
    if iso and proj.get("iso") and proj["iso"] != iso:
        return None, "country_mismatch"

    # projects.json has no country field, so verify geometrically: the matched
    # coordinate must fall inside the country the story is about.
    if gate is not None and iso:
        region = gate.locate(iso, proj["lat"], proj["lng"])
        if region is None:
            return None, "outside_country"
        proj = dict(proj, admin1=region)

    # rule 1: the matched project must itself be a place, not a programme.
    if proj.get("precise") is False and SUPRA_LOCAL.search(text):
        return None, "supra_local"

    return proj, score


def level_of(project):
    """What geographic level does this coordinate actually represent?"""
    if project.get("precise") is False:
        return "municipal"        # centroid of a commune/settlement
    return "point"


def run(wire, projects, min_overlap=3, gate=None):
    idx, kept, toksets = build_index(projects)
    out, reasons = [], collections.Counter()
    for item in wire:
        proj, res = match_item(item, idx, kept, toksets, min_overlap, gate=gate)
        if proj is None:
            reasons[res] += 1
            continue
        lvl = level_of(proj)
        if lvl not in ALLOWED_LEVELS:
            reasons["level_too_coarse"] += 1
            continue
        out.append({**item, "lat": proj["lat"], "lng": proj["lng"],
                    "level": lvl, "project": proj.get("name"),
                    "project_url": proj.get("url"),
                    "admin1": proj.get("admin1"), "match_score": res})
        reasons["mapped"] += 1
    return out, reasons


# ---------------------------------------------------------------------------

def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    # metaphors rejected
    eq(is_metaphor("Your retirement account is a gold mine of tax breaks"),
       True, "meta/retirement-goldmine")
    eq(is_metaphor("A new drug delivery pipeline for cancer therapy"),
       True, "meta/drug-pipeline")
    eq(is_metaphor("Startups build a sales pipeline"), True, "meta/sales-pipeline")
    eq(is_metaphor("Data mining reveals patterns"), True, "meta/data-mining")
    eq(is_metaphor("Toxic workplace culture at the firm"), True, "meta/toxic-culture")

    # literal usage survives
    eq(is_metaphor("Villagers block the Trans-Anatolian gas pipeline route"),
       False, "meta/keeps-real-pipeline")
    eq(is_metaphor("Gold mine tailings dam collapses in Para"),
       False, "meta/keeps-real-goldmine")
    eq(is_metaphor("Company begins drilling at the Karoo site"),
       False, "meta/keeps-real-drilling")

    eq(bool(NON_SITE.search("Mining shares rose on Wall Street")), True,
       "nonsite/market")
    eq(bool(NON_SITE.search("Residents object to the quarry permit")), False,
       "nonsite/keeps-local")

    projects = [
        {"name": "Karahisar Copper Mine", "lat": 40.1, "lng": 38.2,
         "url": "u1", "iso": "TUR"},
        {"name": "Riverside Housing Development", "lat": 51.5, "lng": -0.1,
         "url": "u2", "precise": False},
    ]
    idx, kept, toksets = build_index(projects)
    eq(len(kept), 2, "index/keeps-coord-projects")

    hit, score = match_item(
        {"title": "Protest halts work at Karahisar copper mine",
         "snippet": "", "iso": "TUR"}, idx, kept, toksets)
    eq(hit["url"] if hit else None, "u1", "match/finds-project")

    miss, why = match_item(
        {"title": "Copper prices climb as analysts say demand rises",
         "snippet": "", "iso": "TUR"}, idx, kept, toksets)
    eq(miss, None, "match/rejects-market")
    eq(why, "sector_or_market", "match/market-reason")

    miss2, why2 = match_item(
        {"title": "Retirement accounts are a gold mine of tax breaks",
         "snippet": ""}, idx, kept, toksets)
    eq(why2, "metaphor", "match/rejects-metaphor")

    miss3, why3 = match_item(
        {"title": "Karahisar copper mine expansion approved", "snippet": "",
         "iso": "GRC"}, idx, kept, toksets)
    eq(why3, "country_mismatch", "match/country-gate")

    eq(level_of(projects[0]), "point", "level/point")
    eq(level_of(projects[1]), "municipal", "level/centroid")

    mapped, reasons = run(
        [{"title": "Karahisar copper mine protest", "snippet": "", "iso": "TUR"},
         {"title": "Sales pipeline software raises funding", "snippet": ""}],
        projects)
    eq(len(mapped), 1, "run/maps-one")
    eq(mapped[0]["level"], "point", "run/level-attached")
    eq(reasons["metaphor"], 1, "run/counts-metaphor")

    # generic names are not indexed at all
    _, generic, _ = build_index([{"name": "Building", "lat": 1, "lng": 1},
                                 {"name": "Construction site", "lat": 2, "lng": 2}])
    eq(len(generic), 0, "index/drops-generic-names")

    # partial overlap must not match
    _, k2, t2 = build_index([{"name": "Karahisar Copper Mine", "lat": 1,
                              "lng": 1, "url": "u"}])
    part, whyp = match_item({"title": "Copper mine opens in Chile",
                             "snippet": ""}, _, k2, t2)
    eq(part, None, "match/rejects-partial-overlap")

    class FakeGate:
        def locate(self, iso, lat, lng):
            return "Trabzon" if iso == "TUR" else None

    hit2, sc2 = match_item(
        {"title": "Protest halts work at Karahisar copper mine",
         "snippet": "", "iso": "TUR"}, idx, kept, toksets, gate=FakeGate())
    eq(hit2["admin1"] if hit2 else None, "Trabzon", "gate/attaches-admin1")

    # project carrying no iso field (the real projects.json case): only the
    # geometric gate can catch a wrong-country match
    _, k3, t3 = build_index([{"name": "Karahisar Copper Mine", "lat": 40.1,
                              "lng": 38.2, "url": "u"}])
    i3 = collections.defaultdict(list)
    for n, tk in enumerate(t3):
        for w in tk:
            i3[w].append(n)
    out3, why4 = match_item(
        {"title": "Protest halts work at Karahisar copper mine",
         "snippet": "", "iso": "CHL"}, i3, k3, t3, gate=FakeGate())
    eq(why4, "outside_country", "gate/rejects-wrong-country")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (25 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wire", default="wire.json")
    ap.add_argument("--projects", default="projects.json")
    ap.add_argument("--out", default="wire_geo.json")
    ap.add_argument("--report", default="wire_geo_report.json")
    ap.add_argument("--min-overlap", type=int, default=3)
    ap.add_argument("--no-iso-gate", action="store_true",
                    help="skip the country check (faster, much less precise)")
    ap.add_argument("--cache", default="boundary_cache")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    wire = json.load(open(args.wire))
    pdata = json.load(open(args.projects))
    projects = pdata["projects"] if isinstance(pdata, dict) else pdata

    gate = None
    if not args.no_iso_gate:
        if IsoGate is None:
            print("warning: isogate.py not found; country check disabled",
                  file=sys.stderr)
        else:
            gate = IsoGate(args.cache)
    mapped, reasons = run(wire, projects, args.min_overlap, gate)

    json.dump(mapped, open(args.out, "w"), ensure_ascii=False, indent=1)
    json.dump({"wire_items": len(wire), "mapped": len(mapped),
               "reasons": dict(reasons)},
              open(args.report, "w"), indent=1)

    print(f"wire {len(wire)} | mapped {len(mapped)}")
    for r, n in reasons.most_common():
        print(f"  {r:20s} {n}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
