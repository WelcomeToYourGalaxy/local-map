#!/usr/bin/env python3
"""
patch_index_govnotes.py — what a government office above the council is for.

TWO FUNCTIONS, BOTH DECISIVE
----------------------------
1. IT DECIDES THE PERMITS THE COUNCIL CANNOT. Environmental impact assessment,
   discharge and emissions permits, water abstraction, waste licences, mining
   and quarrying, protected species and habitat consents, major roads and
   energy. A council can approve a development that still cannot lawfully
   operate without one of these — which is why an agency permit is often a
   later and better place to fight than the planning decision everyone watched.

2. IT HOLDS THE RECORDS THAT DECIDE ARGUMENTS. The land registry says who
   actually owns the site and what is charged against it. The company registry
   says who is behind the applicant. The cadastre says where the boundary
   really runs. Monitoring data says whether the last operator complied. These
   are usually obtainable by anyone, often for a small fee, and they settle
   questions that months of meetings do not.

WHAT IT CANNOT DO
-----------------
It will not overturn a council's planning decision because you ask, staff
cannot act as your advocate, and nothing arrives unless requested. Agencies
answer specific written questions with a file reference far better than they
answer general complaints.

Requires patch_index_facnotes.py first. Idempotent. Applies to government
offices and ministry/department headquarters.

USAGE
  python3 patch_index_govnotes.py index.html
  python3 patch_index_govnotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* govnotes (patch_index_govnotes) */"

UNIVERSAL = (
    "<b>This is where the permits above the council are decided:</b> "
    "environmental impact assessment, discharge and emissions, water "
    "abstraction, waste licences, mining and quarrying, protected species and "
    "habitat, major roads and energy. A council can approve a scheme that still "
    "<b>cannot lawfully operate</b> without one of these — so an agency permit "
    "is often a later and stronger place to object than the planning decision "
    "everyone was watching. Ask when the consultation on it opens.<br>"
    "<b>And this is where the records are.</b> The <b>land registry</b> shows who "
    "really owns the site and what is charged against it; the <b>company "
    "registry</b> shows who is behind the applicant; the <b>cadastre</b> shows "
    "where the boundary actually runs; <b>monitoring and inspection data</b> "
    "shows whether the operator complied last time. Most are obtainable by "
    "anyone, often for a small fee — and they settle arguments that months of "
    "meetings will not.<br>"
    "<b>What it will not do:</b> overturn the council's planning decision "
    "because you asked, or act as your advocate. Nothing arrives unless "
    "requested.<br>"
    "<b>How to ask so you get an answer:</b> put it in writing, name the site "
    "and the <b>file or application reference</b>, ask for the <b>case "
    "officer</b>, ask one specific question, and ask for the <b>consultation "
    "responses</b> from other agencies — those are written by technical staff "
    "with no stake in approval and are frequently the most useful documents in "
    "the file. Keep the reply."
)

# Country -> which office decides, and where the land record lives.
GOVNOTES = {
    "GBR": "In the UK: the <b>Environment Agency</b> (SEPA, NRW) for permits and abstraction, "
           "<b>Natural England</b> or equivalent for protected sites, the <b>Planning "
           "Inspectorate</b> for appeals and major infrastructure, and <b>HM Land Registry</b> "
           "for ownership and charges.",
    "USA": "In the US: the <b>state environmental agency</b> (DEQ/DEP/EPA-state) issues most "
           "permits, the <b>EPA regional office</b> handles federal programmes, the <b>Army "
           "Corps</b> handles wetlands, and the <b>county recorder or assessor</b> holds deeds "
           "and parcel records.",
    "CAN": "In Canada: the <b>provincial ministry of environment</b> issues approvals, the "
           "<b>Impact Assessment Agency</b> handles federal reviews, and <b>land titles</b> "
           "offices hold ownership.",
    "FRA": "In France: the <b>DREAL</b> and the <b>préfecture</b> handle ICPE authorisations and "
           "environmental assessment, the <b>OFB</b> protected species, and the <b>cadastre</b> "
           "with the service de publicité foncière holds parcels and ownership.",
    "DEU": "In Germany: the <b>Landesamt für Umwelt</b> or Regierungspräsidium issues "
           "immission-control permits, and the <b>Grundbuchamt</b> holds title while the "
           "Katasteramt holds boundaries.",
    "ESP": "In Spain: the <b>consejería de medio ambiente</b> of the autonomous community handles "
           "environmental authorisation and the confederación hidrográfica handles water; the "
           "<b>Catastro</b> and Registro de la Propiedad hold parcels and title.",
    "ITA": "In Italy: the <b>Regione</b> and <b>ARPA</b> handle environmental authorisation and "
           "monitoring, the Soprintendenza protects landscape and heritage, and the "
           "<b>Catasto</b> with the Conservatoria holds parcels and ownership.",
    "NLD": "In the Netherlands: the <b>omgevingsdienst</b> and province issue environmental "
           "permits, <b>Rijkswaterstaat</b> handles major water and roads, and the "
           "<b>Kadaster</b> holds ownership and boundaries.",
    "FIN": "In Finland: the <b>ELY Centre</b> and the Regional State Administrative Agency (AVI) "
           "issue environmental permits, and the <b>National Land Survey</b> holds title and "
           "cadastre.",
    "AUS": "In Australia: the <b>state EPA</b> licenses, state planning departments handle "
           "significant projects, federal EPBC referrals cover protected matters, and the "
           "<b>land titles office</b> holds ownership.",
    "NZL": "In New Zealand: the <b>regional council</b> issues resource consents for water, "
           "discharge and coastal work, the EPA handles national applications, and <b>LINZ</b> "
           "holds title.",
    "ZAF": "In South Africa: the provincial environment department and <b>DFFE</b> issue "
           "environmental authorisations, the Department of Water and Sanitation licenses water "
           "use, and the <b>Deeds Office</b> holds ownership.",
    "IND": "In India: the <b>State Pollution Control Board</b> issues consent to establish and "
           "operate, the <b>SEIAA/MoEFCC</b> grants environmental clearance, and the revenue "
           "department holds land records — often the decisive documents in a land dispute.",
    "BRA": "In Brazil: <b>IBAMA</b> or the state environmental agency issues licenciamento "
           "(prévia, instalação, operação — three separate chances to object), and the "
           "<b>cartório de registro de imóveis</b> holds title.",
    "MEX": "In Mexico: <b>SEMARNAT</b> decides the impacto ambiental, CONAGUA the water "
           "concession, and the <b>Registro Público de la Propiedad</b> — with the <b>RAN</b> for "
           "ejido land — holds ownership.",
    "PHL": "In the Philippines: the <b>DENR-EMB</b> issues the Environmental Compliance "
           "Certificate, the Mines and Geosciences Bureau handles mining, and the <b>Land "
           "Registration Authority</b> and assessor hold title and tax declarations.",
    "KEN": "In Kenya: <b>NEMA</b> approves the EIA licence and the Water Resources Authority the "
           "abstraction permit, while the <b>Ministry of Lands</b> registry holds title — a "
           "search there is cheap and often decisive.",
}

JS_BLOCK = """
/* govnotes (patch_index_govnotes) */
/* Agency offices do two things a council cannot: issue the permits above the
   planning decision, and hold the records that settle arguments. Stored once
   per country, looked up per pin. */
var GOVUNIV=__UNIV__;
var GOVNOTES=__GOVNOTES__;
function _gvNote(la,lo){ try{
    var s='<div class="fac-why"><b>What this office decides \\u2014 and what it holds</b><br>'+GOVUNIV;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&GOVNOTES[iso]) s+='<br>'+GOVNOTES[iso];
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
             .replace("__GOVNOTES__", json.dumps(GOVNOTES, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    if anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(anchor, block + "\n" + anchor, 1)

    tail = "  return s; }\nfunction _facPopList("
    if tail not in text:
        raise SystemExit("could not find _facPop tail — aborting, no change")
    text = text.replace(
        tail, "  if(p.k==='go'||p.k==='mi'){ s+=_gvNote(p.la,p.lo); }\n" + tail, 1)
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
    eq("if(p.k==='go'||p.k==='mi'){ s+=_gvNote(p.la,p.lo); }" in out, True,
       "patch/gov-and-ministry-branch")
    eq(out.count("_gvNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){return '';}\nfunction _facPopList(){}")
        fails.append("patch/missing-dependency not caught")
    except SystemExit:
        pass

    # both functions must be present, plus the limits and the asking method
    eq("cannot lawfully operate" in UNIVERSAL, True, "content/permit-leverage")
    eq("land registry" in UNIVERSAL, True, "content/records")
    eq("company registry" in UNIVERSAL, True, "content/who-is-behind-it")
    eq("What it will not do" in UNIVERSAL, True, "content/limits")
    eq("file or application reference" in UNIVERSAL, True, "content/how-to-ask")
    eq("consultation responses" in UNIVERSAL, True, "content/best-documents")

    for iso, n in GOVNOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
        # every country line must name where land ownership is recorded
        if not re.search(r"(registr|cadastre|catastro|catasto|"
                         r"Kadaster|Grundbuchamt|land titles|Deeds Office|LINZ|"
                         r"land records|recorder|cartório|Land Survey)", n, re.I):
            fails.append(f"data/no-land-record: {iso}")
    eq(len(GOVNOTES) >= 15, True, "data/coverage")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (12 checks + {len(GOVNOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(GOVNOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
