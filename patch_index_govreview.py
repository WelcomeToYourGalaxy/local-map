#!/usr/bin/env python3
"""
patch_index_govreview.py — one courthouse layer, and an honest test for every office.

1. DUPLICATE COURTHOUSE LAYER
   The filter listed both 'ch' (the external set, which returns nothing: 0) and
   'c' (the repo file: 26,267). Two rows, one of them permanently empty. 'ch' is
   dropped from the list and FACDESC['c'] inherits its description, so the
   surviving row keeps the explanation.

2. THE OFFICE PROBLEM, PROPERLY
   An Armed Forces Recruitment Center was being told that "the Army Corps
   handles wetlands", and an Election Center that it issues environmental
   permits. Adding another regex for each wrong case is endless: the
   government-office layer is every public building OSM knows, in every
   language, so the list of things that are NOT land bodies has no end.

   Inverted: instead of listing what to exclude, require a reason to show the
   permits-and-records briefing at all. An office gets it only if its name
   indicates land, environment, water, planning, transport, resources, records
   or revenue — the functions the briefing actually describes. Everything else
   gets one honest line saying it has no role in development decisions and
   pointing at the body that does.

   That way a recruitment centre, an election office, a benefits office, a
   licensing counter and the thousands of untranslated names nobody has thought
   of all behave correctly by default, rather than by enumeration.

Idempotent. Requires patch_index_gofix.py and patch_index_courtdata.py.

USAGE
  python3 patch_index_govreview.py index.html
  python3 patch_index_govreview.py --selftest
"""

import re
import sys

MARKER = "/* govreview (patch_index_govreview) */"

JS_BLOCK = """
/* govreview (patch_index_govreview) */
/* The briefing about permits, EIA and land records is only true of offices that
   handle land, environment, water, planning, transport, resources, records or
   revenue. Requiring a positive reason to show it is the only approach that
   scales: the layer holds every public building OSM knows, in every language,
   so the list of things that are NOT land bodies is unbounded. */
var GO_RELEVANT=new RegExp(
  "planning|zoning|land|property|cadast|survey|deeds|registry|register|recorder|"+
  "assessor|valuation|environment|ecolog|conservation|natural resource|forest|"+
  "wildlife|fisher|water|marine|coastal|river|watershed|irrigation|"+
  "agricultur|farm|rural|mines|mining|geolog|energy|petroleum|"+
  "transport|highway|roads|railway|\\bport\\b|\\bports\\b|harbour|harbor|aviation|"+
  "public works|infrastructur|utilit|sanitat|waste|sewer|drainage|"+
  "building|construction|housing|development|permit|licens|inspector|"+
  "revenue|tax|treasur|"+
  /* the same functions in the other languages this layer carries */
  "urbanism|urbanismo|ambient|medio ambiente|meio ambiente|catastro|catasto|"+
  "kadaster|kataster|grundbuch|bauamt|umwelt|wasser|forst|liegenschaft|"+
  "amenagement|environnement|cadastre|urbanisme|prefecture|"+
  "territorio|ordenamiento|obras|recursos|"+
  "pertanahan|lingkungan|tata ruang|kehutanan", "i");

function _goRelevant(name){ return GO_RELEVANT.test(String(name||'')); }
var GO_NOT_RELEVANT_NOTE='<div class="fac-why"><b>No role in development decisions</b>'
  +'<br>This office does not review, permit or record land use \\u2014 nothing here can '
  +'stop, approve or document a project. For that, use the <b>town hall or planning '
  +'department</b> for local decisions and the <b>environmental agency</b> for permits; '
  +'both are marked on this map.</div>';
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    for dep in ("_goKindNote", "FACDESC", "_gvNote"):
        if dep not in text:
            raise SystemExit(f"could not find {dep} — run the earlier patches first")

    text = text.replace("function _facPop(p){", JS_BLOCK + "\nfunction _facPop(p){", 1)

    # 1. one courthouse row, keeping the description
    old_order = "var order=['po','th','fs','go','mi','ch','c','p'];"
    if old_order not in text:
        raise SystemExit("could not find the filter order — aborting")
    text = text.replace(
        old_order,
        "var order=['po','th','fs','go','mi','c','p'];   /* 'ch' returned 0 and "
        "duplicated 'c' */", 1)
    text = text.replace(
        "FACLAB.c=FACLAB.ch; FACLAB.p=FACLAB.pr;",
        "FACLAB.c=FACLAB.ch; FACLAB.p=FACLAB.pr;\n"
        "try{ FACDESC.c=FACDESC.ch; FACDESC.p=FACDESC.pr; }catch(e){}", 1)

    # 2. relevance gate on the government-office briefing
    old_call = ("if(p.k==='go'||p.k==='mi'){ var _gk=_goKindNote(p.n);\n"
                "    /* an office with no power over development says so, and skips the\n"
                "       permits-and-records briefing that does not apply to it */\n"
                "    if(_gk){ s+=_gk; } else { s+=_gvNote(p.la,p.lo); } }")
    if old_call not in text:
        raise SystemExit("could not find the gov branch — aborting")
    new_call = ("if(p.k==='go'||p.k==='mi'){ var _gk=_goKindNote(p.n);\n"
                "    /* named type first; then a positive test for land/environment\n"
                "       function; otherwise say plainly that it does nothing here. */\n"
                "    if(_gk){ s+=_gk; }\n"
                "    else if(p.k==='mi'||_goRelevant(p.n)){ s+=_gvNote(p.la,p.lo); }\n"
                "    else { s+=GO_NOT_RELEVANT_NOTE; } }")
    text = text.replace(old_call, new_call, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = (
        "var FACDESC={ch:'Courthouses — where injunctions are filed',pr:'Prisons'};\n"
        "FACLAB.c=FACLAB.ch; FACLAB.p=FACLAB.pr;\n"
        "function _goKindNote(n){return '';}\n"
        "function _gvNote(a,b){return 'briefing';}\n"
        "function buildFacFilter(){ var order=['po','th','fs','go','mi','ch','c','p']; }\n"
        "function _facPop(p){ let s='a';\n"
        "  if(p.k==='go'||p.k==='mi'){ var _gk=_goKindNote(p.n);\n"
        "    /* an office with no power over development says so, and skips the\n"
        "       permits-and-records briefing that does not apply to it */\n"
        "    if(_gk){ s+=_gk; } else { s+=_gvNote(p.la,p.lo); } }\n"
        "  return s; }\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("'go','mi','c','p'" in out, True, "courthouse/ch-row-removed")
    eq("FACDESC.c=FACDESC.ch" in out, True, "courthouse/description-moved")
    eq("_goRelevant(p.n)" in out, True, "gov/relevance-gate")
    eq("GO_NOT_RELEVANT_NOTE" in out, True, "gov/honest-default")
    eq("p.k==='mi'||" in out, True, "gov/ministries-always-briefed")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("nothing")
        fails.append("patch/missing-deps not caught")
    except SystemExit:
        pass

    # the relevance test, on the names that were getting it wrong
    pat = re.search(r'var GO_RELEVANT=new RegExp\(\s*(.*?)\s*, "i"\);',
                    JS_BLOCK, re.S).group(1)
    src = "".join(re.findall(r'"([^"]*)"', pat))
    rx = re.compile(src, re.I)

    for name, want, label in (
            ("Armed Forces Recruitment Center", False, "recruitment"),
            ("L.A. County Election Center", False, "elections"),
            ("Social Security Administration", False, "ssa"),
            ("USCIS Application Support Center", False, "uscis"),
            ("Post Office", False, "post"),
            ("Public Library", False, "library"),
            ("Veterans Affairs Clinic", False, "veterans"),
            ("Passport Agency", False, "passport"),
            ("County Planning Department", True, "planning"),
            ("Department of Environmental Quality", True, "environment"),
            ("Water Resources Board", True, "water"),
            ("County Recorder of Deeds", True, "deeds"),
            ("Bureau of Land Management", True, "land"),
            ("Ministerio de Medio Ambiente", True, "spanish-environment"),
            ("Bauamt Stadt Köln", True, "german-building"),
            ("Direction de l'urbanisme", True, "french-planning"),
            ("Dinas Lingkungan Hidup", True, "indonesian-environment"),
            ("Highways Agency Depot", True, "transport"),
            ("Assessor's Office", True, "assessor"),
            ("Department of Motor Vehicles", False, "dmv")):
        got = bool(rx.search(name))
        if got != want:
            fails.append(f"relevant/{label}: {name!r} got {got} want {want}")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (9 checks + 20 office-name cases)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
