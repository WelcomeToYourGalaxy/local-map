#!/usr/bin/env python3
"""
harvest_networks.py — bulk entries from NGO member directories.

WHY
---
Hand-adding runs at 1-3 verified entries per session. But the organisations
this map wants already exist in curated member directories, each holding
hundreds to thousands of groups that are on-theme BY CONSTRUCTION:

  Land Trust Alliance   ~950 member land trusts, conserving land in 93% of
                        US counties -> conserve:acquire + conserve:protect
  Waterkeeper Alliance  ~300 licensed Waterkeeper groups worldwide, each with
                        a named waterbody and citizen-suit standing
                        -> organizing:legal + conserve:protect
  Surfrider             ~80 US chapters fighting coastal development
  Sierra Club           ~64 chapters and several hundred local groups
  Riverkeeper/others    regional networks

One directory pass yields more on-theme entries than a year of manual rounds,
and every member is already vetted by its network.

RULES (unchanged, and load-bearing at this volume)
--------------------------------------------------
1. No fabricated URLs. Every emitted URL comes from the directory AND resolves.
2. No guessed geography. A member is placed at county/municipal tier only when
   its own name or the directory's own field says which unit it serves.
   Otherwise it goes to state tier, or is reported as a gap. Never invented.
3. Tags come from the NETWORK's registry entry, never inferred per member.
   A land trust gets acquire+protect because every LTA member holds land; a
   Waterkeeper gets legal because the licence requires enforcement capacity.
4. Members whose URL is dead, parked or redirects off-domain are gaps.

USAGE
  python3 harvest_networks.py --selftest
  python3 harvest_networks.py --registry networks.json --network lta \\
      --out network_adds.json --contact you@example.com
"""

import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# geography: reuse the "never guess" discipline
# ---------------------------------------------------------------------------

COUNTY_RE = re.compile(r"\b([A-Z][\w'\-]+(?:\s+[A-Z][\w'\-]+)?)\s+County\b")
JOINT_RE = re.compile(r"\b(and|&|/|regional|tri|inter)\b", re.I)


# --- country resolution for international networks ---------------------------
# Directories give country names in many spellings. pycountry handles the long
# tail; this table covers the common variants and political namings it misses.
# Anything unresolved is a GAP, never a guess: filing a Congolese group under
# the wrong Congo is worse than not filing it.
COUNTRY_ALIASES = {
    "uk": "GBR", "united kingdom": "GBR", "great britain": "GBR",
    "england": "GBR", "scotland": "GBR", "wales": "GBR",
    "usa": "USA", "united states": "USA", "u.s.": "USA", "america": "USA",
    "russia": "RUS", "south korea": "KOR", "north korea": "PRK",
    "iran": "IRN", "syria": "SYR", "vietnam": "VNM", "viet nam": "VNM",
    "laos": "LAO", "venezuela": "VEN", "bolivia": "BOL", "tanzania": "TZA",
    "czech republic": "CZE", "czechia": "CZE", "turkey": "TUR",
    "turkiye": "TUR", "t\u00fcrkiye": "TUR", "ivory coast": "CIV",
    "cote d'ivoire": "CIV", "c\u00f4te d'ivoire": "CIV",
    "cape verde": "CPV", "cabo verde": "CPV", "swaziland": "SWZ",
    "eswatini": "SWZ", "burma": "MMR", "myanmar": "MMR",
    "drc": "COD", "dr congo": "COD", "democratic republic of the congo": "COD",
    "congo-kinshasa": "COD", "republic of the congo": "COG",
    "congo-brazzaville": "COG", "moldova": "MDA", "macedonia": "MKD",
    "north macedonia": "MKD", "palestine": "PSE", "brunei": "BRN",
    "east timor": "TLS", "timor-leste": "TLS", "cape town": None,
}


def resolve_country(name):
    """Country name -> ISO3, or None. Never guesses."""
    if not name:
        return None
    key = re.sub(r"\s+", " ", str(name)).strip().lower().rstrip(".")
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if re.fullmatch(r"[A-Za-z]{3}", key) and key.upper() not in ("AND", "THE"):
        return key.upper()
    try:
        import pycountry
    except ImportError:
        return None
    try:
        hit = pycountry.countries.lookup(key)
        return hit.alpha_3
    except LookupError:
        return None


def unit_from_name(name):
    """'Sonoma County Land Trust' -> ('Sonoma County', 'county').

    Returns (None, 'subnational') when the name says nothing reliable — a
    region-shaped name like 'Coastal Prairie Conservancy' must not be pinned
    to one county."""
    if not name:
        return None, "subnational"
    m = COUNTY_RE.search(name)
    if not m:
        return None, "subnational"
    # reject joint bodies by looking at the text BEFORE "County" too:
    # "Bath and Wells County Trust" captures "Wells" but serves two places.
    lead = name[:m.start()] + m.group(1)
    if JOINT_RE.search(lead):
        return None, "subnational"
    return f"{m.group(1)} County", "county"


# ---------------------------------------------------------------------------
# extraction backends
# ---------------------------------------------------------------------------

LINK_RE = re.compile(
    r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>',
    re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")


def parse_json_members(payload, fields):
    """Directory exposed as JSON (WP REST, Algolia, custom API)."""
    rows = payload
    for key in fields.get("path", []):
        rows = rows.get(key, []) if isinstance(rows, dict) else []
    out = []
    for r in rows if isinstance(rows, list) else []:
        name = str(r.get(fields.get("name", "name"), "") or "").strip()
        url = str(r.get(fields.get("url", "website"), "") or "").strip()
        state = str(r.get(fields.get("state", "state"), "") or "").strip()
        if name and url:
            out.append({"name": name, "url": url, "state": state})
    return out


def parse_html_members(html, name_filter=r"."):
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
        out.append({"name": text, "url": href, "state": ""})
    return out


# ---------------------------------------------------------------------------
# endpoint discovery
# ---------------------------------------------------------------------------
# Member directories are JS map widgets: the HTML holds a headline and a donate
# button, and the 350 (or 1,000) organisations live behind an API the widget
# calls. Doing that lookup by hand means opening DevTools. This does it in
# Actions instead: fetch the page, pull every candidate endpoint out of it, try
# each, and report which ones return a list of records.

ENDPOINT_PATTERNS = [
    # WordPress REST, by far the most common for these sites
    (r"""["'](/?wp-json/[^"'\s]+)["']""", "wp-json"),
    (r"""["'](https?://[^"'\s]+/wp-json/[^"'\s]*)["']""", "wp-json"),
    # explicit fetch/axios/ajax calls in inline script
    (r"""(?:fetch|axios\.get|\$\.getJSON|\$\.ajax)\(\s*["']([^"']+)["']""", "call"),
    # data attributes used by map plugins to point at their source
    (r"""data-(?:src|url|endpoint|source|json|markers)=["']([^"']+)["']""", "data-attr"),
    # ArcGIS / Mapbox / Airtable / Algolia style sources
    (r"""["'](https?://[^"'\s]*(?:arcgis|airtable|algolia|mapbox)[^"'\s]*)["']""", "saas"),
    # bare .json references
    (r"""["']([^"'\s]+\.json(?:\?[^"'\s]*)?)["']""", "json-file"),
]

LIST_KEYWORDS = re.compile(
    r"(member|organi|waterkeeper|keeper|chapter|partner|group|affiliate|"
    r"trust|location|marker|map|store|directory|point)", re.I)


def find_endpoints(html, base_url=""):
    """Candidate data endpoints referenced by a directory page, ranked."""
    from urllib.parse import urljoin

    seen, out = set(), []
    for pat, kind in ENDPOINT_PATTERNS:
        for m in re.finditer(pat, html):
            raw = m.group(1).strip()
            if not raw or raw.startswith(("data:", "#", "mailto:")):
                continue
            url = urljoin(base_url, raw) if base_url else raw
            if not url.lower().startswith(("http://", "https://")):
                continue
            if url in seen:
                continue
            seen.add(url)
            score = 0
            if kind == "wp-json":
                score += 3
            if LIST_KEYWORDS.search(url):
                score += 2
            if url.endswith(".json"):
                score += 1
            out.append({"url": url, "kind": kind, "score": score})
    out.sort(key=lambda d: -d["score"])
    return out


def count_records(payload):
    """How many records does this response look like it holds, and under what key."""
    if isinstance(payload, list):
        return len(payload), []
    if not isinstance(payload, dict):
        return 0, []
    best = (0, [])
    for key in ("results", "records", "data", "features", "items",
                "members", "locations", "markers", "posts"):
        v = payload.get(key)
        if isinstance(v, list) and len(v) > best[0]:
            best = (len(v), [key])
    for key, v in payload.items():
        if isinstance(v, list) and len(v) > best[0]:
            best = (len(v), [key])
        elif isinstance(v, dict):
            n, path = count_records(v)
            if n > best[0]:
                best = (n, [key] + path)
    return best


SKIP_TYPES = {"post", "page", "attachment", "nav_menu_item", "wp_block",
              "wp_template", "wp_template_part", "wp_navigation", "wp_font_family",
              "wp_font_face", "wp_global_styles", "revision", "menu-item",
              "tribe_events", "tribe_venue", "tribe_organizer"}


def _probe_wp_types(root, headers, requests):
    """List WordPress post types and try each collection for records.

    A directory of 350 Waterkeepers or 1,000 GAIA members is almost always a
    custom post type - 'member', 'keeper', 'chapter', 'partner', 'organization'.
    The route table shows these as regex patterns, which is why the first pass
    missed them."""
    out = []
    try:
        t = requests.get(root + "/wp-json/wp/v2/types", headers=headers, timeout=45)
        types = t.json() if t.status_code < 400 else {}
    except Exception:
        return out
    if not isinstance(types, dict):
        return out
    for slug, meta in types.items():
        if slug in SKIP_TYPES:
            continue
        rest_base = (meta or {}).get("rest_base") or slug
        url = f"{root}/wp-json/wp/v2/{rest_base}?per_page=100"
        try:
            rr = requests.get(url, headers=headers, timeout=45)
            if rr.status_code >= 400:
                continue
            data = rr.json()
        except Exception:
            continue
        if not isinstance(data, list) or len(data) < 5:
            continue
        total = rr.headers.get("X-WP-Total") or len(data)
        keys = sorted(data[0].keys())[:16] if isinstance(data[0], dict) else []
        print(f"  TYPE   {total:>6} records  {url}")
        print(f"         fields: {', '.join(keys)}")
        out.append({"url": url, "records": int(total) if str(total).isdigit() else len(data),
                    "path": [], "sample_fields": keys, "post_type": slug})
    return out


def discover(page_url, contact, limit=25):
    """Fetch a directory page, try its endpoints, report which return records."""
    import requests

    headers = {"User-Agent": f"local-map-networks (+{contact})"}
    r = requests.get(page_url, headers=headers, timeout=60)
    r.raise_for_status()
    cands = find_endpoints(r.text, page_url)

    # WordPress sites expose their whole route table; ask for it directly.
    from urllib.parse import urlparse
    root = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    cands.insert(0, {"url": root + "/wp-json/", "kind": "wp-json-root", "score": 9})

    print(f"page: {page_url}")
    print(f"candidate endpoints found: {len(cands)}")
    hits = []
    for c in cands[:limit]:
        try:
            rr = requests.get(c["url"], headers=headers, timeout=45)
            if rr.status_code >= 400:
                continue
            data = rr.json()
        except Exception:
            continue
        if c["kind"] == "wp-json-root" and isinstance(data, dict):
            routes = [k for k in (data.get("routes") or {})
                      if LIST_KEYWORDS.search(k)]
            for rt in routes[:20]:
                print(f"  ROUTE  {root}/wp-json{rt}")
            # THE ACTUAL FIX: these sites keep members as WordPress CUSTOM POST
            # TYPES, not plugin APIs. The route table hides them behind regex
            # patterns, so ask for the type list and hit each collection.
            hits.extend(_probe_wp_types(root, headers, requests))
            continue
        n, path = count_records(data)
        if n >= 5:
            keys = []
            probe = data
            for p in path:
                probe = probe[p]
            if isinstance(probe, list) and isinstance(probe[0], dict):
                keys = sorted(probe[0].keys())[:14]
            hits.append({"url": c["url"], "records": n,
                         "path": path, "sample_fields": keys})
            print(f"  HIT    {n:6d} records  path={path or '(root list)'}  {c['url']}")
            print(f"         fields: {', '.join(keys)}")
    if not hits:
        print("  no endpoint returned a record list — the widget may need a POST "
              "or a key; check the page's XHR calls manually.")
    return hits


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

# --- anti-development screen -------------------------------------------------
# The map carries resources a community can use AGAINST a project. Some
# conservation bodies work the other side of the same transaction: mitigation
# and offset banks SELL credits that let a development proceed, and some trusts
# market themselves to developers as a permitting service. Those are not
# resister resources, whatever their conservation credentials.
PRO_DEVELOPMENT = re.compile(
    r"mitigation bank|compensatory mitigation|wetland credits?|"
    r"species banking|conservation banking|habitat credits?|"
    r"offset (credits?|banking|provider)|biodiversity (credits?|offsets?)|"
    r"credit sales|purchase credits|sell(ing)? credits|"
    r"we (help|assist|work with) developers|developer services|"
    r"permitting solutions|streamline (your )?permit", re.I)

# Wording that shows the same words used from the resister side, which must
# survive the screen ("we opposed the mitigation bank", "no net loss is a myth").
RESISTER_CTX = re.compile(
    r"(oppos|challeng|object|fight|defeat|block|reject|against|"
    r"campaign|petition|lawsuit|sued|sue )", re.I)


def is_pro_development(text):
    """True when a page markets credit sales or developer services."""
    if not text:
        return False
    if not PRO_DEVELOPMENT.search(text):
        return False
    return not RESISTER_CTX.search(text)


PARKED = re.compile(
    r"(domain (is )?for sale|buy this domain|parked (free|domain)|"
    r"godaddy|sedo\.com|hugedomains|namecheap parking|"
    r"account suspended|site not found|coming soon)", re.I)


def check(url, contact, timeout=20):
    """(ok, status, final_url, title). Parked and suspended pages fail."""
    import requests

    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True,
                         headers={"User-Agent": f"local-map-networks (+{contact})"})
    except Exception as exc:  # noqa: BLE001
        return False, f"error:{type(exc).__name__}", url, ""
    body = r.text or ""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", TAG_RE.sub("", m.group(1))).strip()[:200]
    if r.status_code >= 400:
        return False, r.status_code, r.url, title
    if PARKED.search(title) or PARKED.search(body[:4000]):
        return False, "parked", r.url, title
    if is_pro_development(TAG_RE.sub(" ", body[:20000])):
        return False, "pro_development", r.url, title
    return True, r.status_code, r.url, title


# ---------------------------------------------------------------------------
# harvest
# ---------------------------------------------------------------------------

def build_entry(spec, member, unit, tier):
    where = unit or member.get("state") or ""
    country = spec.get("country", "USA")
    if country == "GLOBAL":
        country = resolve_country(member.get("state")) or "UNRESOLVED"
    return {
        "country": country,
        "state": member.get("state", ""),
        "unit": unit,
        "tier": tier,
        "name": member["name"],
        "url": member["url"],
        "tags": list(spec["tags"]),
        "desc": spec["desc"].format(name=member["name"], where=where,
                                    network=spec["network"]),
        "network": spec["network"],
    }


def harvest(spec, contact, limit=None, sleep=0.3, fetcher=None):
    entries, gaps = [], []
    stats = collections.Counter()

    records = fetcher(spec) if fetcher else fetch_members(spec, contact)
    seen = set()
    for rec in records:
        stats["records"] += 1
        if limit and stats["emitted"] >= limit:
            break
        url = rec["url"].strip()
        if not url:
            stats["no_url"] += 1
            gaps.append({"name": rec["name"], "reason": "no_url"})
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            stats["dupe"] += 1
            continue
        ok, status, final, title = check(url, contact)
        time.sleep(sleep)
        if not ok:
            reason = "pro_development" if status == "pro_development" else "dead"
            stats[reason] += 1
            gaps.append({"name": rec["name"], "url": url,
                         "reason": f"{reason}:{status}"})
            continue
        if spec.get("country") == "GLOBAL" and not resolve_country(rec.get("state")):
            stats["no_country"] += 1
            gaps.append({"name": rec["name"], "country_field": rec.get("state"),
                         "reason": "country_unresolved"})
            continue
        unit, tier = unit_from_name(rec["name"])
        if tier == "subnational" and spec.get("require_local"):
            stats["not_local"] += 1
            gaps.append({"name": rec["name"], "reason": "no_local_unit"})
            continue
        seen.add(key)
        rec["url"] = final
        entries.append(build_entry(spec, rec, unit, tier))
        stats["emitted"] += 1
    return entries, gaps, dict(stats)


def fetch_members(spec, contact):
    import requests

    headers = {"User-Agent": f"local-map-networks (+{contact})"}
    r = requests.get(spec["url"], headers=headers, timeout=90)
    r.raise_for_status()
    if spec["kind"] == "json":
        return parse_json_members(r.json(), spec.get("fields", {}))
    if spec["kind"] == "html":
        return parse_html_members(r.text, spec.get("name_filter", "."))
    raise ValueError(f"unknown kind {spec['kind']!r}")


# ---------------------------------------------------------------------------

def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    eq(unit_from_name("Sonoma County Land Trust"), ("Sonoma County", "county"),
       "unit/county-named")
    eq(unit_from_name("Kittitas County Conservation Trust"),
       ("Kittitas County", "county"), "unit/county-named-2")
    eq(unit_from_name("Coastal Prairie Conservancy"), (None, "subnational"),
       "unit/region-not-guessed")
    eq(unit_from_name("Triangle Land Conservancy"), (None, "subnational"),
       "unit/region-not-guessed-2")
    eq(unit_from_name("Bath and Wells County Trust")[1], "subnational",
       "unit/joint-rejected")
    eq(unit_from_name(""), (None, "subnational"), "unit/empty")

    eq(is_pro_development(
        "We operate a wetland mitigation bank and sell credits to developers"),
        True, "prodev/mitigation-bank")
    eq(is_pro_development("Conservation banking and habitat credits available"),
       True, "prodev/species-banking")
    eq(is_pro_development("Developer services: permitting solutions"), True,
       "prodev/developer-services")
    eq(is_pro_development(
        "We opposed the proposed mitigation bank at the county hearing"),
        False, "prodev/resister-context-survives")
    eq(is_pro_development(
        "Our land trust buys land and holds conservation easements"), False,
        "prodev/ordinary-land-trust")
    eq(is_pro_development(""), False, "prodev/empty")

    eq(resolve_country("United Kingdom"), "GBR", "iso/uk")
    eq(resolve_country("Türkiye"), "TUR", "iso/turkiye")
    eq(resolve_country("DR Congo"), "COD", "iso/drc")
    eq(resolve_country("Republic of the Congo"), "COG", "iso/congo-b")
    eq(resolve_country("KEN"), "KEN", "iso/passthrough")
    eq(resolve_country("Atlantis"), None, "iso/unknown-not-guessed")
    eq(resolve_country(""), None, "iso/empty")

    def coerce(v):
        try:
            return int(str(v).strip() or 0)
        except ValueError:
            return 0
    eq(coerce(""), 0, "args/empty-limit-is-zero")
    eq(coerce("25"), 25, "args/numeric-limit")
    eq(coerce(" "), 0, "args/whitespace-limit")
    eq(coerce("junk"), 0, "args/junk-limit-does-not-crash")

    eq(bool(PARKED.search("This domain is for sale")), True, "parked/for-sale")
    eq(bool(PARKED.search("Sonoma Land Trust — Home")), False, "parked/real")

    rows = parse_json_members(
        {"data": {"members": [
            {"org": "Ada County Land Trust", "site": "https://a.org", "st": "ID"},
            {"org": "No Site Trust", "site": "", "st": "ID"}]}},
        {"path": ["data", "members"], "name": "org", "url": "site",
         "state": "st"})
    eq(len(rows), 1, "json/requires-url")
    eq(rows[0]["state"], "ID", "json/state")

    html = ('<a href="https://x.org">Marin County Land Trust</a>'
            '<a href="/rel">Relative</a>')
    eq(len(parse_html_members(html)), 1, "html/absolute-only")

    spec = {"network": "LTA", "country": "USA",
            "tags": ["conserve:acquire", "conserve:protect"],
            "desc": "WHAT IT DOES: {name}, a {network} member land trust "
                    "serving {where}."}
    e = build_entry(spec, {"name": "Ada County Land Trust",
                           "url": "https://a.org", "state": "ID"},
                    "Ada County", "county")
    eq(e["tier"], "county", "entry/tier")
    eq("Ada County" in e["desc"], True, "entry/desc-filled")
    eq(e["tags"], ["conserve:acquire", "conserve:protect"], "entry/tags-from-spec")

    # end-to-end with a stub fetcher and stubbed checker
    global check
    real_check = check
    check = lambda url, contact, timeout=20: (  # noqa: E731
        ("dead" not in url), 200, url, "ok")
    try:
        entries, gaps, stats = harvest(
            spec, "x@y.z", fetcher=lambda s: [
                {"name": "Ada County Land Trust", "url": "https://a.org",
                 "state": "ID"},
                {"name": "Dead Trust", "url": "https://dead.org", "state": "ID"},
                {"name": "Ada County Land Trust", "url": "https://a.org/",
                 "state": "ID"}],
            sleep=0)
    finally:
        check = real_check
    eq(stats["emitted"], 1, "harvest/emits-live-only")
    eq(stats["dead"], 1, "harvest/counts-dead")
    eq(stats["dupe"], 1, "harvest/dedups-trailing-slash")

    html = ('<script>fetch("/wp-json/wk/v1/members?per_page=500")</script>'
            '<div data-src="https://x.org/locations.json"></div>'
            '<script src="https://cdn.example.com/lib.js"></script>'
            '<a href="mailto:a@b.c">mail</a>')
    eps = find_endpoints(html, "https://waterkeeper.org/findyourwaterkeeper/")
    urls = [e["url"] for e in eps]
    eq(any("wp-json/wk/v1/members" in u for u in urls), True, "discover/finds-wp-json")
    eq(any("locations.json" in u for u in urls), True, "discover/finds-data-attr")
    eq(any(u.startswith("mailto") for u in urls), False, "discover/skips-mailto")
    eq(eps[0]["score"] >= eps[-1]["score"], True, "discover/ranked")
    eq(urls[0].startswith("https://waterkeeper.org/wp-json"), True,
       "discover/resolves-relative")

    eq(count_records([1, 2, 3]), (3, []), "count/bare-list")
    eq(count_records({"results": [1, 2]})[0], 2, "count/named-list")
    eq(count_records({"data": {"members": [1, 2, 3, 4]}}), (4, ["data", "members"]),
       "count/nested-path")
    eq(count_records({"ok": True})[0], 0, "count/no-list")

    eq("post" in SKIP_TYPES and "page" in SKIP_TYPES, True, "types/skips-builtin")
    eq("member" in SKIP_TYPES, False, "types/keeps-custom")
    eq("tribe_events" in SKIP_TYPES, True, "types/skips-events-plugin")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (46 checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="networks.json")
    ap.add_argument("--network", default="")
    ap.add_argument("--out", default="network_adds.json")
    ap.add_argument("--contact", default=os.environ.get("HARVEST_CONTACT", ""))
    # Scheduled runs and blank workflow inputs arrive as "", which argparse
    # rejects as an int. Parse as text and coerce, so an empty field means
    # "no limit" rather than a failed job.
    ap.add_argument("--limit", default="0")
    ap.add_argument("--discover", default="",
                    help="directory page URL: find its data endpoint and stop")
    ap.add_argument("--discover-all", action="store_true",
                    help="run discovery for every network with a 'page' in the registry")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    if args.discover:
        if not args.contact:
            print("error: --contact required", file=sys.stderr)
            return 2
        discover(args.discover, args.contact)
        return 0

    if args.discover_all:
        if not args.contact:
            print("error: --contact required", file=sys.stderr)
            return 2
        specs = json.load(open(args.registry)).get("networks", [])
        for spec in specs:
            page = spec.get("page")
            if not page:
                continue
            print(f"\n=== {spec['network']} ===")
            try:
                discover(page, args.contact)
            except Exception as exc:  # noqa: BLE001
                print(f"  unreachable: {type(exc).__name__}")
        return 0

    if not args.contact:
        print("error: --contact required", file=sys.stderr)
        return 2
    if not os.path.exists(args.registry):
        print(f"no registry at {args.registry}", file=sys.stderr)
        return 1

    try:
        limit = int(str(args.limit).strip() or 0)
    except ValueError:
        limit = 0

    specs = json.load(open(args.registry)).get("networks", [])
    if args.network:
        specs = [s for s in specs if s.get("network") == args.network]
    if not specs:
        print("no matching networks", file=sys.stderr)
        return 1

    all_entries, all_gaps, totals = [], [], collections.Counter()
    for spec in specs:
        try:
            e, g, s = harvest(spec, args.contact, limit or None)
        except Exception as exc:  # noqa: BLE001
            all_gaps.append({"network": spec.get("network"),
                             "reason": f"unreachable:{type(exc).__name__}"})
            continue
        all_entries += e
        all_gaps += g
        totals.update(s)
        print(f"{spec['network']}: emitted {s.get('emitted',0)} "
              f"dead {s.get('dead',0)} not_local {s.get('not_local',0)}")

    json.dump({"generated": datetime.now(timezone.utc).isoformat(),
               "entries": all_entries, "gaps": all_gaps,
               "stats": dict(totals)},
              open(args.out, "w"), indent=1, ensure_ascii=False)
    print(f"total emitted {len(all_entries)} | gaps {len(all_gaps)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
