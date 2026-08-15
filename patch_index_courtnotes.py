#!/usr/bin/env python3
"""
patch_index_courtnotes.py — when a court can help, and the clock you are already on.

THE TWO THINGS PEOPLE GET WRONG
-------------------------------
1. WHAT COURTS DECIDE. In most countries a court reviewing a permit does not
   re-decide whether the project is a good idea. It decides whether the
   decision was taken LAWFULLY — proper notice, proper assessment, reasons
   given, no undisclosed interest, no ignored evidence. "Too big, too ugly,
   we don't want it" loses. "They never assessed the flood risk they were
   required to assess" wins. A few systems are different — New Zealand's
   Environment Court and India's NGT can look at the merits — and that
   difference is worth knowing before spending money.

2. THE DEADLINE. This is the one that ends most cases before they start. Time
   to challenge a planning or permit decision is measured in WEEKS in much of
   the world, and it usually runs from the decision, not from when you heard
   about it. By the time diggers arrive it is normally far too late.

Also covered: standing usually depends on having objected during the
consultation, so the objection you filed earlier is what buys the right to sue
later; the costs risk, which is the real barrier in common-law countries; and
where a person can genuinely act WITHOUT a lawyer — the Philippines' writ of
kalikasan, India's NGT, New Zealand's Environment Court, small-claims style
tribunals — versus where self-representation is technically allowed but
practically unwise.

Requires patch_index_facnotes.py first. Idempotent. Deadlines are given as
typical periods with an instruction to confirm at the registry, because limits
vary by decision type and are the single most dangerous thing to get wrong.

USAGE
  python3 patch_index_courtnotes.py index.html
  python3 patch_index_courtnotes.py --selftest
"""

import json
import re
import sys

MARKER = "/* courtnotes (patch_index_courtnotes) */"

UNIVERSAL = (
    "<b>What a court will decide:</b> usually not whether the project is a good "
    "idea, but whether the decision was taken <b>lawfully</b> — was notice "
    "given, was the required assessment done, were reasons given, was evidence "
    "ignored, did someone vote who should not have. \u201cToo big, too ugly\u201d "
    "loses; \u201cthey never assessed the flood risk they were required to "
    "assess\u201d wins.<br>"
    "<b>The clock is the real danger.</b> Time to challenge a permit is measured "
    "in <b>weeks</b> in much of the world, and it normally runs from the date of "
    "the decision — not from when you found out, and certainly not from when "
    "machinery arrives. Ask the court registry for the exact limit for your type "
    "of decision <b>before</b> anything else.<br>"
    "<b>Standing usually comes from having objected.</b> If you filed a written "
    "objection during the consultation, you are far more likely to be heard "
    "later. That is why the planning stage matters more than the courtroom.<br>"
    "<b>Without a lawyer:</b> court staff cannot give legal advice, but they can "
    "tell you the deadline, the form, the fee and whether a fee waiver exists. "
    "Ask for the <b>self-represented litigant</b> guidance. Before filing, ask "
    "one lawyer about <b>costs exposure</b> — in some systems losing means paying "
    "the other side, and that risk, not the filing fee, is what decides whether "
    "to proceed."
)

# Country -> forum, typical limit, and whether a lay person can realistically act.
COURTNOTES = {
    "GBR": "In the UK a planning decision is challenged by <b>judicial review</b> in the "
           "Planning Court, typically within <b>six weeks</b>. Environmental cases can qualify "
           "for the <b>Aarhus costs cap</b>, which limits what you pay if you lose — ask about "
           "it explicitly, it is the difference between arguable and unaffordable.",
    "USA": "In the US challenges run in <b>state court</b> against local decisions and federal "
           "court under NEPA/APA against federal ones; limits are often very short and set by "
           "state statute. Many states require you to have <b>exhausted administrative "
           "appeals</b> first. Fee waivers exist; costs are usually not shifted to losing "
           "plaintiffs.",
    "CAN": "In Canada judicial review goes to the superior court or Federal Court, commonly "
           "within <b>30 days</b> of the decision; several provinces have municipal or "
           "environmental appeal boards that hear objections first and are cheaper.",
    "FRA": "In France a permis de construire is contested before the <b>tribunal administratif</b>, "
           "usually within <b>two months</b>, and the recours must be notified to the beneficiary. "
           "Associations can act if their statutes and registration predate the decision.",
    "DEU": "In Germany the route is <b>Widerspruch</b> then <b>Klage</b> at the "
           "Verwaltungsgericht, generally within <b>one month</b>. Recognised environmental "
           "associations have their own standing (<b>Verbandsklage</b>) without needing personal "
           "harm.",
    "ESP": "In Spain the <b>recurso contencioso-administrativo</b> is generally brought within "
           "<b>two months</b>; Spain also has a broad <b>acción popular</b> in urbanismo letting "
           "any citizen challenge planning illegality.",
    "ITA": "In Italy the <b>TAR</b> (regional administrative court) hears challenges, normally "
           "within <b>60 days</b>; local committees and associations are routinely admitted.",
    "NLD": "In the Netherlands you file <b>bezwaar</b> or <b>beroep</b> within <b>six weeks</b>, "
           "and standing generally requires that you filed a zienswijze at the draft stage. "
           "Appeals on major decisions go to the Raad van State.",
    "FIN": "In Finland planning and permit decisions are appealed to the <b>administrative "
           "court</b>, typically within <b>30 days</b>; municipal residents have broad standing "
           "on plan decisions.",
    "AUS": "In Australia the <b>Land and Environment Court</b> (NSW) and equivalents in other "
           "states hear both merits appeals and judicial review — the merits route is the "
           "valuable one, but objector appeal rights are limited to designated development.",
    "NZL": "In New Zealand the <b>Environment Court</b> hears appeals on the merits, and "
           "submitters can appear <b>without a lawyer</b> — one of the most accessible "
           "environmental courts anywhere. You must have made a submission on the notified "
           "consent.",
    "ZAF": "In South Africa review runs under <b>PAJA</b>, generally within <b>180 days</b>, "
           "after exhausting internal appeals. Section 32 of NEMA gives wide standing, including "
           "acting in the public interest.",
    "IND": "In India the <b>National Green Tribunal</b> takes applications directly from affected "
           "people, usually within <b>30 days</b> of the order, and is designed to work "
           "<b>without a lawyer</b>; it decides on the merits, not just legality.",
    "BRA": "In Brazil any citizen may bring an <b>ação popular</b> against an unlawful act "
           "damaging public assets, and the <b>Ministério Público</b> can bring an ação civil "
           "pública on your complaint — the cheapest route is usually to give it the evidence "
           "rather than to sue.",
    "MEX": "In Mexico the <b>juicio de amparo</b> protects against acts of authority, with a "
           "short filing window — commonly <b>15 working days</b>. Courts have accepted "
           "collective environmental interest, but the deadline is unforgiving.",
    "PHL": "In the Philippines the <b>writ of kalikasan</b> can be filed by any person or group "
           "on behalf of others whose right to a balanced ecology is threatened, with <b>no "
           "docket fees</b>, plus the writ of continuing mandamus to force officials to act.",
    "KEN": "In Kenya the <b>Environment and Land Court</b> has broad standing — anyone may sue "
           "on environmental grounds without showing personal loss — and the National "
           "Environment Tribunal hears licence appeals, usually within <b>60 days</b>.",
}

JS_BLOCK = """
/* courtnotes (patch_index_courtnotes) */
/* What courts decide, the limitation clock, standing, and whether a lay person
   can act. Stored once per country, looked up per pin. */
var COURTUNIV=__UNIV__;
var COURTNOTES=__COURTNOTES__;
function _crNote(la,lo){ try{
    var s='<div class="fac-why"><b>When to take it to court \\u2014 and by when</b><br>'+COURTUNIV;
    var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
    if(iso&&COURTNOTES[iso]) s+='<br>'+COURTNOTES[iso];
    s+='<br><i>Time limits differ by decision type and change \\u2014 confirm yours with the court registry or a lawyer before relying on any period above.</i></div>';
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
             .replace("__COURTNOTES__", json.dumps(COURTNOTES, ensure_ascii=False)))

    anchor = "function _facPop(p){"
    if anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(anchor, block + "\n" + anchor, 1)

    tail = "  return s; }\nfunction _facPopList("
    if tail not in text:
        raise SystemExit("could not find _facPop tail — aborting, no change")
    text = text.replace(tail, "  if(p.k==='ch'){ s+=_crNote(p.la,p.lo); }\n" + tail, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ("function _fnCountry(a,b){return 'PHL';}\n"
              "function _facPop(p){ let s='a';\n"
              "  return s; }\nfunction _facPopList(l){}\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("if(p.k==='ch'){ s+=_crNote(p.la,p.lo); }" in out, True, "patch/court-branch")
    eq(out.count("_crNote(p.la,p.lo)"), 1, "patch/single-call")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("function _facPop(p){return '';}\nfunction _facPopList(){}")
        fails.append("patch/missing-dependency not caught")
    except SystemExit:
        pass

    # the four things that must never be missing
    eq("lawfully" in UNIVERSAL, True, "content/legality-not-merits")
    eq("weeks" in UNIVERSAL, True, "content/deadline-warning")
    eq("Standing usually comes from having objected" in UNIVERSAL, True,
       "content/standing")
    eq("costs exposure" in UNIVERSAL, True, "content/costs-risk")
    eq("self-represented litigant" in UNIVERSAL, True, "content/without-lawyer")

    for iso, n in COURTNOTES.items():
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")
    eq(len(COURTNOTES) >= 15, True, "data/coverage")
    # lay-access systems must actually say so
    for iso, word in (("PHL", "any person"), ("IND", "without a lawyer"),
                      ("NZL", "without a lawyer"), ("BRA", "any citizen")):
        if word not in COURTNOTES[iso]:
            fails.append(f"data/lay-access-not-stated: {iso}")
    # costs protection must be flagged where it exists
    if "Aarhus costs cap" not in COURTNOTES["GBR"]:
        fails.append("data/costs-cap-missing: GBR")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (12 checks + {len(COURTNOTES)} country entries)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status} ({len(COURTNOTES)} countries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
