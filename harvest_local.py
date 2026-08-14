#!/usr/bin/env python3
"""
harvest_local.py — global harvester for county- and municipal-tier entries

SCOPE
-----
Every subnational local unit on earth, not just US counties:
  - admin-2 ("county" tier): ~47,000 units worldwide
  - admin-3/4 ("municipal" tier): several hundred thousand units worldwide

The US-only predecessor (harvest_districts.py) assumed conservation districts,
which exist in one country. This replaces that assumption with a country-keyed
registry of WHICH LOCAL BODY actually holds land and water powers, because the
answer differs everywhere: conservation districts (US), regional districts
(CAN), comunas/municipios (LatAm), councils (GBR/AUS/NZL), communes (FRA/BEL),
Gemeinden (DEU/AUT/CHE), catchment/water boards (NLD, ZAF), panchayats (IND),
prefectures/municipalities (JPN), and so on.

TWO GLOBAL BACKBONES
--------------------
Only two sources actually span every country with machine-readable official
URLs, so both are first-class backends:
  wikidata  — SPARQL; P856 (official website) on admin units, filtered by
              P31/P131 to a country and admin level. Covers ~all countries.
  overpass  — OSM admin boundaries (admin_level 6/7/8) carrying website= or
              contact:website= tags. Better than Wikidata in some countries
              (DEU, FRA, ITA, POL, BRA), worse in others.
Country-specific sources (arcgis / html / csv / json) override both where a
national or state government publishes a better list.

NON-NEGOTIABLE RULES (carried over, and they matter more at this scale)
----------------------------------------------------------------------
1. No fabricated URLs. Every emitted URL comes from a source AND resolves.
2. No guessed unit names. If a body's name cannot be mapped to a named unit
   with confidence, it is a gap, not an entry.
3. No off-theme entries. A bare government homepage is NOT a land-defence
   resource. An entry is emitted only when the source gives a themed page
   (planning, environment, land, water, conservation) OR the body is itself a
   land/water authority. Everything else is reported under gaps as
   "no_themed_page" so the count stays honest.
4. Tags are set per country/body-type from the registry, never inferred. A body
   that cannot buy land never receives conserve:acquire.

USAGE
-----
  python3 harvest_local.py --selftest
  python3 harvest_local.py --registry registry.json --country USA \
      --tier county --out local_adds_USA_county.json --contact you@example.com
  python3 harvest_local.py --registry registry.json --shard 3/32 --out ...
  python3 harvest_local.py --plan          # print unit counts + coverage plan
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# tier vocabulary — must match index.html's tieredPopHTML() buckets
# ----------------------------------------------------------------------------
TIERS = ("county", "municipal")

# OSM admin_level -> tier, per broad convention. Overridden per country in the
# registry because admin_level semantics genuinely differ by country.
DEFAULT_OSM_LEVELS = {"county": [6], "municipal": [7, 8]}

# Themed-page detection. Rule 3 above depends on this: we only accept a URL if
# it looks like a land/water/planning page, or the body itself is one.
THEME_WORDS = re.compile(
    r"(planning|planungs|urbanisme|urbanismo|urbanistica|zoning|"
    r"environment|environnement|medio\s*ambiente|ambiente|umwelt|milieu|"
    r"land|terrain|terreno|grund|"
    r"water|eau|agua|wasser|catchment|watershed|"
    r"conservation|conserva|natur|nature|"
    r"park|parque|parc|open\s*space|espace|"
    r"heritage|patrimonio|patrimoine)", re.I)


def is_themed(url, page_title="", body_is_land_authority=False):
    """Rule 3. A council homepage is not a land-defence resource."""
    if body_is_land_authority:
        return True
    return bool(THEME_WORDS.search(url) or THEME_WORDS.search(page_title or ""))


# ----------------------------------------------------------------------------
# registry — what body holds land/water power in each country
# ----------------------------------------------------------------------------
# registry.json shape:
# {"countries": {
#    "USA": {"county": {"body": "Soil & Water Conservation District",
#                       "land_authority": true,
#                       "tags": ["conserve:protect","organizing:help"],
#                       "desc": "WHAT IT DOES: ... {unit} ...",
#                       "sources": [ {source descriptors} ]},
#            "municipal": {...}},
#    "GBR": {...}}}
#
# A country with no entry here is NOT harvested. Silence beats guessing which
# body in Kazakhstan holds land powers.

REQUIRED_BODY_KEYS = ("body", "tags", "desc")


def load_registry(path):
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        data = json.load(fh)
    countries = data.get("countries", data)
    for iso3, tiers in countries.items():
        if not re.fullmatch(r"[A-Z]{3}", iso3):
            raise ValueError(f"country key must be ISO3: {iso3!r}")
        for tier, spec in tiers.items():
            if tier not in TIERS:
                raise ValueError(f"{iso3}: bad tier {tier!r}")
            for key in REQUIRED_BODY_KEYS:
                if key not in spec:
                    raise ValueError(f"{iso3}.{tier}: missing {key!r}")
            if "{unit}" not in spec["desc"]:
                raise ValueError(f"{iso3}.{tier}: desc must contain {{unit}}")
    return countries


# ----------------------------------------------------------------------------
# backends
# ----------------------------------------------------------------------------

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"

WIKIDATA_QUERY = """
SELECT ?unit ?unitLabel ?site WHERE {
  ?unit wdt:P31/wdt:P279* wd:%(class_qid)s .
  ?unit wdt:P17 wd:%(country_qid)s .
  ?unit wdt:P856 ?site .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "%(lang)s,en". }
}
"""

OVERPASS = "https://overpass-api.de/api/interpreter"

OVERPASS_QUERY = """
[out:json][timeout:180];
area["ISO3166-1:alpha3"="%(iso3)s"]->.c;
relation(area.c)["boundary"="administrative"]["admin_level"~"^(%(levels)s)$"]
  ["name"][~"^(website|contact:website)$"~"."];
out tags;
"""


def parse_wikidata(payload):
    out = []
    for row in payload.get("results", {}).get("bindings", []):
        name = (row.get("unitLabel", {}) or {}).get("value", "").strip()
        site = (row.get("site", {}) or {}).get("value", "").strip()
        qid = (row.get("unit", {}) or {}).get("value", "").rsplit("/", 1)[-1]
        if not name or not site:
            continue
        if re.fullmatch(r"Q\d+", name):
            continue  # unlabelled item; do not emit a QID as a place name
        out.append({"unit": name, "url": site, "ref": qid})
    return out


def parse_overpass(payload):
    out = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {}) or {}
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        site = (tags.get("website") or tags.get("contact:website") or "").strip()
        if not name or not site:
            continue
        if not site.lower().startswith(("http://", "https://")):
            site = "https://" + site.lstrip("/")
        out.append({"unit": name, "url": site,
                    "ref": f"osm:{el.get('type','rel')}/{el.get('id')}"})
    return out


LINK_RE = re.compile(
    r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>', re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def parse_html(html, name_filter=r"."):
    import html as _html
    out = []
    for m in LINK_RE.finditer(html):
        text = _html.unescape(TAG_RE.sub("", m.group("text")))
        text = re.sub(r"\s+", " ", text).strip()
        href = m.group("href").strip()
        if not text or not re.search(name_filter, text, re.I):
            continue
        if not href.lower().startswith(("http://", "https://")):
            continue
        out.append({"unit": text, "url": href, "ref": "html"})
    return out


def parse_arcgis(payload, fields):
    out = []
    for feat in payload.get("features", []):
        attrs = feat.get("attributes") or feat.get("properties") or {}
        unit = str(attrs.get(fields.get("unit", "NAME"), "") or "").strip()
        url = str(attrs.get(fields.get("website", "URL"), "") or "").strip()
        if unit and url:
            out.append({"unit": unit, "url": url, "ref": "arcgis"})
    return out


# ----------------------------------------------------------------------------
# unit-name hygiene (rule 2)
# ----------------------------------------------------------------------------

JOINT_MARKERS = re.compile(
    r"\b(and|und|et|y|e)\b|\bjoint\b|\bregional\b|\bassociation\b|"
    r"\bverbandsgemeinde\b|\bsamtgemeinde\b|\bverwaltungsgemeinschaft\b|"
    r"\bcommunaut[ée]\b|\bsyndicat\b|\bmetropole\b|\bm[ée]tropole\b|"
    r"\bagglom[ée]ration\b|\bintercommunal\w*\b", re.I)

# A hyphen means "joint body" in US district names (Kootenai-Shoshone) but is
# ordinary orthography in French and German place names (Saint-Étienne,
# Baden-Baden). Countries opt in via "allow_hyphen": true in the registry.
SPLIT_MARKERS = re.compile(r"[/&]|[-\u2013]{2,}")


def clean_unit(name, tier, allow_hyphen=False):
    """Return a trustworthy unit name, or None.

    Refuses joint/regional/multi-unit bodies: attaching a five-municipality
    authority to one municipality points a community at the wrong government."""
    if not name:
        return None
    name = re.sub(r"\s+", " ", name).strip(" -,")
    if len(name) < 2 or len(name) > 80:
        return None
    if JOINT_MARKERS.search(name) or SPLIT_MARKERS.search(name):
        return None
    if not allow_hyphen and "-" in name:
        return None
    if re.fullmatch(r"[\W\d_]+", name):
        return None
    return name


# ----------------------------------------------------------------------------
# verification
# ----------------------------------------------------------------------------

def check_url(url, contact, session=None, timeout=20, retries=1):
    import requests

    sess = session or requests.Session()
    headers = {"User-Agent": f"local-map-harvester (+{contact})"}
    for attempt in range(retries + 1):
        try:
            r = sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            title = ""
            m = re.search(r"<title[^>]*>(.*?)</title>", r.text or "", re.I | re.S)
            if m:
                title = re.sub(r"\s+", " ", TAG_RE.sub("", m.group(1))).strip()[:200]
            return (r.status_code < 400), r.status_code, r.url, title
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                return False, f"error:{type(exc).__name__}", url, ""
            time.sleep(1.5 * (attempt + 1))
    return False, "unknown", url, ""


def fetch_json(url, contact, params=None, timeout=180):
    import requests

    headers = {"User-Agent": f"local-map-harvester (+{contact})",
               "Accept": "application/sparql-results+json,application/json"}
    r = requests.get(url, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ----------------------------------------------------------------------------
# harvest
# ----------------------------------------------------------------------------

def records_for_source(src, contact):
    kind = src["kind"]
    if kind == "wikidata":
        q = WIKIDATA_QUERY % {"class_qid": src["class_qid"],
                              "country_qid": src["country_qid"],
                              "lang": src.get("lang", "en")}
        return parse_wikidata(fetch_json(WIKIDATA_SPARQL, contact,
                                         params={"query": q, "format": "json"}))
    if kind == "overpass":
        q = OVERPASS_QUERY % {"iso3": src["iso3"],
                              "levels": "|".join(str(l) for l in src["levels"])}
        return parse_overpass(fetch_json(OVERPASS, contact, params={"data": q}))
    if kind == "arcgis":
        return parse_arcgis(fetch_json(src["url"], contact), src.get("fields", {}))
    if kind == "html":
        import requests
        headers = {"User-Agent": f"local-map-harvester (+{contact})"}
        r = requests.get(src["url"], headers=headers, timeout=60)
        r.raise_for_status()
        return parse_html(r.text, src.get("name_filter", r"."))
    raise ValueError(f"unknown source kind: {kind!r}")


def harvest(registry, contact, country=None, tier=None, limit=None,
            shard=None, sleep=0.3):
    entries, gaps = [], []
    stats = {"sources": 0, "records": 0, "emitted": 0, "no_url": 0,
             "dead_url": 0, "bad_unit": 0, "no_themed_page": 0, "dupe": 0}

    for iso3, tiers in sorted(registry.items()):
        if country and iso3 != country:
            continue
        for tname, spec in sorted(tiers.items()):
            if tier and tname != tier:
                continue
            land_authority = bool(spec.get("land_authority"))
            allow_hyphen = bool(spec.get("allow_hyphen"))
            seen = set()
            for src in spec.get("sources", []):
                stats["sources"] += 1
                try:
                    records = records_for_source(src, contact)
                except Exception as exc:  # noqa: BLE001
                    gaps.append({"country": iso3, "tier": tname, "unit": None,
                                 "reason": f"source_unreachable:{type(exc).__name__}",
                                 "source": src.get("id", src["kind"])})
                    continue

                for i, rec in enumerate(records):
                    if shard and (i % shard[1]) != shard[0]:
                        continue
                    stats["records"] += 1
                    if limit and stats["emitted"] >= limit:
                        break

                    unit = clean_unit(rec["unit"], tname, allow_hyphen)
                    if not unit:
                        stats["bad_unit"] += 1
                        gaps.append({"country": iso3, "tier": tname,
                                     "unit": rec["unit"], "reason": "unusable_unit_name",
                                     "source": src.get("id", src["kind"])})
                        continue
                    if not rec["url"]:
                        stats["no_url"] += 1
                        gaps.append({"country": iso3, "tier": tname, "unit": unit,
                                     "reason": "no_url",
                                     "source": src.get("id", src["kind"])})
                        continue
                    if rec["url"] in seen:
                        stats["dupe"] += 1
                        continue

                    ok, status, final, title = check_url(rec["url"], contact)
                    time.sleep(sleep)
                    if not ok:
                        stats["dead_url"] += 1
                        gaps.append({"country": iso3, "tier": tname, "unit": unit,
                                     "reason": f"dead_url:{status}", "url": rec["url"],
                                     "source": src.get("id", src["kind"])})
                        continue
                    if not is_themed(final, title, land_authority):
                        stats["no_themed_page"] += 1
                        gaps.append({"country": iso3, "tier": tname, "unit": unit,
                                     "reason": "no_themed_page", "url": final,
                                     "source": src.get("id", src["kind"])})
                        continue

                    seen.add(rec["url"])
                    entries.append({
                        "country": iso3,
                        "tier": tname,
                        "unit": unit,
                        "name": f"{unit} — {spec['body']}",
                        "url": final,
                        "tags": list(spec["tags"]),
                        "desc": spec["desc"].format(unit=unit, body=spec["body"]),
                        "source": src.get("id", src["kind"]),
                        "ref": rec.get("ref", ""),
                    })
                    stats["emitted"] += 1

    return entries, gaps, stats


# ----------------------------------------------------------------------------
# planning
# ----------------------------------------------------------------------------

# Rough published counts of local units, for honest progress reporting.
WORLD_UNIT_ESTIMATE = {"county": 47_000, "municipal": 500_000}


def print_plan(registry):
    print("registry coverage")
    print(f"  countries wired : {len(registry)}")
    for iso3, tiers in sorted(registry.items()):
        for tname, spec in sorted(tiers.items()):
            n = len(spec.get("sources", []))
            print(f"    {iso3} {tname:9s} body={spec['body'][:38]:40s} sources={n}")
    print()
    print("world scale (published estimates)")
    for tname, n in WORLD_UNIT_ESTIMATE.items():
        print(f"  {tname:9s} ~{n:,} units worldwide")
    print()
    print("note: units with no themed land/water/planning page are reported as")
    print("gaps, not emitted. Expect emitted << unit count in most countries.")


# ----------------------------------------------------------------------------
# selftest (no network)
# ----------------------------------------------------------------------------

def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    # unit hygiene
    eq(clean_unit("Ada", "county"), "Ada", "unit/simple")
    eq(clean_unit("Kootenai-Shoshone", "county"), None, "unit/joint-hyphen")
    eq(clean_unit("Saint-Étienne", "municipal", allow_hyphen=True),
       "Saint-Étienne", "unit/hyphen-allowed")
    eq(clean_unit("Baden-Baden", "municipal", allow_hyphen=True),
       "Baden-Baden", "unit/hyphen-allowed-de")
    eq(clean_unit("Communauté de communes du Val", "municipal", allow_hyphen=True),
       None, "unit/intercommunal-rejected")
    eq(clean_unit("Verbandsgemeinde Rhein-Nahe", "municipal", allow_hyphen=True),
       None, "unit/verbandsgemeinde-rejected")
    eq(clean_unit("Bath and North East Somerset", "county"), None, "unit/joint-and")
    eq(clean_unit("Regional District of Nanaimo", "county"), None, "unit/regional")
    eq(clean_unit("", "county"), None, "unit/empty")
    eq(clean_unit("   ", "county"), None, "unit/whitespace")
    eq(clean_unit("München", "municipal"), "München", "unit/unicode")

    # theme gate
    eq(is_themed("https://x.gov/planning/local-plan"), True, "theme/url")
    eq(is_themed("https://x.gov/", "Environment and waste"), True, "theme/title")
    eq(is_themed("https://x.gov/", "Council tax and bins"), False, "theme/homepage")
    eq(is_themed("https://x.gov/", "", body_is_land_authority=True), True,
       "theme/land-authority-exempt")

    # parsers
    wd = {"results": {"bindings": [
        {"unit": {"value": "http://www.wikidata.org/entity/Q42"},
         "unitLabel": {"value": "Sample Council"},
         "site": {"value": "https://sample.gov/environment"}},
        {"unit": {"value": "http://www.wikidata.org/entity/Q43"},
         "unitLabel": {"value": "Q43"},
         "site": {"value": "https://x.gov"}},
    ]}}
    r = parse_wikidata(wd)
    eq(len(r), 1, "wikidata/drops-unlabelled")
    eq(r[0]["ref"], "Q42", "wikidata/ref")

    ov = {"elements": [
        {"type": "relation", "id": 7, "tags": {"name": "Testville",
                                               "contact:website": "example.org/parks"}},
        {"type": "relation", "id": 8, "tags": {"name": "NoSite"}},
    ]}
    r2 = parse_overpass(ov)
    eq(len(r2), 1, "overpass/requires-website")
    eq(r2[0]["url"], "https://example.org/parks", "overpass/scheme-added")

    ag = parse_arcgis({"features": [{"attributes": {"NAME": "Adams",
                                                    "URL": "https://a.org/land"}}]}, {})
    eq(ag[0]["unit"], "Adams", "arcgis/unit")

    ht = parse_html('<a href="https://c.gov/planning">Ada &amp; District</a>'
                    '<a href="/rel">Rel</a>')
    eq(len(ht), 1, "html/absolute-only")
    eq(ht[0]["unit"], "Ada & District", "html/unescape")
    eq(clean_unit(ht[0]["unit"], "county"), None, "html/joint-rejected-downstream")

    # registry validation
    try:
        load_registry_obj({"countries": {"US": {"county": {}}}})
        fails.append("registry/bad-iso3 not rejected")
    except ValueError:
        pass
    try:
        load_registry_obj({"countries": {"USA": {"county": {"body": "b",
                                                            "tags": [], "desc": "no placeholder"}}}})
        fails.append("registry/missing-placeholder not rejected")
    except ValueError:
        pass

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK ({24} checks)")
    return 0


def load_registry_obj(data):
    """load_registry for an in-memory object (used by selftest)."""
    countries = data.get("countries", data)
    for iso3, tiers in countries.items():
        if not re.fullmatch(r"[A-Z]{3}", iso3):
            raise ValueError(f"country key must be ISO3: {iso3!r}")
        for tier, spec in tiers.items():
            if tier not in TIERS:
                raise ValueError(f"{iso3}: bad tier {tier!r}")
            for key in REQUIRED_BODY_KEYS:
                if key not in spec:
                    raise ValueError(f"{iso3}.{tier}: missing {key!r}")
            if "{unit}" not in spec["desc"]:
                raise ValueError(f"{iso3}.{tier}: desc must contain {{unit}}")
    return countries


# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="registry.json")
    ap.add_argument("--out", default="local_adds.json")
    ap.add_argument("--contact", default=os.environ.get("HARVEST_CONTACT", ""))
    ap.add_argument("--country", default="")
    ap.add_argument("--tier", default="", choices=["", *TIERS])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="", help="i/N, e.g. 3/32")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--plan", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    try:
        registry = load_registry(args.registry)
    except ValueError as exc:
        print(f"registry error: {exc}", file=sys.stderr)
        return 2

    if args.plan:
        print_plan(registry)
        return 0

    if not registry:
        print(f"no countries in {args.registry}; nothing to harvest.", file=sys.stderr)
        return 1
    if not args.contact:
        print("error: --contact required", file=sys.stderr)
        return 2

    shard = None
    if args.shard:
        i, n = args.shard.split("/")
        shard = (int(i), int(n))

    entries, gaps, stats = harvest(registry, args.contact,
                                   args.country or None, args.tier or None,
                                   args.limit or None, shard)

    with open(args.out, "w") as fh:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(),
                   "entries": entries, "gaps": gaps, "stats": stats},
                  fh, indent=1, sort_keys=True, ensure_ascii=False)

    print(f"sources {stats['sources']} | records {stats['records']} | "
          f"emitted {stats['emitted']} | dead {stats['dead_url']} | "
          f"unthemed {stats['no_themed_page']} | bad_unit {stats['bad_unit']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
