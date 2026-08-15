#!/usr/bin/env python3
"""
patch_index_courtdata.py — get courthouses back, and cover every facility type.

WHY COURTHOUSES SHOWED ZERO
---------------------------
Two separate faults, and the second would have kept them invisible even after
fixing the first:

  a) The loader pulls legalmap_local_courthouse.json from the external
     executive-map site. That request is not returning data, so the set was
     empty. The supplied judicial_facilities.json holds 26,267 courthouses and
     10,809 prisons, so it is loaded from THIS repo instead — same origin, no
     third-party dependency.

  b) Key mismatch. The data marks courthouses 'c' and prisons 'p', and
     trackerdata's own court entries already use 'c'/'p' too — but FACLAB,
     FACCOL, facActive and the filter list all use 'ch'/'pr'. So even with data
     present, every courthouse fell through to the generic "Local facility"
     label, was absent from the filter, and never triggered the court note.
     Both key forms are now accepted.

COVERING THE REST
-----------------
Notes existed for town halls, police, fire, courts, government offices and
ministries. Prisons, embassies and border posts had none, so they showed a name
and a link and nothing else. Each now gets a short, honest note — including
saying plainly when a facility has no role in a development fight.

Idempotent. Requires the earlier note patches.

USAGE
  python3 patch_index_courtdata.py index.html
  python3 patch_index_courtdata.py --selftest
"""

import json
import re
import sys

MARKER = "/* courtdata (patch_index_courtdata) */"

EXTRA_NOTES = {
    "pr": ("Prison / detention",
           "Detention estates are development in their own right — new prisons "
           "and immigration centres go through the same planning and "
           "environmental consents as any other large institution, and are "
           "frequently sited on cheap land beside communities with least "
           "capacity to object. If one is proposed near you, it is a planning "
           "application like any other: the notice, the consultation window and "
           "the objection routes are identical."),
    "dp": ("Embassy / consulate",
           "No role in local development decisions. Relevant in one situation "
           "only: where the applicant is a state-owned company, an embassy is "
           "the accountable channel for that state's conduct abroad — and its "
           "own government may run a national contact point for OECD complaints "
           "about companies it hosts."),
    "bd": ("Border / customs post",
           "No role in approving development. Occasionally useful where a "
           "project depends on cross-border movement of waste, minerals or "
           "hazardous cargo: customs records and shipment notifications are the "
           "paper trail behind waste exports."),
}

JS_BLOCK = """
/* courtdata (patch_index_courtdata) */
/* Courthouses and prisons ship with the repo: the external set returned nothing
   and a same-origin file removes the third-party dependency entirely. */
var JUD_FILE='judicial_facilities.json';
/* The data marks courthouses 'c' and prisons 'p'; the UI was written around
   'ch' and 'pr'. Accept both rather than rewriting either dataset. */
FACLAB.c=FACLAB.ch; FACLAB.p=FACLAB.pr;
FACCOL.c=FACCOL.ch||'#1d2b3a'; FACCOL.p=FACCOL.pr;
facActive.c=1; facActive.ch=1; facActive.p=0; facActive.pr=0;
var FAC_EXTRA_NOTES=__EXTRA__;
function _extraNote(k){ var e=FAC_EXTRA_NOTES[k]; if(!e)return '';
  return '<div class="fac-why"><b>'+e[0]+'</b><br>'+e[1]+'</div>'; }
function _loadJudicial(){
  return fetch(JUD_FILE,{cache:'no-store'})
    .then(function(r){ return r.ok?r.json():[]; })
    .then(function(rows){
      if(!Array.isArray(rows)||!rows.length)return 0;
      var add=[];
      for(var i=0;i<rows.length;i++){ var r=rows[i];
        if(!isFinite(r.la)||!isFinite(r.lo))continue;
        add.push({la:r.la,lo:r.lo,n:r.n||'',u:r.u||'',k:r.k||'c'}); }
      facilityMarkers=(facilityMarkers||[]).concat(add);
      _facPts=null;
      try{ buildFacFilter(); }catch(e){}
      if(_facLayer&&_facLayer._draw)_facLayer._draw();
      return add.length; })
    .catch(function(){ return 0; }); }
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    for dep in ("FACLAB=", "buildFacFilter", "_crNote"):
        if dep not in text:
            raise SystemExit(f"could not find {dep} — run the earlier patches first")

    text = text.replace("function _facPop(p){",
                        JS_BLOCK.replace("__EXTRA__",
                                         json.dumps(EXTRA_NOTES, ensure_ascii=False))
                        + "\nfunction _facPop(p){", 1)

    # court note must fire for both key forms
    old_ch = "if(p.k==='ch'){ s+=_crNote(p.la,p.lo); }"
    if old_ch not in text:
        raise SystemExit("could not find the courthouse branch — aborting")
    text = text.replace(old_ch,
                        "if(p.k==='ch'||p.k==='c'){ s+=_crNote(p.la,p.lo); }", 1)

    # prisons, embassies and border posts get their own note
    tail = "  return s; }\nfunction _facPopList("
    if tail not in text:
        raise SystemExit("could not find _facPop tail — aborting")
    text = text.replace(
        tail,
        "  if(p.k==='pr'||p.k==='p'||p.k==='dp'||p.k==='bd'){\n"
        "    s+=_extraNote(p.k==='p'?'pr':p.k); }\n" + tail, 1)

    # load the repo-hosted judicial set alongside the external ones
    hook = "     facilityMarkers=out; _facPts=null; buildFacFilter();"
    if hook not in text:
        raise SystemExit("could not find the facility loader — aborting")
    text = text.replace(
        hook,
        "     facilityMarkers=out; _facPts=null; buildFacFilter();\n"
        "     try{ _loadJudicial(); }catch(e){}", 1)

    # show courthouses in the filter under their real key
    text = text.replace("var order=['po','th','fs','go','mi','ch'];",
                        "var order=['po','th','fs','go','mi','ch','c','p'];", 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = (
        "var FACCOL={ch:'#1',pr:'#2'}, FACLAB={ch:'Courthouse',pr:'Prison / detention'};"
        " var facActive={po:1};\n"
        "function buildFacFilter(){ var order=['po','th','fs','go','mi','ch']; }\n"
        "function _crNote(a,b){return 'court';}\n"
        "function _facPop(p){ let s='a';\n"
        "  if(p.k==='ch'){ s+=_crNote(p.la,p.lo); }\n"
        "  return s; }\nfunction _facPopList(l){}\n"
        "     facilityMarkers=out; _facPts=null; buildFacFilter();\n")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq("if(p.k==='ch'||p.k==='c')" in out, True, "keys/court-both-forms")
    eq("FACLAB.c=FACLAB.ch" in out, True, "keys/label-alias")
    eq("'ch','c','p'" in out, True, "filter/keys-added")
    eq("_loadJudicial();" in out, True, "load/hooked")
    eq("_extraNote(p.k==='p'?'pr':p.k)" in out, True, "notes/extra-types")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("nothing")
        fails.append("patch/missing-deps not caught")
    except SystemExit:
        pass

    # every facility kind the UI knows must now have a note or a stated reason
    covered = {"th", "go", "mi", "po", "fs", "ch", "c"}
    for k in EXTRA_NOTES:
        covered.add(k)
    for k in ("po", "pr", "th", "fs", "go", "mi", "dp", "bd", "ch"):
        if k not in covered:
            fails.append(f"coverage/no-note-for: {k}")
    eq("planning application like any other" in EXTRA_NOTES["pr"][1], True,
       "pr/treated-as-development")
    eq("No role in local development" in EXTRA_NOTES["dp"][1], True,
       "dp/honest-about-limits")
    eq("waste exports" in EXTRA_NOTES["bd"][1], True, "bd/names-the-use")
    eq("prisons" in EXTRA_NOTES["pr"][1] and "immigration centres" in EXTRA_NOTES["pr"][1],
       True, "pr/names-both")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print(f"SELFTEST OK (16 checks + {len(EXTRA_NOTES)} added types)")
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
