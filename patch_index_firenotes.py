#!/usr/bin/env python3
"""
patch_index_firenotes.py — what a fire service can actually do about a development.

WHY THIS IS WORTH A BOX OF ITS OWN
----------------------------------
Fire services are the most under-used lever in this whole map, for one reason
almost nobody outside the industry knows: in a great many countries the fire
authority is a STATUTORY CONSULTEE on building or planning approval, and in
several its clearance is a PRECONDITION of the permit — Brazil's AVCB, the
Philippines' Fire Safety Evaluation Clearance, India's fire NOC for high-rises,
Italy's CPI. That makes fire safety a genuine chokepoint: if the developer
cannot satisfy it, the project cannot proceed, whatever the planners think.

And the fire authority's response to a consultation is normally a public
document. Asking for it is often the single most productive records request a
community can make, because it is written by people with no stake in the
project's approval.

The box therefore covers:
  BRING IT   — access for appliances, water supply and hydrants, hazardous
               storage near homes, wildfire and vegetation risk, blocked
               escape routes, site burning.
  DON'T      — a project you simply oppose; and never the emergency number for
               a document request.
  ASK        — whether the fire authority was consulted, and what it said.
  PER COUNTRY— the named instrument, because it differs sharply.

Requires patch_index_facnotes.py first (reuses _fnCountry). Idempotent.
No phone numbers — a wrong number in an emergency context is dangerous.

USAGE
  python3 patch_index_firenotes.py index.html
  python3 patch_index_firenotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* firenotes (patch_index_firenotes) */"

UNIVERSAL = (
    "<b>Bring it here:</b> a layout that fire engines cannot reach or turn in, "
    "no hydrant or inadequate water supply, fuel or chemical storage close to "
    "homes or schools, vegetation and wildfire risk left unmanaged, blocked or "
    "single escape routes, and burning of waste on a construction site.<br>"
    "<b>Not here:</b> a project you oppose on planning grounds — fire services "
    "do not weigh whether something should be built. And <b>never use the "
    "emergency number</b> for questions or documents; use the fire prevention "
    "or community safety office.<br>"
    "<b>The question worth asking:</b> was the fire authority consulted on this "
    "application, and what did it say? In many countries that response is a "
    "public document, written by people with no stake in approval — and where "
    "fire clearance is a precondition of the permit, an unresolved objection "
    "stops the project."
)

# Country -> the named fire instrument, and whether it gates the permit.
FIRENOTES = {
    "GBR": "In the UK the <b>Fire and Rescue Authority</b> is consulted on Building "
           "Regulations (Part B) applications, and the <b>Regulatory Reform (Fire Safety) "
           "Order</b> governs occupied premises; higher-risk buildings go through the "
           "<b>Building Safety Regulator</b> gateways.",
    "USA": "In the US the <b>fire marshal</b> or fire prevention bureau reviews plans against "
           "the fire code (IFC/NFPA) and can refuse occupancy. In wildfire states check the "
           "<b>Fire Hazard Severity Zone</b> and defensible-space rules — in California, "
           "CAL FIRE's maps and WUI codes.",
    "CAN": "In Canada the <b>fire commissioner or provincial fire marshal</b> enforces the fire "
           "code and reviews plans; municipalities apply the National Building Code fire "
           "provisions.",
    "FRA": "In France the <b>SDIS</b> advises and the <b>commission de sécurité</b> must give a "
           "favourable opinion for establishments open to the public (ERP). Hazardous sites are "
           "permitted separately as <b>ICPE</b> by the préfet.",
    "DEU": "In Germany the <b>Brandschutzdienststelle</b> reviews the <b>Brandschutznachweis</b> "
           "submitted with the building application; major-hazard sites fall under the "
           "<b>Störfall-Verordnung</b>.",
    "ESP": "In Spain the <b>bomberos</b> report on compliance with the Código Técnico "
           "<b>DB-SI</b> fire sections; Seveso establishments are authorised by the autonomous "
           "community.",
    "ITA": "In Italy the <b>Vigili del Fuoco</b> issue the <b>Certificato di Prevenzione "
           "Incendi</b> — for listed activities the project cannot lawfully operate without it, "
           "via the SCIA antincendio.",
    "NLD": "In the Netherlands the <b>veiligheidsregio</b> advises on the omgevingsvergunning "
           "and on external safety distances; major-hazard sites fall under <b>Brzo</b>.",
    "FIN": "In Finland the regional <b>pelastuslaitos</b> gives a statement on building permits "
           "and inspects; the rescue authority can require corrections before use.",
    "AUS": "In Australia <b>bushfire</b> is the decisive one: land mapped as bushfire-prone "
           "triggers Planning for Bushfire Protection, a <b>BAL assessment</b>, and referral to "
           "the rural fire service — in NSW the <b>RFS</b> is an integrated referral body whose "
           "requirements bind the consent.",
    "NZL": "In New Zealand <b>Fire and Emergency New Zealand</b> is consulted on fire design "
           "under Building Code clauses C1–C6 and on water supply for firefighting; it can be an "
           "affected party in a resource consent.",
    "ZAF": "In South Africa the municipal fire service comments on building plans against "
           "<b>SANS 10400-T</b> and can refuse approval; major-hazard installations are "
           "separately regulated.",
    "IND": "In India a <b>fire NOC</b> from the state fire service is required for high-rise and "
           "many commercial buildings — issued before occupancy and a real chokepoint; the "
           "National Building Code sets the standard.",
    "BRA": "In Brazil the <b>Corpo de Bombeiros</b> issues the <b>AVCB</b> (auto de vistoria) — "
           "without it the building cannot lawfully operate, and the project's fire plan must be "
           "approved before construction.",
    "MEX": "In Mexico <b>Protección Civil</b> issues the dictamen and the bomberos the visto "
           "bueno; both are normally required for the operating licence.",
    "PHL": "In the Philippines the <b>Bureau of Fire Protection</b> issues the Fire Safety "
           "Evaluation Clearance <b>before the building permit</b> and the Fire Safety Inspection "
           "Certificate before occupancy — a formal precondition.",
    "KEN": "In Kenya county fire services approve fire safety plans with the building approval, "
           "and workplaces require a periodic <b>fire safety audit</b> filed with the "
           "occupational safety directorate.",
}

JS_BLOCK = """
/* firenotes (patch_index_firenotes) */
/* Fire authorities are often a statutory consultee - and in several countries
   their clearance gates the permit. Stored once per country, looked up per pin. */
var FIREUNIV=__UNIV__;
var FIRENOTES=__FIRENOTES__;
function _firNote(la,lo){ try{
    var s='<div class="fac-why"><b>When to bring it to the fire service</b><br>'+FIREUNIV;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&FIRENOTES[iso]) s+='<br>'+FIRENOTES[iso];
    s+='</div>';
    return s; }
  catch(e){ return ''; } }
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    if "_fnCountry" not in text:
        raise SystemExit("run patch_index_facnotes.py first (needs _fnCountry)")

    block = (JS_BLOCK
             .replace("__UNIV__", json.dumps(UNIVERSAL, ensure_ascii=False))
             .replace("__FIRENOTES__", json.dumps(FIRENOTES, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    if anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(anchor, block + "\n" + anchor, 1)

    tail = "  return s; }\nfunction _facPopList("
    if tail not in text:
        raise SystemExit("could not find _facPop tail — aborting, no change")
    text = text.replace(tail, "  if(p.k==='fs'){ s+=_firNote(p.la,p.lo); }\n" + tail, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("function _fnCountry(a,b){return 'BRA';}\n"
              "function _facPop(p){ let s='a';\n"
              "  return s; }\nfunction _facPopList(l){}\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("if(p.k==='fs'){ s+=_firNote(p.la,p.lo); }" in out, True, "patch/fire-branch")
    eq(out.count("_firNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){return '';}\nfunction _facPopList(){}")
        fails.append("patch/missing-dependency not caught")
    except SystemExit:
        pass

    # content requirements
    eq("never use the emergency number" in UNIVERSAL, True, "content/no-999-abuse")
    eq("Not here" in UNIVERSAL, True, "content/negative-case")
    eq("was the fire authority consulted" in UNIVERSAL, True, "content/records-ask")
    eq("hydrant" in UNIVERSAL, True, "content/water-supply")
    eq("wildfire" in UNIVERSAL, True, "content/wildfire")

    for iso, n in FIRENOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
        if re.search(r"\b\d{3,}\b", n) and "10400" not in n and "NFPA" not in n:
            fails.append(f"data/suspect-number: {iso}")
    eq(len(FIRENOTES) >= 15, True, "data/coverage")
    # the permit-gating cases must actually say so
    for iso in ("BRA", "PHL", "IND", "ITA"):
        if not re.search(r"(precondition|before the building permit|cannot lawfully|chokepoint)",
                         FIRENOTES[iso]):
            fails.append(f"data/gate-not-stated: {iso}")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (11 checks + {len(FIRENOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(FIRENOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
