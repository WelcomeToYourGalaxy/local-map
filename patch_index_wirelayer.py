#!/usr/bin/env python3
"""
patch_index_wirelayer.py — put the geolocated news on the map.

wire_geo.json is generated daily (wire_geo.yml) and, until now, nothing read it.
This adds a toggleable layer: each item is a small marker at the coordinates of
the project the story is about, with a popup giving the headline, the source,
the date, the matched project and a link out.

DESIGN CHOICES WORTH STATING
----------------------------
- OFF BY DEFAULT. The map already carries facilities and projects; a third
  always-on layer would clutter it. The toggle sits with the other layer
  controls.
- MATCH CONFIDENCE IS SHOWN, not hidden. Each popup says which project the
  story was matched to. The matcher is good but not perfect, and a reader who
  can see the match can spot a wrong one; a reader who cannot, cannot.
- FAILS SILENTLY. If wire_geo.json is missing or malformed the toggle simply
  reports that no items are loaded. A news layer must never break the map.
- NO NEW DEPENDENCY. Plain Leaflet circle markers and the page's existing
  _esc/_href helpers.

Idempotent.

USAGE
  python3 patch_index_wirelayer.py index.html
  python3 patch_index_wirelayer.py --selftest
"""

import re
import sys

MARKER = "/* wirelayer (patch_index_wirelayer) */"

CONTROL_HTML = (
    '<div class="leg-title" style="margin-top:9px;">News</div>'
    '<label class="fac-toggle" style="margin:2px 0 0;">'
    '<input type="checkbox" id="wireToggle"> Show news pinned to projects</label>'
    '<div class="facf-hint">Recent reporting matched to a specific project and '
    'placed at its location. Only local, place-specific stories are pinned \\u2014 '
    'sector and market coverage is left in the feed. Each popup names the project '
    'it was matched to, so a wrong match is visible.</div>'
)

JS_BLOCK = """
/* wirelayer (patch_index_wirelayer) */
/* Renders wire_geo.json: news items matched to a project and placed at its
   coordinates. Off by default; degrades quietly if the file is absent. */
var _wireLayer=null, _wireLoaded=false, _wireItems=[];
function _wireDate(d){ try{ var t=(typeof d==='number')?d:Date.parse(d);
    if(!isFinite(t))return ''; var dt=new Date(t);
    return dt.toISOString().slice(0,10); }catch(e){ return ''; } }
function _wirePop(it){
  var s='<div class="ip-title">'+_esc(it.title||'Untitled')+'</div>';
  var meta=[]; if(it.name)meta.push(_esc(it.name)); var d=_wireDate(it.date); if(d)meta.push(d);
  if(meta.length) s+='<div style="margin:6px 0;font-size:12px;color:#9dbca6">'+meta.join(' \\u00b7 ')+'</div>';
  if(it.snippet) s+='<div style="font-size:12px;margin:4px 0">'+_esc(String(it.snippet).slice(0,260))+'\\u2026</div>';
  if(it.link) s+='<div><a href="'+_esc(_href(it.link))+'" target="_blank" rel="noopener">Read the story</a></div>';
  if(it.project){ s+='<div class="fac-why"><b>Matched to:</b> '+_esc(it.project)+
    (it.admin1?(' \\u2014 '+_esc(it.admin1)):'')+
    '<br><span style="font-size:11px;color:#84a08c">Matched automatically by name. If this looks wrong, it is \\u2014 trust the story, not the pin.</span></div>'; }
  return s; }
function _wireBuild(){ if(_wireLoaded)return Promise.resolve();
  _wireLoaded=true;
  return fetch('wire_geo.json',{cache:'no-store'})
    .then(function(r){ return r.ok?r.json():[]; })
    .then(function(rows){
      _wireItems=Array.isArray(rows)?rows:[];
      _wireLayer=L.layerGroup();
      for(var i=0;i<_wireItems.length;i++){ var it=_wireItems[i];
        var la=parseFloat(it.lat), lo=parseFloat(it.lng);
        if(!isFinite(la)||!isFinite(lo))continue;
        var mk=L.circleMarker([la,lo],{radius:5,weight:1.5,color:'#e8c46a',
          fillColor:'#c9922c',fillOpacity:0.85,pane:'markerPane'});
        mk.bindPopup(_wirePop(it),{maxWidth:340});
        _wireLayer.addLayer(mk); }
    })
    .catch(function(){ _wireItems=[]; _wireLayer=L.layerGroup(); }); }
function toggleWire(on){
  var cb=document.getElementById('wireToggle');
  var want=(on===undefined)?(cb?cb.checked:false):on;
  _wireBuild().then(function(){
    if(!_wireLayer)return;
    if(want){ _wireLayer.addTo(map); }
    else if(map.hasLayer(_wireLayer)){ map.removeLayer(_wireLayer); }
    var hint=document.getElementById('wireCount');
    if(hint) hint.textContent=_wireItems.length?(_wireItems.length+' pinned'):'none loaded'; }); }
(function wireInit(){ var cb=document.getElementById('wireToggle');
  if(cb) cb.addEventListener('change',function(){ toggleWire(cb.checked); }); })();
"""


def patch(text):
    if MARKER in text:
        return text, "already patched"
    for dep in ("function _esc", "function _href"):
        if dep not in text:
            raise SystemExit(f"could not find {dep} — aborting, no change")

    anchor = '<div class="leg-title" style="margin-top:9px;">Facility dots</div>'
    if anchor not in text:
        raise SystemExit("could not find the facility toggle block — aborting")
    text = text.replace(anchor, CONTROL_HTML + anchor, 1)

    js_anchor = "function _facPop(p){"
    if js_anchor not in text:
        raise SystemExit("could not find _facPop() — aborting, no change")
    text = text.replace(js_anchor, JS_BLOCK + "\n" + js_anchor, 1)
    return text, "patched"


def selftest():
    fails = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r} want {want!r}")

    sample = ('<div class="leg-title" style="margin-top:9px;">Facility dots</div>'
              '<label><input id="facToggle"></label>'
              "<script>function _esc(s){return s;} function _href(u){return u;}\n"
              "function _facPop(p){ return ''; }</script>")

    out, status = patch(sample)
    eq(status, "patched", "patch/applies")
    eq('id="wireToggle"' in out, True, "patch/toggle-added")
    eq(out.index('id="wireToggle"') < out.index("Facility dots"), True,
       "patch/toggle-before-facilities")
    eq("_wireBuild" in out, True, "patch/js-added")
    eq("checked>" in out.split('id="wireToggle"')[1][:20], False,
       "patch/off-by-default")

    again, st2 = patch(out)
    eq(st2, "already patched", "patch/idempotent")
    eq(again, out, "patch/no-change-on-rerun")

    try:
        patch('<div class="leg-title" style="margin-top:9px;">Facility dots</div>')
        fails.append("patch/missing-helpers not caught")
    except SystemExit:
        pass

    # behaviour requirements
    eq("cache:'no-store'" in JS_BLOCK, True, "js/always-fresh")
    eq("r.ok?r.json():[]" in JS_BLOCK, True, "js/missing-file-safe")
    eq(".catch(" in JS_BLOCK, True, "js/never-breaks-map")
    eq("Matched to:" in JS_BLOCK, True, "js/shows-match")
    eq("trust the story, not the pin" in JS_BLOCK, True, "js/honest-about-matcher")
    eq("localStorage" in JS_BLOCK, False, "js/no-browser-storage")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK (14 checks)")
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
