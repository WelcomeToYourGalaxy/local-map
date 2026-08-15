#!/usr/bin/env python3
"""patch_index_scopefix2.py — drop other places' local programmes from a county popup.

The first pass labelled them ("Local programmes elsewhere in California"). But a
Davis parcel tax has no business in a Rosamond popup at all: it is 350 miles
away, it cannot be applied for there, and its presence pushes the sources that
DO serve Kern County down the panel.

Where the entries still belong: the STATE popup. Opening California should show
its county and municipal programmes, because they are inside the unit you are
looking at. So the rule is positional, not categorical:

  clicked unit IS the state  -> show them, headed "County and municipal
                                programmes in <state>"
  clicked unit is a county   -> drop them entirely

This same popup builder serves every country and every admin level, so the fix
applies worldwide, not just to US counties.

Idempotent. Requires patch_index_scopefix.py.
"""
import sys

MARKER = "/* scopefix2 */"

OLD = """  if(elsewhere.length){ body+='<div class="scope-head" title="These belong to other counties and towns in the same state. They are shown because they are the closest working models \\u2014 not because they operate here.">Local programmes elsewhere in '+_esc(region||nm)+'</div>';
    body+=lensGroupsHTML(elsewhere,'country'); }"""

NEW = """  /* scopefix2 */
  /* County- and municipal-tier entries belong INSIDE a state. Show them when the
     open unit is that state; drop them when it is one county, where another
     county's programme is noise that buries the sources serving this one. */
  var _unitIsRegion = (typeof ownRegion!=='undefined' && ownRegion && region
                       && gbNorm(ownRegion)===gbNorm(region));
  if(elsewhere.length && _unitIsRegion){
    body+='<div class="scope-head" title="Programmes run by counties and municipalities within this state. Each serves its own area \\u2014 open that area for the ones that apply there.">County and municipal programmes in '+_esc(region||nm)+'</div>';
    body+=lensGroupsHTML(elsewhere,'country'); }
  else if(elsewhere.length){ elsewhere=[]; }"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    if OLD not in text:
        raise SystemExit("could not find the elsewhere block — run patch_index_scopefix.py first")
    text = text.replace(OLD, NEW, 1)
    # `elsewhere` is reassigned, so it cannot be a const
    text = text.replace("const elsewhere=[], regionWide=[];",
                        "var elsewhere=[]; const regionWide=[];", 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = "const elsewhere=[], regionWide=[];\n" + OLD + "\n"
    out, st = patch(sample)
    eq(st, "patched", "patch/applies")
    eq("_unitIsRegion" in out, True, "patch/positional-rule")
    eq("County and municipal programmes in" in out, True, "patch/state-heading")
    eq("Local programmes elsewhere in" in out, False, "patch/old-heading-gone")
    eq("var elsewhere=[]" in out, True, "patch/reassignable")
    eq("const elsewhere" in out, False, "patch/no-const-reassign")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch("nothing")
        fails.append("patch/missing-anchor not caught")
    except SystemExit:
        pass

    # the positional rule itself
    def show(own, region):
        return bool(own and region and own == region)
    eq(show("California", "California"), True, "rule/state-shows")
    eq(show("Kern", "California"), False, "rule/county-drops")
    eq(show(None, "California"), False, "rule/unmatched-drops")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (11 checks)")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
    t = open(path, encoding="utf-8").read()
    out, status = patch(t)
    if status == "patched":
        open(path, "w", encoding="utf-8").write(out)
    print(f"{path}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
