#!/usr/bin/env python3
"""Validate trackerdata.json. Fails loudly on the defect classes that have actually
bitten this project rather than on hypothetical ones.

Every check here exists because a real defect got through:

  empty_url        POST, Thousand Currents and Urgent Action Fund each sat in the map
                   with no url at all. The renderer links the name, so an empty url is
                   a dead link on a body the user is being told to contact.
  bad_tier         index.html coerces any tier that is not exactly 'county' or
                   'municipal' to 'state'. A typo therefore degrades SILENTLY - the
                   entry renders, just in the wrong tab. This check makes it loud.
  bad_tag          tags outside VALID_TAGS.txt do not match any lens, so the entry is
                   invisible under every filter.
  directory_url    an entry pointing at a third-party directory listing instead of the
                   body's own site. Allowed only for entries that ARE directories.
  dupe_in_bucket   the same url twice in one bucket.
  bad_scheme       a url that is not http(s).

Exit code is the number of ERROR-severity findings, so it works in CI.
WARN findings are reported but do not fail the run.

Usage:
  python3 validate_trackerdata.py selftest
  python3 validate_trackerdata.py check trackerdata.json [VALID_TAGS.txt]
"""
import json, re, sys, os
from collections import Counter

# index.html tieredPopHTML(): anything not exactly 'county' or 'municipal' falls into
# the State group. So an unknown tier still RENDERS - just in the State tab - which is
# why a typo degrades silently and needs a loud check here.
#
# 'state' was retired by patch_trackerdata_tier_normalise.py: the 3 legacy entries that
# used it are now 'subnational', which renders identically. That frees 'state' to be a
# pure error signal. Before that patch it had to be tolerated as a warning, and a real
# typo could not be told apart from a deliberate value.
KNOWN_TIERS = {"subnational", "county", "municipal"}
LEGACY_TIERS = set()

DIRECTORY_HOSTS = ("landcan.org", "landtrustalliance.org", "mltn.org",
                   "guidestar.org", "idealist.org", "propublica.org",
                   "influencewatch.org", "findlaw.com")

# Entries that legitimately point at a directory, because being a directory is the
# service they provide. Matched by exact url.
DIRECTORY_ALLOWLIST = {
    "https://landtrustalliance.org/",
    "https://landtrustalliance.org/take-action/conserve-your-land/how-to-conserve-your-land",
    "https://www.landcan.org/grant-and-assistance-programs/",
    "https://www.propublica.org/",
}


def _norm(u):
    """Normalise a url for identity comparison.

    Strips scheme and a leading 'www.' as well as the trailing slash. Without this,
    Croatia's THREE rows for the Information Commissioner (https://pristupinfo.hr,
    https://pristupinfo.hr/ and https://www.pristupinfo.hr/) counted as two distinct
    urls and only one duplicate was reported. Scheme is stripped too, so an http and
    https row for the same site are recognised as the same destination.
    """
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def walk(node, state=None):
    """Yield (bucket_label, entry) for every entry under a country node."""
    for t in node.get("trackers", []):
        yield (state or "(national)", t)
    for k, s in node.get("sub", {}).items():
        yield from walk(s, state or k)


# The three lenses this map is built around. An entry carrying one of these tags is
# a resource someone is meant to USE, which is why actionability is checked for them
# and not for reference entries like court registries.
LENS_TAGS = {"conserve:acquire", "conserve:protect", "organizing:fund", "organizing:legal"}


def check(data, valid_tags):
    findings = []          # (severity, code, bucket, name, detail)

    def add(sev, code, bucket, name, detail):
        findings.append((sev, code, bucket, name, detail))

    for iso, country in data.items():
        seen = {}
        for bucket, t in walk(country):
            name = t.get("name", "?")
            label = f"{iso}/{bucket}"
            # An entry nested inside an admin-1 bucket must state its tier explicitly.
            # The renderer coerces anything not exactly 'county'/'municipal' into the
            # State tab, so an untiered in-bucket entry DISPLAYS as state-level while the
            # data says nothing. That silent coercion hid a miscount of 189 entries
            # across a whole session: tools that classify by the tier field alone read
            # them as national. patch_trackerdata_tier_explicit.py set them all; this
            # check keeps it that way.
            if bucket != "(national)" and not t.get("tier"):
                add("ERROR", "missing_tier", label, name,
                    "in an admin-1 bucket but no tier - renders as state, data is silent")

            url = t.get("url", "")

            # ACTIONABILITY, and deliberately a WARNING not an ERROR.
            # A lens entry exists so someone can act: apply, file, qualify, object. The
            # entries that do that name a statute section, a deadline, a membership
            # floor, a fee, a percentage - so they carry a digit. An audit of 1,054
            # lens-tagged entries found 269 (25%) with no digit anywhere, clustered in
            # the earliest-written anglophone tier (ZAF 73%, AUS 50%, USA 35%) against
            # 0-1% in later work. The digit is a PROXY, not a standard: a no-digit entry
            # naming a specific programme in words can be fine, and a land trust's
            # usefulness may genuinely be "it buys land in this state". So this never
            # fails a build - it produces a worklist.
            # REFINEMENT (after two enrichment passes): the digit proxy has a real
            # false-positive class. Some entries are actionable through STRUCTURE
            # rather than through a number - they tell the reader WHERE TO GO FIRST,
            # WHAT ORDER TO DO THINGS IN, or WHICH BODY IS THE FRONT DOOR. Examples
            # that were being flagged wrongly: SALC ("works through local counsel
            # rather than taking clients directly"), the EDO Pasifika entries after
            # they were given a named national partner, Slovakia's sequencing entry,
            # and Uruguay's platform-links-to-ministry finding. A routing or
            # sequencing marker is evidence of actionability just as a threshold is.
            desc_t = t.get("desc", "")
            has_digit = bool(re.search(r"\d", desc_t))
            has_route = bool(re.search(
                r"(?i)\b(your national|national partner|front door|apply to your|"
                r"office near you|go to them|rather than|before you|first step|"
                r"starts with|then apply|only after|works through)\b", desc_t))
            if LENS_TAGS & set(t.get("tags", [])) and not (has_digit or has_route):
                add("WARNING", "low_actionability", label, name,
                    "lens entry with no statute, deadline, threshold, figure or routing step")

            # An entry may DECLARE that no website exists, rather than being pushed
            # toward guessing one. Set "noWebsite" to a non-empty string giving the
            # reason. This exists because the only alternatives were a url or an
            # error, and that pressure is exactly what the no-fabrication rule is
            # meant to remove. A declared absence must still say WHY, so a bare
            # true/empty value is itself an error.
            declared = t.get("noWebsite")
            if declared is not None:
                if not (isinstance(declared, str) and declared.strip()):
                    add("ERROR", "bad_no_website", label, name,
                        "noWebsite must be a non-empty reason string")
                elif url.strip():
                    add("ERROR", "no_website_with_url", label, name,
                        "declares noWebsite but also has a url")
                # a properly declared absence is not an empty_url error
            elif not url.strip():
                add("ERROR", "empty_url", label, name, "no url")
            elif not re.match(r"^https?://", url.strip(), re.I):
                add("ERROR", "bad_scheme", label, name, url[:60])
            else:
                # URL HYGIENE. Twice in one session I introduced a broken link by
                # RETYPING a url instead of copying it: 'subventions-de-project' for
                # 'subventions-de-projet', and 'Generico.pdf' for 'Gen%C3%A9rico.pdf'.
                # Both were URLs containing or adjacent to non-ASCII characters. A
                # fabricated link is worse than no link, so these are ERRORs.
                u = url.strip()
                if any(ord(ch) > 127 for ch in u):
                    add("ERROR", "unencoded_url", label, name,
                        "raw non-ASCII in url - percent-encode it or copy the real link")
                # a stray % that is not a valid %XX escape means the encoding was
                # hand-edited and is now wrong
                for m in re.finditer(r"%(.{0,2})", u):
                    if not re.fullmatch(r"[0-9A-Fa-f]{2}", m.group(1)):
                        add("ERROR", "bad_percent_escape", label, name,
                            f"malformed %-escape near {m.group(0)!r}")
                        break
                if re.search(r"\s", u):
                    add("ERROR", "whitespace_in_url", label, name, "url contains whitespace")

            tier = t.get("tier")
            if tier is not None:
                if tier not in KNOWN_TIERS:
                    detail = ("retired value; use 'subnational'"
                              if tier == "state"
                              else f"{tier!r} silently renders in the State tab")
                    add("ERROR", "bad_tier", label, name, detail)
                elif tier in LEGACY_TIERS:
                    add("WARN", "legacy_tier", label, name, f"{tier!r}")

            for tag in t.get("tags", []):
                if tag not in valid_tags:
                    add("ERROR", "bad_tag", label, name, tag)

            if url.strip() and _norm(url) not in {_norm(u) for u in DIRECTORY_ALLOWLIST}:
                if any(h in url.lower() for h in DIRECTORY_HOSTS):
                    add("WARN", "directory_url", label, name, url[:70])

            key = (label, _norm(url))
            if url.strip():
                if key in seen:
                    add("ERROR", "dupe_in_bucket", label, name, url[:60])
                seen[key] = True

    return findings


# --------------------------------------------------------------------------
def selftest():
    n = 0
    tags = {"organizing:help", "conserve:acquire"}

    def ok(cond, label):
        nonlocal n
        assert cond, "FAILED: " + label
        n += 1

    def mk(entries, sub=None):
        c = {"name": "X", "trackers": entries}
        if sub: c["sub"] = sub
        return {"USA": c}

    def codes(d): return {f[1] for f in check(d, tags)}
    def sev(d, code):
        return next((f[0] for f in check(d, tags) if f[1] == code), None)

    good = {"name": "A", "url": "https://a.org/", "tags": ["organizing:help"]}
    ok(not check(mk([good]), tags), "clean entry passes")

    ok("empty_url" in codes(mk([{**good, "url": ""}])), "empty url caught")
    ok("empty_url" in codes(mk([{**good, "url": "   "}])), "whitespace url caught")

    # a DECLARED absence of website is not an error
    ok(not check(mk([{"name": "A", "url": "", "tags": ["organizing:help"],
                      "noWebsite": "committee has no site; see desc"}]), tags),
       "declared noWebsite passes")
    ok("bad_no_website" in codes(mk([{**good, "url": "", "noWebsite": True}])),
       "noWebsite must carry a reason")
    ok("bad_no_website" in codes(mk([{**good, "url": "", "noWebsite": "  "}])),
       "blank reason rejected")
    ok("no_website_with_url" in codes(mk([{**good, "noWebsite": "reason"}])),
       "noWebsite plus a url is contradictory")
    ok("bad_scheme" in codes(mk([{**good, "url": "ftp://a.org"}])), "bad scheme caught")
    ok("bad_tag" in codes(mk([{**good, "tags": ["nope:nope"]}])), "bad tag caught")

    # the silent-degradation case
    ok("bad_tier" in codes(mk([{**good, "tier": "Country"}])), "typo tier caught")
    ok("bad_tier" not in codes(mk([{**good, "tier": "county"}])), "valid tier passes")
    ok("bad_tier" in codes(mk([{**good, "tier": "state"}])),
       "retired 'state' tier is now an ERROR, not a warning")
    ok("bad_tier" in codes(mk([{**good, "tier": "subnatonal"}])), "typo tier caught")
    ok("bad_tier" not in codes(mk([{**good, "tier": "subnational"}])), "subnational passes")

    # in-bucket entries must declare a tier; top-level ones must not be forced to
    nested = {"X": {"trackers": [], "sub": {"A": {"trackers": [
        {"name": "n", "url": "https://a.org", "tags": ["organizing:help"]}]}}}}
    ok("missing_tier" in {f[1] for f in check(nested, tags)},
       "untiered in-bucket entry flagged")
    nested["X"]["sub"]["A"]["trackers"][0]["tier"] = "subnational"
    ok("missing_tier" not in {f[1] for f in check(nested, tags)},
       "tiered in-bucket entry passes")
    ok("missing_tier" not in codes(mk([good])),
       "top-level entry with no tier is fine - it is national")

    # url hygiene: the two mistakes I actually made this session
    ok("unencoded_url" in codes(mk([{**good, "url": "https://x.org/Gen\u00e9rico.pdf"}])),
       "raw non-ASCII in url caught")
    ok("unencoded_url" not in codes(mk([{**good, "url": "https://x.org/Gen%C3%A9rico.pdf"}])),
       "correctly percent-encoded url passes")
    ok("bad_percent_escape" in codes(mk([{**good, "url": "https://x.org/a%GGrico"}])),
       "non-hex percent escape caught")
    ok("bad_percent_escape" in codes(mk([{**good, "url": "https://x.org/a%"}])),
       "trailing percent caught")
    ok("bad_percent_escape" not in codes(mk([{**good, "url": "https://x.org/a%C3%A9b"}])),
       "valid escapes pass")
    ok("whitespace_in_url" in codes(mk([{**good, "url": "https://x.org/a b"}])),
       "whitespace inside url caught")
    ok(not any(c in codes(mk([good])) for c in
               ("unencoded_url", "bad_percent_escape", "whitespace_in_url")),
       "plain ascii url is clean")

    # actionability: WARNING only, and only for lens-tagged entries
    lens_nodigit = {**good, "tags": ["organizing:fund"], "desc": "A fund for groups."}
    ok("low_actionability" in codes(mk([lens_nodigit])),
       "lens entry with no digit is flagged")
    ok(sev(mk([lens_nodigit]), "low_actionability") == "WARNING",
       "actionability never fails a build")
    ok("low_actionability" not in codes(mk([{**lens_nodigit,
        "desc": "A fund for groups; minimum 30 members."}])),
       "a digit clears the flag")
    ok("low_actionability" not in codes(mk([{**good, "tags": ["courts:state"],
        "desc": "A court with no numbers."}])),
       "non-lens entries are not checked for actionability")
    ok("low_actionability" not in codes(mk([{**lens_nodigit,
        "desc": "SALC works through local counsel and partners."}])),
       "a routing marker clears the flag without a digit")
    ok("low_actionability" not in codes(mk([{**lens_nodigit,
        "desc": "Your national partner is the Fiji Environmental Law Association."}])),
       "naming the national front door clears the flag")
    ok("low_actionability" in codes(mk([{**lens_nodigit,
        "desc": "A helpful organisation that supports communities."}])),
       "a vague entry with neither digit nor route is still flagged")
    ok("bad_tier" not in codes(mk([good])), "absent tier is fine (=national)")

    # duplicates are per-bucket, since one url may serve several states
    ok("dupe_in_bucket" in codes(mk([good, dict(good)])), "dupe in one bucket caught")
    two = mk([], {"Maine": {"trackers": [good]}, "Ohio": {"trackers": [dict(good)]}})
    ok("dupe_in_bucket" not in codes(two), "same url in 2 states is NOT a dupe")

    d = mk([{**good, "url": "https://www.landcan.org/local-resources/X/1"}])
    ok("directory_url" in codes(d), "directory url warned")
    ok("directory_url" not in codes(mk([{**good, "url": "https://landtrustalliance.org/"}])),
       "allowlisted directory not warned")

    # url identity: www, scheme and trailing slash must not hide a duplicate.
    # Croatia had 3 rows for one body and only 1 was reported before this.
    ok(_norm("https://www.pristupinfo.hr/") == _norm("https://pristupinfo.hr"),
       "www and trailing slash normalise together")
    ok(_norm("http://a.org") == _norm("https://a.org/"), "scheme normalises")
    ok(_norm("https://a.org/x") != _norm("https://a.org/y"), "paths still distinguished")
    three = mk([good,
                {**good, "url": "https://www.a.org"},
                {**good, "url": "http://a.org/"}])
    ok(sum(1 for f in check(three, tags) if f[1] == "dupe_in_bucket") == 2,
       "3 rows for one url yield 2 dupe findings")

    # severity split: a directory_url is a WARN and must not fail the build
    warnonly = mk([{**good, "url": "https://www.landcan.org/local-resources/X/1"}])
    ok(not [f for f in check(warnonly, tags) if f[0] == "ERROR"],
       "warn-only input yields no errors")

    print("validate_trackerdata selftest: %d/%d passed" % (n, n))


def _load(src):
    """Load from a local path OR an http(s) url.

    The post-upload check is the point: after pushing trackerdata.json to GitHub,
    run this against the raw url. If a partial or stale file landed, the entry count
    and error count both move and you see it the same day. A 13 August upload to this
    repo silently lost 13 entries and nobody noticed for three weeks.
    """
    if re.match(r"^https?://", src, re.I):
        import urllib.request
        with urllib.request.urlopen(src, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    return json.load(open(src, encoding="utf-8"))


def _count_entries(data):
    n = 0
    for iso, country in data.items():
        for _bucket, _t in walk(country):
            n += 1
    return n


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "check" and len(sys.argv) > 2:
        data = _load(sys.argv[2])
        tagfile = sys.argv[3] if len(sys.argv) > 3 else "VALID_TAGS.txt"
        valid = set(open(tagfile).read().split()) if os.path.exists(tagfile) else set()
        if not valid:
            print("WARNING: no VALID_TAGS.txt found - tag checking disabled")
        res = check(data, valid) if valid else \
              [f for f in check(data, set()) if f[1] != "bad_tag"]
        errors = [f for f in res if f[0] == "ERROR"]
        warns = [f for f in res if f[0] == "WARN"]
        by_code = Counter(f[1] for f in res)
        print(f"COUNTRIES: {len(data)} | ENTRIES: {_count_entries(data)}")
        print(f"ERRORS: {len(errors)} | WARNINGS: {len(warns)}")
        for code, cnt in by_code.most_common():
            print(f"  {code}: {cnt}")
        for f in errors[:40]:
            print("  ERROR", f[1], "|", f[2], "|", f[3][:60], "|", f[4])
        for f in warns[:40]:
            print("  WARN ", f[1], "|", f[2], "|", f[3][:60], "|", f[4])
        sys.exit(len(errors))
    else:
        print(__doc__)
