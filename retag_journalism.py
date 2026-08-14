#!/usr/bin/env python3
"""retag_journalism.py — investigative newsrooms are not environmental studies.

Ortak (TUR) surfaced under "Get the environmental study & a polluter's record"
because it carried environment:eia. Ten more entries share that mis-tag: they
are investigative newsrooms, so they belong in the research/help lenses.

TI Zimbabwe is deliberately EXCLUDED: it is an anti-corruption chapter that
runs advice centres, not a newsroom, and its tagging needs its own decision.

Idempotent: entries already retagged are skipped.
"""
import json, sys

# url -> (tags, desc-prefix replacement)
RETAG = {
    "https://publicherald.org": "USA",
    "http://mongabay.com": "USA",
    "https://thenarwhal.ca": "CAN",
    "https://contracorriente.red": "HND",
    "https://thegeckoproject.org": "GBR",
    "https://watershedinvestigations.com": "GBR",
    "https://www.eiforum.org": "FRA",
    "http://oxpeckers.org": "ZAF",
    "https://ortak.org": "TUR",
    "https://indepthsolomons.com.sb": "SLB",
}
NEW_TAGS = ["organizing:research", "organizing:help"]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "trackerdata.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    data = json.load(open(src))
    changed, seen = [], set()

    def walk(node):
        for e in node.get("trackers", []) or []:
            key = (e.get("url") or "").rstrip("/")
            if key in RETAG and "environment:eia" in e.get("tags", []):
                tags = [t for t in e["tags"] if t != "environment:eia"]
                for t in NEW_TAGS:
                    if t not in tags:
                        tags.append(t)
                e["tags"] = tags
                changed.append(e.get("name"))
                seen.add(key)
        for child in (node.get("sub") or {}).values():
            walk(child)

    for node in data.values():
        walk(node)

    print(f"retagged: {len(changed)}/{len(RETAG)}")
    for n in changed:
        print(f"  {n}")
    missing = set(RETAG) - seen
    if missing:
        print(f"already done or not found: {sorted(missing)}")
    json.dump(data, open(dst, "w"), ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
