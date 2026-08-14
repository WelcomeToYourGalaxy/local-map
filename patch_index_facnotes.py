#!/usr/bin/env python3
"""
patch_index_facnotes.py — put the objection rule inside every town hall box.

WHAT THIS ADDS
--------------
A town hall pin currently says "here is a building, here is its website". It
does not say the two things a community actually needs:

  1. WHICH BODY DECIDES. Not a naming question. The tier that signs off differs
     by project size: in France a housing estate goes to the commune but a
     motorway or industrial plant is decided by the PREFET; in the US a
     subdivision goes to the county but a landfill permit to the state agency.
     Sending someone to the town hall for a decision made at prefecture level
     wastes the only time they have.
  2. THE OBJECTION WINDOW. The statutory period in which written objections
     must be accepted and answered. Miss it and the right to appeal usually
     goes with it.

HOW IT AVOIDS DUPLICATION
-------------------------
The rule is national: all ~35,000 French communes share one enquete publique
procedure. So the text is stored ONCE per country in FACNOTES and looked up at
render time by the facility's coordinates. Every town hall box shows it; the
sentence exists once. A law change is a one-line edit, not 145,547 edits.

Country is resolved from lat/lng against the world-atlas polygons the map
already loads (no extra download), with the ISO taken from the existing
NUM2A3 table. If the point falls outside every wired country, no note is shown
- never a guessed one.

Idempotent: re-running detects the marker and makes no change.

USAGE
  python3 patch_index_facnotes.py index.html
  python3 patch_index_facnotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* facnotes (patch_index_facnotes) */"

# Per-country: who decides, and the objection window. Kept factual and short;
# each names the instrument by its local name so it can be searched for.
FACNOTES = {
    "FRA": "The <b>commune</b> adopts the PLU and issues most permis de construire — "
           "but large or industrial projects are decided by the <b>préfet</b>, not the mairie. "
           "PLU revisions and major works carry an <b>enquête publique</b>: a commissaire enquêteur "
           "must answer written objections on the record.",
    "DEU": "The <b>Gemeinde</b> holds Bauleitplanung — the Flächennutzungsplan and Bebauungsplan "
           "decide what may be built. Draft plans go to <b>Öffentlichkeitsbeteiligung</b> with a "
           "statutory objection window; larger installations are permitted by the Land authority.",
    "ITA": "The <b>comune</b> adopts the piano urbanistico and issues building and landscape "
           "authorisations. Plan variants go to <b>deposito e osservazioni</b> — a fixed window for "
           "written objections. Regional VIA applies to larger works.",
    "ESP": "The <b>municipio</b> approves the plan general and grants licencias de obra. Approval "
           "requires an <b>información pública</b> period for <b>alegaciones</b>; the autonomous "
           "community handles environmental authorisation for major projects.",
    "GBR": "The <b>local planning authority</b> determines applications and adopts the local plan. "
           "Every application has a <b>statutory consultation period</b> with comments on the public "
           "register; nationally significant infrastructure goes to the Planning Inspectorate instead.",
    "NLD": "The <b>gemeente</b> decides omgevingsvergunningen under the Omgevingswet; "
           "<b>waterschappen</b> are separately elected authorities for water and flooding. "
           "Draft decisions carry a <b>six-week zienswijze window</b> — standing to appeal usually "
           "depends on having filed one.",
    "FIN": "The <b>kunta</b> holds the planning monopoly and approves the asemakaava. Plan proposals "
           "go on public display with a <b>muistutus</b> objection period; decisions are appealable "
           "to the administrative court.",
    "IND": "The <b>gram panchayat</b> or urban local body handles local approvals. Where the Forest "
           "Rights Act or PESA applies, the <b>gram sabha's recorded resolution</b> is the strongest "
           "instrument available; large projects need central environmental clearance.",
    "BRA": "The <b>município</b> adopts the plano diretor and licenses local-impact activity. The "
           "plano diretor must be revised with public participation, and the municipal environmental "
           "council (<b>CONDEMA</b>) is an open body; state agencies license larger works.",
    "MEX": "The <b>municipio</b> issues licencias de uso de suelo and the programa de desarrollo "
           "urbano. Cabildo sessions are public and land-use changes require a <b>consulta "
           "pública</b> — that record is what a later amparo relies on.",
    "PHL": "The <b>LGU</b> issues locational clearances and its Sanggunian adopts the land use plan. "
           "The Local Government Code requires prior consultation and <b>Sanggunian approval before "
           "a national project can proceed locally</b> — a real veto point.",
    "ZAF": "The <b>municipality</b> runs the land use scheme under SPLUMA. Applications must be "
           "advertised for comment and objectors have a <b>right to be heard by the Municipal "
           "Planning Tribunal</b>, with an internal appeal before review.",
    "AUS": "The <b>council</b> is consent authority for most development applications and writes the "
           "local environmental plan. DAs are <b>notified for public submission</b> and objectors can "
           "address the council or planning panel; state significant projects bypass council.",
    "NZL": "The <b>territorial authority</b> processes resource consents and the district plan. "
           "Notified consents let affected people <b>make a submission and be heard</b>, with appeal "
           "to the <b>Environment Court</b>.",
    "KEN": "The <b>county government</b> controls physical planning and development control. "
           "<b>Public participation is a constitutional requirement</b> in county planning, and its "
           "absence is a common and successful ground of challenge.",
    "USA": "The <b>county or city</b> decides zoning and subdivision; <b>state agencies</b> permit "
           "landfills, pipelines and large industrial facilities. Hearings must be noticed in advance "
           "and written comment accepted — check both the local agenda and the state permit docket.",
    "CAN": "The <b>municipality</b> decides zoning and development permits; provincial ministries "
           "handle environmental assessment for larger works. Rezonings require a <b>public hearing</b> "
           "at which anyone affected may speak.",
}

JS_BLOCK = """
/* facnotes (patch_index_facnotes) */
/* Objection rules are NATIONAL, so the text lives once per country here and is
   looked up per facility at render time. Never duplicated per marker. */
var FACNOTES=__FACNOTES__;
var _fnFeat=null;
function _fnSetCountries(fc){ _fnFeat=fc; }
function _fnRingHas(x,y,ring){ var inside=false;
  for(var i=0,j=ring.length-1;i<ring.length;j=i++){
    var xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
    if(((yi>y)!==(yj>y)) && (x < (xj-xi)*(y-yi)/(yj-yi)+xi)) inside=!inside; }
  return inside; }
function _fnPolyHas(x,y,poly){ if(!_fnRingHas(x,y,poly[0]))return false;
  for(var h=1;h<poly.length;h++) if(_fnRingHas(x,y,poly[h])) return false;
  return true; }
function _fnCountry(la,lo){ if(!_fnFeat)return '';
  for(var i=0;i<_fnFeat.length;i++){ var f=_fnFeat[i]; if(!f.geometry)continue;
    var g=f.geometry, hit=false;
    if(g.type==='Polygon') hit=_fnPolyHas(lo,la,g.coordinates);
    else if(g.type==='MultiPolygon'){ for(var m=0;m<g.coordinates.length && !hit;m++) hit=_fnPolyHas(lo,la,g.coordinates[m]); }
    if(hit) return (typeof NUM2A3!=='undefined' && NUM2A3[f.id])||''; }
  return ''; }
function _fnNote(la,lo){ try{ var iso=_fnCountry(la,lo); if(!iso)return '';
    var n=FACNOTES[iso]; if(!n)return '';
    return '<div class="fac-why"><b>Who decides, and by when</b><br>'+n+'</div>'; }
  catch(e){ return ''; } }
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"

    block = JS_BLOCK.replace("__FACNOTES__",
                             json.dumps(FACNOTES, ensure_ascii=False))

    # 1. insert the block just before the facility popup builder
    anchor = "function _facPop(p){"
    if anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(anchor, block + "\n" + anchor, 1)

    # 2. append the note inside the town hall / gov office branch
    old_tail = ("look for <i>planning / development / agendas / public notices</i>."
                "</div>'; }\n  return s; }")
    if old_tail not in text:
        raise SystemExit("could not find _facPop tail — aborting, no change")
    new_tail = old_tail.replace("return s; }",
                                "s+=_fnNote(p.la,p.lo); }\n  return s; }")
    # the branch closes before `return s;` — put the note inside the same branch
    new_tail = ("look for <i>planning / development / agendas / public notices</i>."
                "</div>'; s+=_fnNote(p.la,p.lo); }\n  return s; }")
    text = text.replace(old_tail, new_tail, 1)

    # 3. hand the loaded country polygons to the lookup (no extra download)
    feed = "const countries=topojson.feature(wd,wd.objects.countries);"
    if feed not in text:
        raise SystemExit("could not find topojson feature build — aborting")
    text = text.replace(feed, feed + " try{_fnSetCountries(countries.features);}catch(e){}", 1)

    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("var x=1;\n"
              "function _facPop(p){ const label='x';\n"
              "  let s='a';\n"
              "  if(p.k==='th'||p.k==='go'){ s+='<div class=\"fac-why\">... "
              "look for <i>planning / development / agendas / public notices</i>."
              "</div>'; }\n  return s; }\n"
              "const countries=topojson.feature(wd,wd.objects.countries);\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq(MARKER in out, True, "patch/marker")
    eq("_fnSetCountries(countries.features)" in out, True, "patch/feeds-polygons")
    eq("s+=_fnNote(p.la,p.lo); }" in out, True, "patch/note-inside-branch")
    eq(out.count("_fnNote(p.la,p.lo)"), 1, "patch/single-call")

    again, status2 = patch(out)
    eq(status2, "already patched", "patch/idempotent")
    eq(again, out, "patch/idempotent-nochange")

    # the note text must exist exactly once per country, not per marker
    eq(out.count('"FRA"'), 1, "data/one-entry-per-country")
    eq(len(FACNOTES) >= 15, True, "data/coverage")
    for iso, note in FACNOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
        if "<b>" not in note:
            fails.append(f"data/no-emphasis: {iso}")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (9 checks + {len(FACNOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(FACNOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
