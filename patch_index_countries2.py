#!/usr/bin/env python3
"""
patch_index_countries2.py — extend every facility note table to ten more countries.

The eight note tables added so far cover 17 countries. Outside them a pin shows
the universal text and nothing local, which is honest but thin. This adds:

  IRL POL SWE PRT TUR JPN IDN NGA ARG CHL

chosen for population, volume of contested development, and because several
have a mechanism worth knowing that no other country has — Japan's fire consent
requirement and resident audit request, Chile's environmental courts and the
Contraloría's toma de razón, Sweden's land and environment courts.

Every country is added to ALL eight tables, so no pin type is left half-wired.
The selftest enforces exactly that: if a country appears in one table it must
appear in all of them.

Requires the eight note patches to have run first. Idempotent.

USAGE
  python3 patch_index_countries2.py index.html
  python3 patch_index_countries2.py --selftest
"""

import json
import re
import sys

MARKER = "/* countries2 (patch_index_countries2) */"

NEW = {
    # ---- town hall: which body decides, and the objection window -----------
    "FACNOTES": {
        "IRL": "The <b>local authority</b> decides planning applications and adopts the "
               "development plan. Anyone may make a <b>written submission within five weeks</b> "
               "of the application, and — unusually — <b>any third party who did so can appeal</b> "
               "the decision to An Coimisiún Pleanála.",
        "POL": "The <b>gmina</b> adopts the local plan (miejscowy plan) and issues warunki "
               "zabudowy where none exists; the starosta issues the building permit. Plans go on "
               "public display with a stated period for <b>uwagi</b> (comments).",
        "SWE": "The <b>kommun</b> holds the planning monopoly — the byggnadsnämnd grants bygglov "
               "and the council adopts detaljplan. A plan is consulted at samråd and granskning; "
               "decisions are appealed to the <b>länsstyrelsen</b> within three weeks.",
        "PRT": "The <b>câmara municipal</b> licenses works and adopts the PDM; plans go to "
               "<b>discussão pública</b> with a fixed period, and larger projects need a separate "
               "environmental decision.",
        "TUR": "The <b>belediye</b> adopts the imar planı and issues yapı ruhsatı. A plan on "
               "public display can be objected to in writing during the <b>one-month askı</b> "
               "period — missing it usually forecloses later challenge.",
        "JPN": "The <b>municipality</b> handles building confirmation and city planning; larger "
               "projects go to the <b>prefecture</b>. City plan proposals are published for "
               "written opinions, and residents can request an explanatory meeting.",
        "IDN": "The <b>kabupaten or kota</b> issues the PBG building approval and the spatial "
               "plan (RTRW); an environmental approval is separate and obtained through the "
               "national <b>OSS</b> system.",
        "NGA": "The <b>state physical planning authority</b> and the local government approve "
               "development; state urban planning laws require notice and objection before "
               "approval of a scheme.",
        "ARG": "The <b>municipio</b> grants habilitación and zoning; the province runs "
               "environmental assessment, and the national environment law makes a <b>audiencia "
               "pública</b> mandatory for significant projects.",
        "CHL": "The <b>municipalidad</b>'s Dirección de Obras issues the permiso de edificación, "
               "but environmental approval runs through the <b>SEIA</b> with a formal "
               "<b>participación ciudadana</b> window — that is the real objection route.",
    },
    # ---- departments -------------------------------------------------------
    "DEPTNOTES": {
        "IRL": "In Ireland: the <b>planning department</b> assesses, elected councillors adopt "
               "the development plan, and the <b>executive</b> decides individual applications — "
               "councillors cannot decide your case, only the policy behind it.",
        "POL": "In Poland: the <b>wydział architektury</b> handles permits, the <b>rada gminy</b> "
               "adopts the plan, and the <b>SKO</b> (self-government appeal board) hears appeals "
               "before the courts.",
        "SWE": "In Sweden: the <b>byggnadsnämnd</b> decides bygglov, the <b>kommunfullmäktige</b> "
               "adopts plans, and the miljö- och hälsoskyddsnämnd handles noise, dust and odour.",
        "PRT": "In Portugal: the <b>divisão de urbanismo</b> assesses, the <b>câmara</b> decides "
               "and the <b>assembleia municipal</b> approves plans; CCDR handles regional matters.",
        "TUR": "In Turkey: the <b>imar müdürlüğü</b> handles permits, the <b>belediye meclisi</b> "
               "adopts plans, and the <b>zabıta</b> handles enforcement of local rules.",
        "JPN": "In Japan: the <b>建築主事</b> or a designated private agency issues building "
               "confirmation, the city planning division handles zoning, and the assembly "
               "receives residents' petitions (陳情).",
        "IDN": "In Indonesia: <b>Dinas PUPR</b> handles building approval, <b>Dinas Lingkungan "
               "Hidup</b> the environmental side, and the <b>DPRD</b> approves the spatial plan.",
        "NGA": "In Nigeria: the state <b>physical planning permit authority</b> approves "
               "development, the local government handles minor works, and the state environment "
               "ministry runs assessment.",
        "ARG": "In Argentina: <b>obras particulares</b> issues permits, the <b>concejo "
               "deliberante</b> passes zoning ordinances, and the provincial environment agency "
               "runs assessment.",
        "CHL": "In Chile: the <b>Dirección de Obras Municipales</b> issues permits, the "
               "<b>concejo municipal</b> approves the plan regulador, and the <b>SEA</b> runs "
               "environmental evaluation with the <b>SMA</b> enforcing conditions afterwards.",
    },
    # ---- police ------------------------------------------------------------
    "POLNOTES": {
        "IRL": "In Ireland the <b>EPA</b> licenses and enforces against industrial and waste "
               "sites, local authorities handle unauthorised development and litter, and the "
               "Gardaí act on waste crime with them.",
        "POL": "In Poland the <b>WIOŚ</b> (environmental protection inspectorate) inspects and "
               "sanctions; the police and prosecutor handle criminal dumping.",
        "SWE": "In Sweden the municipal <b>miljökontor</b> supervises and the county board "
               "enforces; police investigate miljöbrott through a specialist prosecutor.",
        "PRT": "In Portugal the <b>SEPNA</b> (GNR nature protection service) is a police unit for "
               "environmental crime, alongside APA and ICNF.",
        "TUR": "In Turkey the <b>Çevre ve Şehircilik İl Müdürlüğü</b> inspects and fines, and "
               "complaints can be filed through the national <b>CİMER</b> system, which requires "
               "a reply.",
        "JPN": "In Japan the <b>prefectural environment department</b> handles pollution "
               "complaints and the <b>Pollution Adjustment Commission</b> mediates disputes; "
               "police act on illegal dumping under the Waste Management Act.",
        "IDN": "In Indonesia the <b>KLHK</b> has its own civil-service investigators (PPNS) and "
               "the police have an environmental crime unit; report through the ministry's "
               "complaint channel to create a record.",
        "NGA": "In Nigeria <b>NESREA</b> enforces federal environmental standards and state "
               "environmental agencies handle local breaches; police handle threats.",
        "ARG": "In Argentina provincial environment agencies enforce and the <b>fiscalía</b> "
               "prosecutes; the Ley de Residuos Peligrosos makes some dumping a federal crime.",
        "CHL": "In Chile the <b>Superintendencia del Medio Ambiente</b> is the enforcement body "
               "and can fine or revoke; Carabineros act on immediate offences.",
    },
    # ---- corruption --------------------------------------------------------
    "ANTICORR": {
        "IRL": "In Ireland: the <b>Standards in Public Office Commission</b> for declarations and "
               "conduct, the Ombudsman for maladministration, and the Garda National Economic "
               "Crime Bureau for fraud.",
        "POL": "In Poland: the <b>prokuratura</b> for criminal conduct and the <b>NIK</b> "
               "(supreme audit office) for misuse of public funds; regional audit chambers review "
               "municipal spending.",
        "SWE": "In Sweden: the <b>National Anti-Corruption Unit</b> prosecutes bribery and the "
               "Parliamentary Ombudsman supervises officials; the principle of public access "
               "makes most documents obtainable on request.",
        "PRT": "In Portugal: the <b>Ministério Público</b> and the DCIAP for serious corruption, "
               "plus the <b>Tribunal de Contas</b> for public spending.",
        "TUR": "In Turkey: the <b>Sayıştay</b> audits public bodies and the prosecutor handles "
               "criminal complaints; the Ombudsman institution accepts individual applications.",
        "JPN": "In Japan: a <b>resident audit request</b> (住民監査請求) to the local audit "
               "commissioners, which can be followed by a <b>resident lawsuit</b> — a strong "
               "citizen remedy against unlawful municipal spending.",
        "IDN": "In Indonesia: the <b>KPK</b> takes public reports on corruption, and the BPK "
               "audits public spending.",
        "NGA": "In Nigeria: the <b>EFCC</b> and <b>ICPC</b> both take citizen petitions, and the "
               "Auditor-General reports on public accounts.",
        "ARG": "In Argentina: the <b>Oficina Anticorrupción</b>, the Auditoría General de la "
               "Nación, and provincial fiscalías de investigaciones administrativas.",
        "CHL": "In Chile: the <b>Contraloría General de la República</b> — its <b>toma de "
               "razón</b> reviews the legality of administrative acts, and citizens can lodge a "
               "presentación asking it to rule.",
    },
    # ---- fire --------------------------------------------------------------
    "FIRENOTES": {
        "IRL": "In Ireland a <b>Fire Safety Certificate</b> from the fire authority is required "
               "before most works begin — a formal precondition, not advice.",
        "POL": "In Poland the <b>Państwowa Straż Pożarna</b> must be notified before a building "
               "is taken into use and can object, blocking occupancy.",
        "SWE": "In Sweden the <b>räddningstjänst</b> advises on plans and inspects premises; the "
               "owner must document systematic fire safety work.",
        "PRT": "In Portugal the <b>ANEPC</b> approves fire safety design for most buildings "
               "before licensing.",
        "TUR": "In Turkey fire approval under the Binaların Yangından Korunması regulation is "
               "checked by the <b>itfaiye</b> before the occupancy permit (yapı kullanma izni).",
        "JPN": "In Japan <b>fire department consent</b> (消防同意) is required before building "
               "confirmation is issued — the fire service can stop the approval outright.",
        "IDN": "In Indonesia fire protection requirements are checked for the PBG, and the "
               "<b>dinas pemadam kebakaran</b> inspects before the certificate of function (SLF).",
        "NGA": "In Nigeria the state fire service certifies fire safety for approval and "
               "occupation of larger buildings.",
        "ARG": "In Argentina the <b>bomberos</b> and provincial fire authority certify fire "
               "conditions for the habilitación — without it the premises cannot open.",
        "CHL": "In Chile the <b>Dirección de Obras</b> checks fire requirements under the OGUC "
               "for the recepción final; bomberos report on hazards but do not license.",
    },
    # ---- courts ------------------------------------------------------------
    "COURTNOTES": {
        "IRL": "In Ireland planning decisions are appealed to <b>An Coimisiún Pleanála</b> by any "
               "third party who made a submission, normally within <b>four weeks</b>; judicial "
               "review of planning has a short eight-week window and needs leave.",
        "POL": "In Poland an administrative decision is appealed to the <b>SKO</b> within 14 days, "
               "then to the <b>wojewódzki sąd administracyjny</b> within 30 days.",
        "SWE": "In Sweden appeals go to the <b>länsstyrelsen</b> and then the <b>mark- och "
               "miljödomstol</b> — specialist land and environment courts — typically within three "
               "weeks of the decision.",
        "PRT": "In Portugal challenges go to the <b>tribunal administrativo</b>, generally within "
               "three months, and <b>ação popular</b> allows any citizen to act in the public "
               "interest.",
        "TUR": "In Turkey administrative acts are challenged in the <b>idare mahkemesi</b>, "
               "usually within <b>60 days</b>; a stay of execution (yürütmeyi durdurma) can be "
               "requested at the same time.",
        "JPN": "In Japan an administrative complaint (審査請求) runs about three months and a "
               "revocation suit about six; the <b>resident lawsuit</b> is often more effective "
               "against a municipality than a planning challenge.",
        "IDN": "In Indonesia a permit is challenged in the <b>PTUN</b> administrative court, "
               "normally within <b>90 days</b> of knowing the decision; environmental NGOs have "
               "standing to sue.",
        "NGA": "In Nigeria the <b>Federal High Court</b> hears environmental matters and "
               "fundamental rights suits; standing has been widened in public-interest cases.",
        "ARG": "In Argentina the <b>amparo ambiental</b> is fast and cheap, and the environment "
               "law gives standing to affected people, NGOs and the ombudsman.",
        "CHL": "In Chile the <b>Tribunales Ambientales</b> hear environmental claims and review "
               "SEA decisions, after the Comité de Ministros stage — a dedicated environmental "
               "court system.",
    },
    # ---- government office -------------------------------------------------
    "GOVNOTES": {
        "IRL": "In Ireland: the <b>EPA</b> for industrial and waste licences, the NPWS for "
               "protected sites, and <b>Tailte Éireann</b> for the land registry and valuation.",
        "POL": "In Poland: the <b>RDOŚ</b> issues the environmental decision, the WIOŚ inspects, "
               "and <b>księgi wieczyste</b> (land and mortgage registers) are searchable online.",
        "SWE": "In Sweden: the <b>länsstyrelsen</b> permits and supervises, Naturvårdsverket sets "
               "policy, and <b>Lantmäteriet</b> holds property and boundaries.",
        "PRT": "In Portugal: the <b>APA</b> handles environmental licensing and assessment, CCDR "
               "the regional side, and the <b>conservatória do registo predial</b> holds title.",
        "TUR": "In Turkey: the provincial directorate of the environment ministry handles ÇED and "
               "permits, and the <b>Tapu ve Kadastro</b> directorate holds title and boundaries.",
        "JPN": "In Japan: the <b>prefectural government</b> handles most environmental permits and "
               "assessment, and the <b>Legal Affairs Bureau</b> (法務局) holds the property "
               "register.",
        "IDN": "In Indonesia: environmental approval runs through <b>OSS</b> and the KLHK, while "
               "the <b>BPN/ATR</b> land agency holds certificates — overlapping claims are common, "
               "so check.",
        "NGA": "In Nigeria: <b>NESREA</b> and the federal environment ministry handle assessment, "
               "and the state <b>land registry</b> holds the Certificate of Occupancy — governor's "
               "consent is required for transfers.",
        "ARG": "In Argentina: the provincial environment agency issues the declaración de impacto "
               "ambiental, and the <b>Registro de la Propiedad Inmueble</b> holds title.",
        "CHL": "In Chile: the <b>SEA</b> runs evaluation, the SMA enforces, and the "
               "<b>Conservador de Bienes Raíces</b> holds property records.",
    },
    # ---- ministry ----------------------------------------------------------
    "MINNOTES": {
        "IRL": "In Ireland the <b>Department of Housing, Local Government and Heritage</b> sets "
               "planning policy and national planning guidelines that bind local plans; strategic "
               "infrastructure goes straight to An Coimisiún Pleanála.",
        "POL": "In Poland the <b>Ministry of Climate and Environment</b> and the <b>GDOŚ</b> set "
               "environmental procedure; draft legislation is consulted publicly.",
        "SWE": "In Sweden the government decides permissibility for certain major installations "
               "under the Environmental Code, and the ministry consults on statutory instruments.",
        "PRT": "In Portugal the environment ministry and APA decide national-level AIA; draft "
               "instruments go to public consultation on the Participa portal.",
        "TUR": "In Turkey the <b>Ministry of Environment, Urbanisation and Climate Change</b> "
               "decides ÇED for large projects and can approve plans directly, overriding "
               "municipal ones.",
        "JPN": "In Japan the <b>Ministry of the Environment</b> and MLIT set assessment rules; "
               "public comment (パブリックコメント) on draft rules is a formal process with "
               "published responses.",
        "IDN": "In Indonesia the <b>KLHK</b> decides AMDAL for national projects and issues "
               "forestry releases — the decisive consent where forest land is involved.",
        "NGA": "In Nigeria the <b>Federal Ministry of Environment</b> approves EIA reports and "
               "holds public display and hearing sessions before a certificate is issued.",
        "ARG": "In Argentina the <b>Ministerio de Ambiente</b> sets national minimum standards "
               "that provinces cannot fall below — a useful floor when a province is permissive.",
        "CHL": "In Chile the <b>Comité de Ministros</b> hears administrative appeals against SEIA "
               "decisions before the environmental courts — a mandatory stage worth using.",
    },
}


def merge_table(text, name, additions):
    """Merge new entries into an existing `var NAME={...};` JSON literal."""
    m = re.search(r"var " + name + r"=(\{.*?\});", text, re.S)
    if not m:
        raise SystemExit(f"could not find {name} — run the earlier note patches first")
    try:
        table = json.loads(m.group(1))
    except ValueError as exc:
        raise SystemExit(f"{name} is not parseable JSON: {exc}")
    added = 0
    for iso, note in additions.items():
        if iso not in table:
            table[iso] = note
            added += 1
    new_lit = "var " + name + "=" + json.dumps(table, ensure_ascii=False) + ";"
    return text[:m.start()] + new_lit + text[m.end():], added, len(table)


def patch(text):
    if MARKER in text:
        return text, "already patched", {}
    counts = {}
    for name, additions in NEW.items():
        text, added, total = merge_table(text, name, additions)
        counts[name] = (added, total)
    text = text.replace("function _facPop(p){", MARKER + "\nfunction _facPop(p){", 1)
    return text, "patched", counts


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    # every table must gain exactly the same country set — no half-wired pins
    sets = {name: set(d) for name, d in NEW.items()}
    first = sets["FACNOTES"]
    for name, s in sets.items():
        if s != first:
            fails.append(f"coverage/mismatch in {name}: {sorted(s ^ first)}")
    eq(len(first), 10, "coverage/ten-countries")
    eq(len(NEW), 8, "coverage/eight-tables")
    for iso in first:
        if not re.fullmatch(r"[A-Z]{3}", iso):
            fails.append(f"data/bad-iso: {iso}")

    sample = ('var FACNOTES={"FRA":"x"};\n' +
              "".join(f'var {n}={{"FRA":"x"}};\n' for n in NEW if n != "FACNOTES") +
              "function _facPop(p){ return ''; }\n")
    out, status, counts = patch(sample)
    eq(status, "patched", "patch/applies")
    for name in NEW:
        eq(counts[name][0], 10, f"patch/added-all-{name}")
        eq(counts[name][1], 11, f"patch/total-{name}")
    eq(json.loads(re.search(r"var FACNOTES=(\{.*?\});", out, re.S).group(1))["JPN"][:3],
       "The", "patch/json-still-valid")
    eq("FRA" in out, True, "patch/keeps-existing")

    again, st2, _ = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("var NOTHING={};")
        fails.append("patch/missing-table not caught")
    except SystemExit:
        pass

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK ({len(NEW)*2 + 8} checks, "
          f"{len(first)} countries x {len(NEW)} tables)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    text = open(path, encoding="utf-8").read()
    out, status, counts = patch(text)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status}")
    for name, (added, total) in counts.items():
        print(f"  {name:12s} +{added}  now {total} countries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
