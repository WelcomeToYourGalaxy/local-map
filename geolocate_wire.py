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
import gzip
import os
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
# Words that are common enough in ordinary prose that matching on them is
# meaningless. "MORE Fun" is a real OSM feature name; without this, a story
# containing "more" and "fun" matches it.
COMMON = {
    "more", "most", "fun", "best", "good", "great", "well", "very", "much",
    "many", "some", "such", "than", "then", "when", "what", "where", "which",
    "will", "would", "could", "should", "have", "here", "there", "they",
    "them", "their", "your", "were", "been", "into", "over", "under", "after",
    "before", "again", "also", "just", "like", "make", "made", "take", "come",
    "going", "know", "time", "year", "years", "week", "days", "people",
    "first", "last", "next", "long", "high", "low", "big", "small", "large",
    "open", "close", "full", "free", "real", "main", "top", "old", "young",
    "help", "need", "want", "look", "back", "down", "away", "off", "out",
}

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


def tokens(text, minlen=4, drop_common=True):
    bad = STOP | COMMON if drop_common else STOP
    return {w for w in re.findall(r"[a-z0-9]+", norm(text))
            if len(w) >= minlen and w not in bad}


GENERIC_TAIL = re.compile(
    r"\b(development|redevelopment|project|projects|scheme|expansion|extension|"
    r"phase|stage|works|facility|facilities|site|sites|proposal|application|"
    r"upgrade|programme|program|complex|ltd|limited|plc|inc|corporation|"
    r"company|holdings|group|pty|pte|sa|nv|gmbh|srl)\b", re.I)


def name_variants(name):
    """The forms a story might use for the same project.

    Real coverage rarely uses the register's full string: the permit says
    'Oyu Tolgoi Mine Development', the news says 'Oyu Tolgoi mine'. Stripping
    generic tails adds those hits without loosening any gate."""
    out = {name}
    # registers qualify names in brackets - "Raniganj North Gas Block (India)",
    # "Lot 3 (phase 2)". Coverage never writes those.
    unparen = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", " ", name)
    unparen = re.sub(r"\s+", " ", unparen).strip(" -,\u2014")
    if unparen and unparen != name:
        out.add(unparen)
        tail2 = GENERIC_TAIL.sub(" ", unparen)
        tail2 = re.sub(r"\s+", " ", tail2).strip(" -,\u2014")
        if tail2 and tail2 != unparen:
            out.add(tail2)
    stripped = GENERIC_TAIL.sub(" ", name)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -,\u2014")
    if stripped and stripped != name:
        out.add(stripped)
    return {v for v in out if len(v) > 3}


def phrase_present(name, text):
    """Does the project name appear as a contiguous phrase in the story?

    Set overlap alone let unrelated words in different sentences match. Real
    references name the thing: 'Karahisar copper mine', not 'copper' in
    paragraph 1 and 'Karahisar' in paragraph 9."""
    words = [w for w in re.findall(r"[a-z0-9]+", norm(name))
             if w not in STOP and w not in COMMON]
    if len(words) < 2:
        return False
    return " ".join(words) in " ".join(re.findall(r"[a-z0-9]+", norm(text)))


def distinctive(name):
    """Tokens of a project name that could identify it in a headline."""
    return tokens(name)


# Project names that are just a place or a company are not sites: "Buenos
# Aires", "Social Housing", "Novo Nordisk" match anything written about the
# city or the firm. Require the name to say what the THING is.
SITE_WORDS = re.compile(
    r"(mine|quarry|pit|dam|reservoir|pipeline|terminal|port|airport|railway|"
    r"rail|road|highway|motorway|bridge|tunnel|plant|refinery|smelter|mill|"
    r"factory|works|farm|windfarm|solar|turbine|substation|landfill|incinerat|"
    r"waste|estate|development|scheme|project|park|reserve|canal|barrage|"
    r"platform|field|colliery|quarr|warehouse|datacent|data cent|feedlot|"
    r"cafo|hatchery|kiln|cement|steel|paper|chemical|storage|depot|"
    r"subdivision|resort|marina|dock|jetty|pier|lock|weir|"
    # the same words in the other languages this feed carries
    r"mina|minera|cantera|planta|usina|represa|barragem|barragem|embalse|"
    r"vertedero|relleno sanitario|autopista|carretera|ferrocarril|ferrovia|"
    r"rodovia|estrada|puerto|porto|aeropuerto|aeroporto|oleoducto|gasoducto|"
    r"gasoduto|refiner[ií]a|refinaria|central|parque e[oó]lico|parque solar|"
    r"usine|barrage|carri[eè]re|d[eé]charge|a[eé]roport|autoroute|"
    r"kraftwerk|steinbruch|deponie|tagebau|stau(damm|see)|"
    r"impianto|cava|discarica|centrale|"
    r"kopalnia|elektrownia|wysypisko)", re.I)


# A project name identifies a place only if it is specific. One-word names
# ("Building", "Commercial") and very long dataset titles match everything.
MIN_NAME_TOKENS = 2
MAX_NAME_TOKENS = 8
# A token shared by more than this many projects is generic ("mine", "road")
# and cannot pin a headline to one site.
RARE_MAX_DF = 60


# Companies whose name is too generic or too governmental to identify a site.
COMPANY_STOP = re.compile(
    r"\b(council|department|ministry|agency|authority|administration|"
    r"municipality|government|state|national|parks|university|school|"
    r"hospital|church|trust)\b", re.I)


def company_key(project):
    """A company name usable as an identifier, or None.

    'Vedanta' identifies a site when the story also gives the right region.
    'Dublin City Council' does not - it appears in every story about Dublin."""
    c = (project.get("company") or "").strip()
    if not c or len(c) < 5 or COMPANY_STOP.search(c):
        return None
    toks = [w for w in re.findall(r"[a-z0-9]+", norm(c))
            if w not in STOP and w not in COMMON and len(w) >= 5
            and not GENERIC_TAIL.fullmatch(w)]
    return toks or None


def build_index(projects, min_token_len=4):
    """token -> project indices, plus each project's token set. Coordinates
    required; generic or unusably long names discarded."""
    kept, toksets = [], []
    for p in projects:
        if p.get("lat") is None or p.get("lng") is None:
            continue
        name = p.get("name", "")
        toks = distinctive(name)
        if not (MIN_NAME_TOKENS <= len(toks) <= MAX_NAME_TOKENS):
            continue
        if not SITE_WORDS.search(name):
            continue
        kept.append(p)
        toksets.append(toks)
    idx = collections.defaultdict(list)
    for n, toks in enumerate(toksets):
        for t in toks:
            idx[t].append(n)
    # secondary index: operator name -> projects, used only with a region match
    cidx = collections.defaultdict(list)
    for n, p in enumerate(kept):
        for tok in (company_key(p) or []):
            cidx[tok].append(n)
    return idx, kept, toksets, cidx


def match_item(item, idx, projects, toksets, min_overlap=3,
               max_candidates=400, gate=None, cidx=None):
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
        if not (need <= toks and len(need) >= min_overlap and len(need) > score):
            continue
        if not any(phrase_present(v, text)
                   for v in name_variants(projects[i].get("name", ""))):
            continue
        best, score = i, len(need)
    if False and best is None and cidx:   # operator path withdrawn - see notes
        # A story that names the operator, sits in the right admin-1 and is
        # about a site-shaped thing identifies that site.
        body = " ".join(re.findall(r"[a-z0-9]+", norm(text)))
        want_region = norm(item.get("region") or "")
        for ck, idxs in cidx.items():
            if ck not in body or len(idxs) > 40:
                continue
            for i in idxs:
                pr = projects[i]
                if not SITE_WORDS.search(pr.get("name", "") + " " + (pr.get("type") or "")):
                    continue
                if want_region and gate is not None and item.get("iso"):
                    reg = gate.locate(item["iso"], pr["lat"], pr["lng"])
                    if not reg:
                        continue
                    if want_region not in norm(reg) and norm(reg) not in want_region:
                        continue
                elif want_region:
                    continue     # no gate to confirm the region: do not guess
                best, score = i, "company"
                break
            if best is not None:
                break

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
        # wire items carry their own admin-1; a Florida story must not pin to a
        # Maryland project just because both are in the USA.
        want = norm(item.get("region") or "")
        if want and want not in norm(region) and norm(region) not in want:
            return None, "region_mismatch"
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


def item_age_days(item, now_ms=None):
    """Age in days from the item's date, or None when undated."""
    import time

    now_ms = now_ms if now_ms is not None else time.time() * 1000
    d = item.get("date")
    if d is None:
        return None
    try:
        ts = float(d) if not isinstance(d, str) else None
        if ts is None:
            return None
    except (TypeError, ValueError):
        return None
    if ts > 1e12 * 10:      # implausible; treat as unusable rather than guess
        return None
    return (now_ms - ts) / 86400000.0


def merge_geo(prior, fresh, max_age_days=365, now_ms=None):
    """Union of previously published pins and this run's, newest wins.

    Nothing is dropped for being absent from today's feed - only for being
    older than the age cap, and undated items are kept rather than guessed at."""
    out = {}
    for item in list(prior or []) + list(fresh or []):
        key = (item.get("link") or "").strip()
        if not key:
            continue
        age = item_age_days(item, now_ms)
        if age is not None and age > max_age_days:
            continue
        out[key] = item          # fresh overwrites prior on the same link
    return sorted(out.values(),
                  key=lambda x: (x.get("date") or 0), reverse=True)


def run(wire, projects, min_overlap=3, gate=None):
    idx, kept, toksets, cidx = build_index(projects)
    out, reasons = [], collections.Counter()
    for item in wire:
        proj, res = match_item(item, idx, kept, toksets, min_overlap,
                               gate=gate, cidx=cidx)
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
                    "admin1": proj.get("admin1"), "match_score": res,
                    "matched_on": ("operator" if res == "company" else "name")})
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
    idx, kept, toksets, cidx = build_index(projects)
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

    # the reported failure: a Florida story matching "MORE Fun" in Maryland
    eq("more" in tokens("MORE Fun"), False, "tokens/drops-common-words")
    eq(tokens("Karahisar Copper Mine"), {"karahisar", "copper", "mine"},
       "tokens/keeps-real")
    eq(phrase_present("Karahisar Copper Mine",
                      "work at the Karahisar copper mine stopped"), True,
       "phrase/contiguous-match")
    eq(phrase_present("Karahisar Copper Mine",
                      "copper prices rose; separately, Karahisar votes"), False,
       "phrase/rejects-scattered")
    eq(phrase_present("MORE Fun", "there is more fun to be had"), False,
       "phrase/needs-two-real-words")

    class RegionGate:
        def locate(self, iso, lat, lng):
            return "Maryland"

    _, k4, t4, _c4 = build_index([{"name": "Karahisar Copper Mine", "lat": 39.3,
                                   "lng": -76.8, "url": "u"}])
    i4 = collections.defaultdict(list)
    for n, tk in enumerate(t4):
        for w in tk:
            i4[w].append(n)
    _, whyR = match_item({"title": "Karahisar copper mine protest", "snippet": "",
                          "iso": "USA", "region": "Florida"},
                         i4, k4, t4, gate=RegionGate())
    eq(whyR, "region_mismatch", "gate/region-must-agree")

    eq(bool(SITE_WORDS.search("Karahisar Copper Mine")), True, "site/keeps-mine")
    eq(bool(SITE_WORDS.search("Panama Canal")), True, "site/keeps-canal")
    eq(bool(SITE_WORDS.search("Buenos Aires")), False, "site/rejects-city-name")
    eq(bool(SITE_WORDS.search("Novo Nordisk")), False, "site/rejects-company")
    eq(bool(SITE_WORDS.search("Social Housing")), False, "site/rejects-generic")
    _, k5, _t5, _c5 = build_index([{"name": "Buenos Aires", "lat": 1, "lng": 1},
                                   {"name": "Sisson Mine", "lat": 2, "lng": 2}])
    eq(len(k5), 1, "index/only-sites-indexed")

    eq(name_variants("Oyu Tolgoi Mine Development") ==
       {"Oyu Tolgoi Mine Development", "Oyu Tolgoi Mine"}, True, "alias/strips-tail")
    eq("Raniganj North Gas Block" in name_variants("Raniganj North Gas Block (India)"),
       True, "alias/strips-parenthetical")
    eq(bool(SITE_WORDS.search("Mina Los Bronces")), True, "site/spanish")
    eq(bool(SITE_WORDS.search("Barragem de Irapé")), True, "site/portuguese")
    eq(bool(SITE_WORDS.search("Carrière de Vignats")), True, "site/french")
    eq(bool(SITE_WORDS.search("Kopalnia Turów")), True, "site/polish")
    eq(bool(SITE_WORDS.search("Buenos Aires")), False, "site/still-rejects-city")
    eq(phrase_present("Oyu Tolgoi Mine",
                      "protest at the Oyu Tolgoi mine in Umnugovi"), True,
       "alias/matches-short-form")
    eq(company_key({"company": "Dublin City Council"}), None,
       "company/rejects-government")
    eq(company_key({"company": "Vedanta Resources Ltd"}), ["vedanta", "resources"],
       "company/keeps-operator")
    eq(company_key({"company": ""}), None, "company/empty")

    class RegGate:
        def locate(self, iso, lat, lng):
            return "Odisha"

    ci, ck, ct, cc = build_index([{"name": "Lanjigarh Refinery", "company":
                                   "Vedanta Resources", "lat": 19.7, "lng": 83.4,
                                   "url": "v"}])
    _hitc, sc = match_item({"title": "Vedanta refinery expansion challenged",
                           "snippet": "", "iso": "IND", "region": "Odisha"},
                          ci, ck, ct, gate=RegGate(), cidx=cc)
    eq(sc, "company" if False else "weak_match",
       "company/path-withdrawn-after-precision-failure")
    missc, whyc = match_item({"title": "Vedanta refinery expansion challenged",
                              "snippet": "", "iso": "IND", "region": "Kerala"},
                             ci, ck, ct, gate=RegGate(), cidx=cc)
    eq(missc, None, "company/rejects-wrong-region")

    now = 1_800_000_000_000
    old = {"link": "a", "date": now - 400 * 86400000, "title": "old"}
    mid = {"link": "b", "date": now - 30 * 86400000, "title": "kept"}
    undated = {"link": "c", "title": "undated"}
    fresh = [{"link": "b", "date": now, "title": "updated"},
             {"link": "d", "date": now, "title": "new"}]
    merged = merge_geo([old, mid, undated], fresh, 365, now)
    links = {m["link"] for m in merged}
    eq("a" in links, False, "merge/drops-past-age-cap")
    eq("c" in links, True, "merge/keeps-undated")
    eq({"b", "d"} <= links, True, "merge/keeps-old-and-new")
    eq([m for m in merged if m["link"] == "b"][0]["title"], "updated",
       "merge/fresh-wins-on-same-link")
    eq(len(merge_geo([], [], 365, now)), 0, "merge/empty-safe")
    eq(item_age_days({"date": None}), None, "age/undated")

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        plain = os.path.join(td, "p.json")
        with open(plain, "w") as fh:
            json.dump({"projects": [1]}, fh)
        gzp = os.path.join(td, "q.json.gz")
        with gzip.open(gzp, "wt", encoding="utf-8") as fh:
            json.dump({"projects": [1, 2]}, fh)
        eq(len(load_json(plain)["projects"]), 1, "load/plain-json")
        eq(len(load_json(gzp)["projects"]), 2, "load/gzipped-json")
        eq(resolve_projects(gzp), gzp, "resolve/exact")
        eq(resolve_projects(os.path.join(td, "q.json")), gzp, "resolve/falls-back-to-gz")
        try:
            resolve_projects(os.path.join(td, "nope.json"))
            fails.append("resolve/missing not caught")
        except SystemExit:
            pass

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
    _, generic, _g1, _g2 = build_index([{"name": "Building", "lat": 1, "lng": 1},
                                        {"name": "Construction site", "lat": 2, "lng": 2}])
    eq(len(generic), 0, "index/drops-generic-names")

    # partial overlap must not match
    _, k2, t2, _c2 = build_index([{"name": "Karahisar Copper Mine", "lat": 1,
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
    _, k3, t3, _c3 = build_index([{"name": "Karahisar Copper Mine", "lat": 40.1,
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
    print("SELFTEST OK (60 checks)")
    return 0


def load_json(path):
    """Read a .json or .json.gz file.

    The repo keeps projects.json.gz only - the uncompressed copy is 136 MB and
    was removed. Sniff the gzip magic bytes rather than trusting the extension,
    so either name works and a mislabelled file still loads."""
    with open(path, "rb") as fh:
        head = fh.read(2)
    opener = gzip.open if head == b"\x1f\x8b" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_projects(path):
    """Accept either name: if the given path is missing, try the other one."""
    if os.path.exists(path):
        return path
    alt = path[:-3] if path.endswith(".gz") else path + ".gz"
    if os.path.exists(alt):
        print(f"{path} not found; using {alt}")
        return alt
    raise SystemExit(f"neither {path} nor {alt} exists")


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
    ap.add_argument("--merge", default="",
                    help="existing wire_geo.json to accumulate into (keeps past hits)")
    ap.add_argument("--max-age-days", type=int, default=365,
                    help="drop accumulated items older than this")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    wire = load_json(args.wire)
    pdata = load_json(resolve_projects(args.projects))
    projects = pdata["projects"] if isinstance(pdata, dict) else pdata

    gate = None
    if not args.no_iso_gate:
        if IsoGate is None:
            print("warning: isogate.py not found; country check disabled",
                  file=sys.stderr)
        else:
            gate = IsoGate(args.cache)
    mapped, reasons = run(wire, projects, args.min_overlap, gate)

    # ACCUMULATE. wire.json is a rolling window: today's 9,000 items replace
    # yesterday's, so regenerating from scratch discards every hit older than
    # the window. Matches do not expire just because the feed moved on, so
    # merge with what is already published, keyed on the story link.
    if args.merge and os.path.exists(args.merge):
        try:
            prior = json.load(open(args.merge))
        except Exception:  # noqa: BLE001
            prior = []
        mapped = merge_geo(prior, mapped, args.max_age_days)

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
