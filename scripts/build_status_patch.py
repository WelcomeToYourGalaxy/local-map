#!/usr/bin/env python3
"""Turn check_status.py output into STATUS_PATCH.json.

    python3 build_status_patch.py trackerdata.json status_raw.jsonl STATUS_PATCH.json
    python3 build_status_patch.py trackerdata.json status_raw.jsonl STATUS_PATCH.json --report

Runs anywhere, including in the sandbox — it reads the checker's output file, not the network.

Vocabulary, from index.html: `active` (the default; `statusOf` returns it when the field is
absent), `dormant`, `defunct`. Only the last two render a badge, and `trackerVisible` hides
anything non-active unless the historical toggle is on — which `syncHistToggle` currently hides
entirely, because no entry has a status at all.

Classification
--------------
Deliberately conservative, because the cost is asymmetric. Marking a live body `defunct` hides
it from every user by default; leaving a dead one `active` shows a stale link. The first is
worse, so a URL only earns a non-active status on strong evidence.

    defunct   410 Gone
              a parked / for-sale / suspended page detected in the body text
              DNS failure (NXDOMAIN / getaddrinfo) — the host itself is gone

    dormant   404 or 403 on a host that still resolves and answers
              (the organisation may live on at a new path; the link is stale, not the body)

    active    2xx, 3xx, 401, 429, and every timeout or TLS error
              A timeout is a fact about the request, not about the body. Slow government
              servers time out constantly.

Everything classified `active` is OMITTED from the patch rather than written, since `statusOf`
already defaults to it. The patch therefore contains only the entries whose status changes.

Read the `--report` output before merging. The rules above are a starting point, not a verdict:
a 404 on a ministry's deep link usually means the page moved, and those are worth a look before
several hundred entries pick up a Dormant badge.
"""
import json, sys, argparse, collections, re

DEAD_DNS = re.compile(r"getaddrinfo|Name or service not known|NXDOMAIN|nodename nor servname",
                      re.I)


def walk(td):
    for iso, c in td.items():
        if not isinstance(c, dict):
            continue
        stack = [c]
        while stack:
            node = stack.pop()
            for t in node.get("trackers", []) or []:
                yield iso, t
            for _, v in (node.get("sub") or {}).items():
                stack.append(v)


def classify(r):
    code, err, msg = r.get("code"), r.get("error") or "", r.get("server_msg")
    if msg:
        return "defunct", f"page says: {msg}"
    if code == 410:
        return "defunct", "410 Gone"
    if err and DEAD_DNS.search(err):
        return "defunct", "host does not resolve"
    if code in (404, 403):
        return "dormant", f"{code} on a host that still answers"
    return "active", None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trackerdata")
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    res = {}
    for line in open(a.raw, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            res[r["url"]] = r
        except Exception:
            pass
    print(f"{len(res)} checker results")

    td = json.load(open(a.trackerdata, encoding="utf-8"))
    rows, tally, unchecked = [], collections.Counter(), 0
    reasons = collections.Counter()
    for iso, t in walk(td):
        u = t.get("url")
        if not u:
            continue
        r = res.get(u)
        if not r:
            unchecked += 1
            continue
        st, why = classify(r)
        tally[st] += 1
        if st == "active":
            continue
        reasons[why] += 1
        rows.append({"country": iso, "url": u, "name": t.get("name", ""),
                     "status": st, "evidence": why,
                     "code": r.get("code"), "error": r.get("error")})

    print(f"active {tally['active']} · dormant {tally['dormant']} · defunct {tally['defunct']}"
          f" · unchecked {unchecked}")
    if unchecked:
        print("  (unchecked entries are left alone — re-run check_status.py --resume)")

    if a.report:
        print("\nevidence")
        for w, n in reasons.most_common():
            print(f"   {n:5d}  {w}")
        print("\nsample of what would be flagged")
        for r in rows[:25]:
            print(f"   [{r['status']:7}] {r['country']}  {r['name'][:60]}")

    rows.sort(key=lambda r: (r["status"], r["country"], r["name"]))
    json.dump({"_meta": {
        "task": "set status where the link check gives strong evidence the body is gone",
        "target": "entries at any depth, matched on country + url",
        "count": len(rows),
        "omitted": "entries classified active are not written — statusOf already defaults to active",
        "rules": ("defunct: 410, a parked/for-sale/suspended page, or a host that does not "
                  "resolve. dormant: 404 or 403 on a host that still answers. active: "
                  "everything else, including all timeouts and TLS errors."),
        "caution": ("a 404 on a deep link usually means the page moved, not that the body is "
                    "gone. Read the report before merging — a wrong 'defunct' hides a live "
                    "organisation from every user by default."),
        "values_used": sorted({r["status"] for r in rows})},
        "rows": rows}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwrote {a.out} — {len(rows)} rows")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()   # piping into head closes stdout early; not an error
    except KeyboardInterrupt:
        sys.exit(130)
