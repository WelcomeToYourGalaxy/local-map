#!/usr/bin/env python3
"""
patch_index_polnotes.py — say what police can and cannot act on, per country.

WHY
---
Communities routinely call the police about a development and get nowhere,
because most of what they are angry about is not a criminal matter: a granted
permit, a rezoning, a lawful clearance. Meanwhile the things police CAN act on
— illegal dumping, discharge without a permit, clearing outside consent hours,
destruction of a protected site, and above all threats or violence against the
people objecting — often go unreported.

So each police box gets three things:
  1. BRING IT: what is genuinely criminal or an enforceable offence.
  2. DON'T: what is a planning or licensing decision, with the body that
     actually handles it named instead.
  3. WHERE IT DIFFERS: the country's environmental enforcement body, because
     in some places that IS a police unit (SEPRONA in Spain, Carabinieri
     Forestali in Italy) and in others it is a separate regulator entirely.

Every police station worldwide gets the universal part; the country-specific
line is added where wired. No hotline numbers are included — a wrong number is
worse than none, so bodies are named to be searched for.

SAFETY NOTE THAT IS DELIBERATELY UNIVERSAL
------------------------------------------
Land and environmental defenders are criminalised in many jurisdictions, and
the person reporting can become the person investigated. The note therefore
tells people to get legal advice before reporting where they may themselves be
accused — stated evenly, for every country, without asserting that any
particular force is corrupt.

Requires patch_index_facnotes.py to have run first (reuses _fnCountry).
Idempotent.

USAGE
  python3 patch_index_polnotes.py index.html
  python3 patch_index_polnotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* polnotes (patch_index_polnotes) */"

UNIVERSAL = (
    "<b>Bring it here:</b> dumping or burning of waste, discharge to a river or "
    "drain, work outside permitted hours, clearing or demolition without consent, "
    "damage to a protected site or tree, and — most importantly — <b>threats, "
    "intimidation, assault or damage aimed at people who are objecting</b>. "
    "Report those immediately and keep a copy of the report.<br>"
    "<b>Not here:</b> a permit you disagree with, a rezoning, or a project that is "
    "simply unwanted. Those are planning and licensing decisions — police cannot "
    "reverse them, and the objection route is the planning authority."
)

CAUTION = (
    "<b>Before you report:</b> in many places objectors themselves face "
    "trespass, obstruction or defamation complaints. If you have been part of a "
    "protest or occupation, take legal advice first — the same file can be used "
    "against you."
)

# Country -> who actually enforces environmental offences.
POLNOTES = {
    "ESP": "In Spain the specialist unit is <b>SEPRONA</b> (Guardia Civil) — an actual "
           "police service for environmental crime; the autonomous community handles "
           "administrative sanctions.",
    "ITA": "In Italy the <b>Carabinieri Forestali</b> and the <b>NOE</b> handle "
           "environmental crime as police units; ARPA regional agencies handle "
           "monitoring and administrative breaches.",
    "FRA": "In France the <b>Office français de la biodiversité</b> and DREAL inspectors "
           "hold enforcement powers alongside the gendarmerie; the <b>procureur</b> decides "
           "whether an environmental offence is prosecuted.",
    "DEU": "In Germany the <b>Umweltamt</b> or Landesamt at Land level enforces; police "
           "act on Umweltstraftaten under the Strafgesetzbuch when an offence is criminal.",
    "GBR": "In the UK the <b>Environment Agency</b> (SEPA in Scotland, NRW in Wales) is the "
           "body for pollution and waste crime, with a 24-hour incident line; councils handle "
           "statutory nuisance such as noise and dust.",
    "NLD": "In the Netherlands the regional <b>omgevingsdienst</b> inspects and enforces; "
           "the police environmental team and the ILT handle criminal cases.",
    "FIN": "In Finland the <b>ELY Centre</b> and municipal environmental authority enforce; "
           "police investigate ympäristörikos offences.",
    "USA": "In the US report pollution to the <b>state environmental agency</b> and to the "
           "<b>EPA regional office</b> — EPA takes tips online. Local police rarely handle "
           "environmental offences; sheriffs handle trespass and threats.",
    "CAN": "In Canada the <b>provincial ministry of environment</b> enforces, with "
           "<b>Environment and Climate Change Canada</b> for federal offences; police handle "
           "threats and property crime.",
    "AUS": "In Australia the <b>state EPA</b> is the pollution and waste regulator with its "
           "own investigators; councils handle local nuisance and unauthorised works.",
    "NZL": "In New Zealand the <b>regional council</b> enforces the Resource Management Act "
           "and can issue abatement notices and prosecute; police handle threats.",
    "ZAF": "In South Africa <b>Environmental Management Inspectors</b> — the Green Scorpions "
           "— investigate environmental offences alongside SAPS.",
    "IND": "In India the <b>State Pollution Control Board</b> is the enforcement body and the "
           "<b>National Green Tribunal</b> hears cases directly; police act on obstruction and "
           "violence.",
    "BRA": "In Brazil <b>IBAMA</b> and the state environmental agency enforce, with the "
           "<b>Polícia Ambiental</b> as a dedicated force and the <b>Ministério Público</b> able "
           "to open a civil inquiry on a citizen's complaint.",
    "MEX": "In Mexico <b>PROFEPA</b> is the environmental enforcement authority; a citizen "
           "<b>denuncia popular</b> obliges it to open a file.",
    "PHL": "In the Philippines the <b>DENR</b> and its Environmental Management Bureau enforce; "
           "the PNP has an environmental desk, and barangay officials record local complaints.",
    "KEN": "In Kenya <b>NEMA</b> is the enforcement authority and the <b>Environment and Land "
           "Court</b> hears cases; county enforcement handles local breaches.",
}

JS_BLOCK = """
/* polnotes (patch_index_polnotes) */
/* What police can and cannot act on. Universal part shown everywhere; the
   country line names the actual environmental enforcement body, because in
   some countries that IS a police unit and in others it is not. Stored once
   per country, looked up per pin - never duplicated per marker. */
var POLUNIV=__UNIV__;
var POLCAUTION=__CAUTION__;
var POLNOTES=__POLNOTES__;
function _pnNote(la,lo){ try{
    var s='<div class="fac-why"><b>When to bring it to the police</b><br>'+POLUNIV;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&POLNOTES[iso]) s+='<br>'+POLNOTES[iso];
    s+='<br>'+POLCAUTION+'</div>';
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
             .replace("__CAUTION__", json.dumps(CAUTION, ensure_ascii=False))
             .replace("__POLNOTES__", json.dumps(POLNOTES, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    if anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(anchor, block + "\n" + anchor, 1)

    tail = "  return s; }\nfunction _facPopList("
    if tail not in text:
        raise SystemExit("could not find _facPop tail — aborting, no change")
    text = text.replace(tail,
                        "  if(p.k==='po'){ s+=_pnNote(p.la,p.lo); }\n"
                        + tail, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("function _fnCountry(a,b){return 'ESP';}\n"
              "function _facPop(p){ let s='a';\n"
              "  return s; }\nfunction _facPopList(l){ return ''; }\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq(MARKER in out, True, "patch/marker")
    eq("if(p.k==='po'){ s+=_pnNote(p.la,p.lo); }" in out, True, "patch/police-branch")
    eq(out.count("_pnNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){ return ''; }\nfunction _facPopList(){}")
        fails.append("patch/missing-dependency not caught")
    except SystemExit:
        pass

    # content rules
    eq("threats, intimidation, assault" in UNIVERSAL, True, "content/defender-threats")
    eq("Not here" in UNIVERSAL, True, "content/negative-case")
    eq("legal advice first" in CAUTION, True, "content/caution")
    for iso, n in POLNOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
        if re.search(r"\b\d{3,}\b", n):
            fails.append(f"data/contains-number: {iso}")  # no hotline numbers
    eq(len(POLNOTES) >= 15, True, "data/coverage")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (11 checks + {len(POLNOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(POLNOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
