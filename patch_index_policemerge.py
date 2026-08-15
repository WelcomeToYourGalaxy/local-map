#!/usr/bin/env python3
"""
patch_index_policemerge.py — one police section, and the news toggle where it belongs.

THREE FIXES
-----------
1. The corruption tier said "take it to an independent body" and then, for
   countries not in the table, named none. That is advice you cannot act on.
   There is now a fallback that names the KINDS of body to look for — an
   anti-corruption commission, the public prosecutor, an ombudsman, the state
   audit office, an ethics or standards commission — so a reader in an unwired
   country still knows what to search for.

2. The police box carried two separate headed blocks that read as two leaflets
   stapled together. They are now one section that moves through the real
   sequence a person follows: what police can act on, what they cannot, then
   what to do when the problem is not a crime but the process — suspicion,
   evidence, or a lawful decision that has been engineered. The country line at
   the end names both the environmental enforcement body and the
   anti-corruption body, because that is where "which one?" gets answered.

3. The news map toggle sat with the facility layer switches, nowhere near the
   Global Wire panel it belongs to. It moves into the wire panel head.

No text is duplicated: the merged section reuses the existing POLNOTES and
ANTICORR tables rather than restating them.

Requires patch_index_polnotes.py, patch_index_corruption.py and
patch_index_wirelayer.py. Idempotent.

USAGE
  python3 patch_index_policemerge.py index.html
  python3 patch_index_policemerge.py --selftest
"""

import re
import sys

MARKER = "/* policemerge (patch_index_policemerge) */"

JS_BLOCK = """
/* policemerge (patch_index_policemerge) */
/* One section instead of two, following the sequence a person actually goes
   through, and naming a body to approach even where the country is unwired. */
var CORR_FALLBACK="Where none is named above, look for the kinds of body that exist "
  +"almost everywhere: an <b>anti-corruption commission</b>, the <b>public prosecutor</b>, "
  +"an <b>ombudsman</b>, the <b>state audit office</b>, or an <b>ethics or standards "
  +"commission</b> for elected members. Any of them will tell you if it is the wrong door.";
function _plNote(la,lo){ try{
  var iso=(typeof _fnCountry==='function')?_fnCountry(la,lo):'';
  var s='<div class="fac-why"><b>What the police can and cannot do here</b><br>'+POLUNIV;
  s+='<br><br>Most of what people want stopped is not a crime, so the rest of this is '
   +'about where those complaints actually go.<br>'
   +'<b>If you only suspect something.</b> A council that always sides with developers is '
   +'not by itself an offence, and no officer can act on a pattern. Do not name anyone '
   +'publicly yet \\u2014 a defamation claim is the standard reply. Get the record first: the '
   +'application file, declarations of interests, minutes, and correspondence via '
   +'freedom-of-information.<br>'
   +'<b>If you have evidence</b> \\u2014 an undisclosed interest, a payment, a job or gift, a '
   +'document showing the decision was taken before the hearing \\u2014 that is reportable, but '
   +'usually <b>not at this station</b>, which sits inside the same local structure. '
   +'Keep an original copy somewhere else before you hand anything over.<br>'
   +'<b>If it is legal but engineered</b> \\u2014 one project split into several small '
   +'applications to stay under a threshold, approval on a technicality, consultation run '
   +'over a holiday, a member voting on someone they know \\u2014 no crime has been committed '
   +'and the police will not act. That fight is procedural: challenge the decision, use the '
   +'standards or conflict-of-interest route, and treat it as an election issue.';
  var lines=[];
  if(iso&&typeof POLNOTES!=='undefined'&&POLNOTES[iso]) lines.push(POLNOTES[iso]);
  if(iso&&typeof ANTICORR!=='undefined'&&ANTICORR[iso]) lines.push(ANTICORR[iso]);
  if(lines.length) s+='<br><br><b>Where to take each of those here:</b><br>'+lines.join('<br>');
  else s+='<br><br>'+CORR_FALLBACK;
  if(!iso||!(typeof ANTICORR!=='undefined'&&ANTICORR[iso])) {
    if(lines.length) s+='<br>'+CORR_FALLBACK; }
  s+='<br><br>'+POLCAUTION+'</div>';
  return s; }
  catch(e){ return ''; } }
"""

TOGGLE_HTML = (
    '<label class="fac-toggle" style="margin:6px 0 2px;">'
    '<input type="checkbox" id="wireToggle"> Pin these stories on the map</label>'
    '<div class="facf-hint" style="margin-bottom:6px;">Only stories matched to a '
    'specific project are pinned \\u2014 sector and market coverage stays in the feed. '
    'Each pin names the project it was matched to.</div>'
)


def patch(text):
    if MARKER in text:
        return text, "already patched"
    for dep in ("POLUNIV", "ANTICORR", "wireToggle"):
        if dep not in text:
            raise SystemExit(f"could not find {dep} — run the earlier patches first")

    # 1 + 2: merged police section replaces the two separate calls
    text = text.replace("function _facPop(p){", JS_BLOCK + "\nfunction _facPop(p){", 1)
    old_calls = "if(p.k==='po'){ s+=_pnNote(p.la,p.lo); s+=_cnNote(p.la,p.lo); }"
    if old_calls not in text:
        raise SystemExit("could not find the police branch — aborting, no change")
    text = text.replace(old_calls, "if(p.k==='po'){ s+=_plNote(p.la,p.lo); }", 1)

    # 3: move the news toggle from the facility legend into the wire panel
    old_toggle = re.search(
        r'<div class="leg-title" style="margin-top:9px;">News</div>.*?'
        r'</div>(?=<div class="leg-title" style="margin-top:9px;">Facility dots</div>)',
        text, re.S)
    if not old_toggle:
        raise SystemExit("could not find the news toggle block — aborting, no change")
    text = text[:old_toggle.start()] + text[old_toggle.end():]

    wire_anchor = '<div id="wireItems">'
    if wire_anchor not in text:
        raise SystemExit("could not find the wire feed body — aborting, no change")
    text = text.replace(wire_anchor, TOGGLE_HTML + wire_anchor, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = (
        'var POLUNIV="x"; var POLCAUTION="y"; var POLNOTES={"ESP":"a"};'
        'var ANTICORR={"ESP":"b"};'
        '<div class="leg-title" style="margin-top:9px;">News</div>'
        '<label><input type="checkbox" id="wireToggle"> old</label>'
        '<div class="facf-hint">old hint</div>'
        '<div class="leg-title" style="margin-top:9px;">Facility dots</div>'
        '<div id="wireItems">feed</div>'
        "function _facPop(p){ let s='a';\n"
        "  if(p.k==='po'){ s+=_pnNote(p.la,p.lo); s+=_cnNote(p.la,p.lo); }\n"
        "  return s; }")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("if(p.k==='po'){ s+=_plNote(p.la,p.lo); }" in out, True, "patch/single-call")
    eq("_pnNote(p.la,p.lo)" in out, False, "patch/old-police-call-gone")
    eq("_cnNote(p.la,p.lo)" in out, False, "patch/old-corruption-call-gone")
    eq(out.count('id="wireToggle"'), 1, "patch/toggle-not-duplicated")
    eq(out.index('id="wireToggle"') > out.index('id="wireItems"') - 900, True,
       "patch/toggle-near-feed")
    eq('style="margin-top:9px;">News</div>' in out, False,
       "patch/old-legend-block-removed")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("nothing")
        fails.append("patch/missing-deps not caught")
    except SystemExit:
        pass

    # the merged prose must read as one argument, not two leaflets
    eq("Most of what people want stopped is not a crime" in JS_BLOCK, True,
       "prose/bridge-sentence")
    eq("If you only suspect something" in JS_BLOCK, True, "prose/tier-1")
    eq("If you have evidence" in JS_BLOCK, True, "prose/tier-2")
    eq("If it is legal but engineered" in JS_BLOCK, True, "prose/tier-3")
    eq("<b>1." in JS_BLOCK, False, "prose/no-numbered-transplant")
    eq("Where to take each of those here" in JS_BLOCK, True, "prose/routes-together")
    # and the fallback must name real kinds of body
    for w in ("anti-corruption commission", "public prosecutor", "ombudsman",
              "state audit office", "ethics or standards"):
        if w not in JS_BLOCK:
            fails.append(f"fallback/missing: {w}")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (15 checks + fallback body list)")
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
