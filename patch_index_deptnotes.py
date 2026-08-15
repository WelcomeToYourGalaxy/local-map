#!/usr/bin/env python3
"""
patch_index_deptnotes.py — who inside the building does what, and what each cannot do.

THE PROBLEM
-----------
"Go to the town hall" is not an instruction. A town hall is six or seven
different powers under one roof, and people routinely spend their objection
window arguing with the department that has no power over the thing they care
about — pleading aesthetics to a highways engineer, or asking elected members
to overturn a decision they are legally barred from touching.

Each role is listed with BOTH halves: what it can do, and what it cannot. The
second half matters more, because it stops wasted effort and tells you when you
are being sent in a circle.

THE STRATEGIC POINT, STATED PLAINLY
-----------------------------------
Objections that are technical and quantified — drainage capacity, sewer
headroom, traffic counts, code non-compliance, noise and dust limits — are hard
to dismiss because refuting them requires the developer to produce evidence.
Objections that are aesthetic or about character are easy to dismiss. Same
project, same people, completely different outcome depending on which door and
which argument.

Requires patch_index_facnotes.py first. Idempotent.

USAGE
  python3 patch_index_deptnotes.py index.html
  python3 patch_index_deptnotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* deptnotes (patch_index_deptnotes) */"

ROLES = (
    "<b>Planning officers (staff).</b> Assess the application against the "
    "adopted plan and write the recommendation most decisions follow. "
    "<i>Can</i> negotiate conditions, require more information, recommend "
    "refusal. <i>Cannot</i> refuse because a project is unpopular — give them "
    "policy breaches, not petitions.<br>"
    "<b>Planning commission / committee.</b> Takes the decision, or advises the "
    "council. <i>Can</i> approve, refuse, impose conditions, defer for more "
    "information. <i>Cannot</i> refuse without a valid planning reason — an "
    "unreasoned refusal is usually overturned on appeal, sometimes with costs.<br>"
    "<b>Elected council.</b> Adopts the plan and the zoning that every later "
    "decision is judged against, sets the budget, and can often call an "
    "application in for decision. <i>Can</i> change policy for next time. "
    "<i>Cannot</i> normally overturn an individual decision on request — that "
    "part is quasi-judicial.<br>"
    "<b>Public works / engineering.</b> Roads, drainage, water and sewer "
    "capacity, traffic. <i>Can</i> demand infrastructure works, refuse access or "
    "connection. <b>Most under-used door in the building</b>: capacity "
    "objections are technical and cannot be waved away.<br>"
    "<b>Building control / code enforcement.</b> Permits, inspections, occupancy. "
    "<i>Can</i> issue <b>stop-work orders</b> and withhold occupancy — the "
    "fastest real-world brake on work already underway. <i>Cannot</i> revisit "
    "whether permission should have been granted.<br>"
    "<b>Environmental health.</b> Noise, dust, odour, contaminated land. "
    "<i>Can</i> serve abatement notices and set limits binding during "
    "construction. <i>Cannot</i> stop a lawful project — but conditions it "
    "imposes are enforceable.<br>"
    "<b>Variance / appeals board.</b> Grants exceptions to the rules. This is "
    "where projects that do not fit get made to fit — <b>exceptions are "
    "objectable and often the weakest link</b>. <i>Can</i> waive a standard on "
    "stated grounds such as hardship. <i>Cannot</i> normally grant one just "
    "because compliance is inconvenient or less profitable — ask what the "
    "stated ground is.<br>"
    "<b>Clerk / records office.</b> Agendas, minutes, notices, and the deadline "
    "to register to speak. Start here: they will tell you when the item is heard "
    "and how to get on the list.<br>"
    "<b>Aim well:</b> drainage capacity, traffic counts, code breaches and "
    "pollution limits are hard to dismiss because rebutting them costs the "
    "developer evidence. \u201cIt will spoil the character of the area\u201d is easy "
    "to dismiss."
)

# Country -> local names for the same roles, where they differ enough to matter.
DEPTNOTES = {
    "GBR": "In the UK: <b>planning officers</b> write the report, the <b>planning committee</b> "
           "of elected members decides contested cases, <b>environmental health</b> handles "
           "statutory nuisance, and the <b>highways authority</b> is a separate consultee whose "
           "objection carries real weight.",
    "USA": "In the US: <b>planning department</b> staff, a <b>planning commission</b> that "
           "recommends or decides, the <b>city council or board of supervisors</b> for "
           "rezonings, a <b>zoning board of appeals</b> for variances, plus <b>public works</b> "
           "and <b>code enforcement</b>.",
    "CAN": "In Canada: <b>planning department</b>, <b>committee of adjustment</b> for minor "
           "variances, and <b>council</b> for rezonings and official plan amendments; engineering "
           "reviews servicing capacity.",
    "FRA": "In France: the <b>service urbanisme</b> instructs the permit, the <b>maire</b> signs "
           "it, the <b>conseil municipal</b> adopts the PLU, and during an enquête publique the "
           "<b>commissaire enquêteur</b> is the person who must answer you.",
    "DEU": "In Germany: the <b>Bauamt</b> assesses, the <b>Bauausschuss</b> and "
           "<b>Gemeinderat</b> decide the Bebauungsplan, and the <b>Umweltamt</b> handles "
           "emissions and contaminated land.",
    "ESP": "In Spain: the <b>oficina de urbanismo</b> reports, the <b>pleno del ayuntamiento</b> "
           "approves plans, and the <b>concejalía de medio ambiente</b> handles environmental "
           "conditions.",
    "ITA": "In Italy: the <b>ufficio tecnico</b> or SUE handles the permit, the <b>consiglio "
           "comunale</b> adopts the plan, and the <b>commissione paesaggistica</b> rules on "
           "landscape impact — a genuine constraint in protected areas.",
    "NLD": "In the Netherlands: the <b>college van B&amp;W</b> decides permits, the "
           "<b>gemeenteraad</b> adopts the omgevingsplan, and the regional <b>omgevingsdienst</b> "
           "does environmental assessment and enforcement.",
    "FIN": "In Finland: the <b>kaavoitus</b> (planning) unit prepares, the "
           "<b>kunnanvaltuusto</b> approves plans, and the building supervision authority "
           "(rakennusvalvonta) issues permits.",
    "AUS": "In Australia: council <b>planning officers</b> assess, elected <b>councillors</b> or "
           "a <b>local planning panel</b> decide, and referral agencies — roads, water, rural "
           "fire — must be satisfied before consent.",
    "NZL": "In New Zealand: council <b>planners</b> report, independent <b>hearings "
           "commissioners</b> often decide notified consents, and council <b>compliance "
           "officers</b> enforce consent conditions.",
    "ZAF": "In South Africa: the municipal planning department assesses, the <b>Municipal "
           "Planning Tribunal</b> decides, and your <b>ward councillor</b> is the route into the "
           "political side.",
    "IND": "In India: the <b>town planning department</b> of the municipal corporation or "
           "development authority sanctions plans, the <b>ward committee</b> and corporators are "
           "the local political route, and the state pollution board is separate.",
    "BRA": "In Brazil: the <b>secretaria de urbanismo</b> licenses, the <b>câmara municipal</b> "
           "legislates the plano diretor, and the <b>conselho da cidade</b> or CONDEMA are open "
           "councils where objections are formally recorded.",
    "MEX": "In Mexico: the <b>dirección de desarrollo urbano</b> issues uso de suelo, the "
           "<b>cabildo</b> approves plan changes, and <b>protección civil</b> must sign off on "
           "risk.",
    "PHL": "In the Philippines: the <b>zoning administrator</b> and MPDO handle clearances, the "
           "<b>Sangguniang Bayan/Panlungsod</b> approves the land use plan, and the "
           "<b>barangay</b> records local objections first.",
    "KEN": "In Kenya: the county <b>physical planning</b> department assesses, the <b>county "
           "executive committee member for lands</b> decides, and the <b>county assembly</b> "
           "approves plans — public participation records are the leverage.",
}

JS_BLOCK = """
/* deptnotes (patch_index_deptnotes) */
/* A town hall is several powers under one roof. Each role gets what it CAN and
   CANNOT do, so people stop spending the objection window at the wrong desk.
   Stored once per country, looked up per pin. */
var DEPTROLES=__ROLES__;
var DEPTNOTES=__DEPTNOTES__;
function _dpNote(la,lo){ try{
    var s='<div class="fac-why"><b>Which desk, and what it can actually do</b><br>'+DEPTROLES;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&DEPTNOTES[iso]) s+='<br>'+DEPTNOTES[iso];
    s+='</div>';
    return s; }
  catch(e){ return ''; } }
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    if "_fnNote" not in text:
        raise SystemExit("run patch_index_facnotes.py first (needs _fnNote)")

    block = (JS_BLOCK
             .replace("__ROLES__", json.dumps(ROLES, ensure_ascii=False))
             .replace("__DEPTNOTES__", json.dumps(DEPTNOTES, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    text = text.replace(anchor, block + "\n" + anchor, 1)

    old = "s+=_fnNote(p.la,p.lo); }"
    if old not in text:
        raise SystemExit("could not find town hall branch — aborting, no change")
    text = text.replace(old, "s+=_fnNote(p.la,p.lo); s+=_dpNote(p.la,p.lo); }", 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("function _fnCountry(a,b){return 'FRA';}\n"
              "function _fnNote(a,b){return '';}\n"
              "function _facPop(p){ let s='a';\n"
              "  if(p.k==='th'||p.k==='go'){ s+='x'; s+=_fnNote(p.la,p.lo); }\n"
              "  return s; }\nfunction _facPopList(l){}\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("s+=_fnNote(p.la,p.lo); s+=_dpNote(p.la,p.lo); }" in out, True,
       "patch/appended-after-facnote")
    eq(out.count("_dpNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){return '';}")
        fails.append("patch/missing-dependency not caught")
    except SystemExit:
        pass

    # every role must state a limit, not just a power
    for role in ("Planning officers", "Planning commission", "Elected council",
                 "Public works", "Building control", "Environmental health",
                 "Variance", "Clerk"):
        if role not in ROLES:
            fails.append(f"roles/missing: {role}")
    eq(ROLES.count("<i>Cannot</i>"), 6, "roles/limits-stated")
    eq("stop-work orders" in ROLES, True, "roles/fastest-brake")
    eq("Most under-used door" in ROLES, True, "roles/public-works-flag")
    eq("easy to dismiss" in ROLES, True, "roles/aim-well")

    for iso, n in DEPTNOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
    eq(len(DEPTNOTES) >= 15, True, "data/coverage")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (13 checks + {len(DEPTNOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(DEPTNOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
