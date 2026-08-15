#!/usr/bin/env python3
"""
patch_index_corruption.py — three different situations people call "corruption".

They need three different answers, and conflating them wastes the one shot a
community gets:

  1. SUSPICION ("the council always sides with developers"). Police cannot act
     on a hunch, and saying it publicly can expose you to a defamation claim.
     The answer is records, not officers: get the file, the declarations of
     interests, the meeting minutes, the correspondence.

  2. EVIDENCE (an undisclosed interest, a payment, a job offer, a document
     showing a decision taken before the hearing). This is reportable — but
     usually NOT to the local station, because local police sit inside the same
     local structure. It goes to an independent body: an anti-corruption
     commission, a prosecutor, an ombudsman or a state auditor.

  3. LEGAL BUT LOOPHOLE-DANCING — the most common case by far. Splitting one
     project into small applications to dodge a threshold, approving on a
     technicality, running consultation over a holiday, a councillor voting on
     a developer they know socially. This is not a crime and police will do
     nothing. The remedy is procedural: challenge the decision, use the
     standards or conflict-of-interest route, and vote.

Requires patch_index_facnotes.py and patch_index_polnotes.py first.
Idempotent. No hotline numbers - bodies are named to be searched for.

USAGE
  python3 patch_index_corruption.py index.html
  python3 patch_index_corruption.py --selftest
"""

import json
import re
import sys

MARKER = "/* corruptnotes (patch_index_corruption) */"

TIERS = (
    "<b>1. You suspect it.</b> A council that always sides with developers is "
    "not by itself a crime, and police cannot act on a pattern. Do not name "
    "anyone publicly yet — defamation claims are a standard reply. Get the "
    "record first: the application file, declarations of interests, meeting "
    "minutes, and correspondence via freedom-of-information.<br>"
    "<b>2. You have evidence.</b> An undisclosed interest, a payment, a job or "
    "gift, or a document showing the decision was taken before the hearing. "
    "This is reportable — but usually <b>not to the local station</b>, which "
    "sits inside the same local structure. Take it to an independent body, and "
    "keep an original copy somewhere else.<br>"
    "<b>3. It is legal but engineered.</b> Splitting one project into several "
    "small applications to stay under a threshold, approving on a technicality, "
    "consulting over a holiday, a member voting on someone they know. Not a "
    "crime — police will not act. The remedy is procedural: challenge the "
    "decision itself, use the standards or conflict-of-interest route, and "
    "treat it as an election issue."
)

# Country -> the independent body evidence should go to (not the local station).
ANTICORR = {
    "GBR": "In the UK: the council's <b>monitoring officer</b> and standards committee for "
           "member conduct, the <b>Local Government &amp; Social Care Ombudsman</b> for "
           "maladministration, and police economic crime units or the <b>Serious Fraud "
           "Office</b> for serious cases.",
    "USA": "In the US: the <b>FBI public corruption programme</b> and the US Attorney's office, "
           "the <b>state attorney general</b>, plus any city or county <b>ethics commission</b> "
           "and inspector general.",
    "CAN": "In Canada: the provincial <b>ombudsman</b> and integrity commissioner, the "
           "auditor general, and the RCMP for criminal matters (in Quebec, <b>UPAC</b>).",
    "FRA": "In France: the <b>Parquet national financier</b> for serious cases, the <b>HATVP</b> "
           "for declarations of interests, and the <b>Agence française anticorruption</b>.",
    "DEU": "In Germany: the <b>Staatsanwaltschaft</b> corruption units and the <b>Rechnungshof</b> "
           "for misuse of public money.",
    "ESP": "In Spain: the <b>Fiscalía Anticorrupción</b>, plus regional anti-fraud offices such "
           "as the <b>Oficina Antifrau</b> in Catalonia.",
    "ITA": "In Italy: <b>ANAC</b>, the national anti-corruption authority, and the "
           "<b>procura</b> for criminal conduct.",
    "NLD": "In the Netherlands: the <b>Rijksrecherche</b> investigates officials, and the "
           "National Ombudsman handles maladministration.",
    "FIN": "In Finland: the <b>Parliamentary Ombudsman</b> and Chancellor of Justice oversee "
           "officials; the National Bureau of Investigation handles bribery.",
    "AUS": "In Australia: the state anti-corruption commission (<b>ICAC</b> in NSW, <b>IBAC</b> "
           "in Victoria, CCC in Queensland and WA) and the federal <b>NACC</b>.",
    "NZL": "In New Zealand: the <b>Serious Fraud Office</b>, the Office of the Auditor-General, "
           "and the Ombudsman.",
    "ZAF": "In South Africa: the <b>Public Protector</b>, the Special Investigating Unit, and "
           "the Hawks for organised corruption.",
    "KEN": "In Kenya: the <b>Ethics and Anti-Corruption Commission</b> and the Office of the "
           "Auditor-General.",
    "IND": "In India: the state <b>Lokayukta</b>, the Central Vigilance Commission, and the CBI; "
           "the Right to Information Act is usually the first step.",
    "BRA": "In Brazil: the <b>Ministério Público</b>, which can open an inquiry on a citizen's "
           "complaint, plus the <b>CGU</b> and the Tribunal de Contas.",
    "MEX": "In Mexico: the <b>Fiscalía Anticorrupción</b>, the Auditoría Superior de la "
           "Federación, and the state comptroller under the Sistema Nacional Anticorrupción.",
    "PHL": "In the Philippines: the <b>Office of the Ombudsman</b>, which prosecutes officials "
           "before the <b>Sandiganbayan</b>.",
}

JS_BLOCK = """
/* corruptnotes (patch_index_corruption) */
/* Three different things get called corruption and they need different routes.
   Stored once per country; looked up per pin. */
var CORRTIERS=__TIERS__;
var ANTICORR=__ANTICORR__;
function _cnNote(la,lo){ try{
    var s='<div class="fac-why"><b>If you think something is corrupt</b><br>'+CORRTIERS;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&ANTICORR[iso]) s+='<br>'+ANTICORR[iso];
    s+='</div>';
    return s; }
  catch(e){ return ''; } }
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    for dep, name in (("_fnCountry", "patch_index_facnotes.py"),
                      ("_pnNote", "patch_index_polnotes.py")):
        if dep not in text:
            raise SystemExit(f"run {name} first (needs {dep})")

    block = (JS_BLOCK
             .replace("__TIERS__", json.dumps(TIERS, ensure_ascii=False))
             .replace("__ANTICORR__", json.dumps(ANTICORR, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    text = text.replace(anchor, block + "\n" + anchor, 1)

    old = "if(p.k==='po'){ s+=_pnNote(p.la,p.lo); }"
    if old not in text:
        raise SystemExit("could not find police branch — aborting, no change")
    text = text.replace(old,
                        "if(p.k==='po'){ s+=_pnNote(p.la,p.lo); s+=_cnNote(p.la,p.lo); }",
                        1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("function _fnCountry(a,b){return 'GBR';}\n"
              "function _pnNote(a,b){return '';}\n"
              "function _facPop(p){ let s='a';\n"
              "  if(p.k==='po'){ s+=_pnNote(p.la,p.lo); }\n"
              "  return s; }\nfunction _facPopList(l){}\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("s+=_pnNote(p.la,p.lo); s+=_cnNote(p.la,p.lo); }" in out, True,
       "patch/appended-after-police-note")
    eq(out.count("_cnNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){return '';}")
        fails.append("patch/missing-deps not caught")
    except SystemExit:
        pass

    # the three tiers must be distinguishable and each must give a route
    eq("You suspect it" in TIERS, True, "tiers/suspicion")
    eq("You have evidence" in TIERS, True, "tiers/evidence")
    eq("legal but engineered" in TIERS, True, "tiers/loophole")
    eq("not to the local station" in TIERS, True, "tiers/escalation-warning")
    eq("defamation" in TIERS, True, "tiers/defamation-risk")
    eq("police will not act" in TIERS, True, "tiers/honest-about-limits")

    for iso, n in ANTICORR.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
        if re.search(r"\b\d{4,}\b", n):
            fails.append(f"data/contains-number: {iso}")
    eq(len(ANTICORR) >= 15, True, "data/coverage")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (12 checks + {len(ANTICORR)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(ANTICORR)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
