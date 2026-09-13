#!/usr/bin/env python3
"""Second pass over the URLs the first run flagged. Slow, retried, and root-aware.

    python3 recheck_status.py status_raw.jsonl status_recheck.jsonl
    python3 recheck_status.py status_raw.jsonl status_recheck.jsonl --delay 1.2 --resume

Why a second pass
-----------------
The first run flagged 621 URLs. Reading them shows two problems that make its verdicts
unusable as they stand:

**DNS.** 201 URLs came back `nodename nor servname`, including `ago.ms.gov`,
`sosbizsearch.ky.gov`, `ecorp.azcc.gov` and `nebraskalandtrust.org`. Those hosts are not gone —
`ago.ms.gov` resolves fine from a different machine. Sixteen workers resolving concurrently from
a home connection produces spurious NXDOMAIN. Treating that as `defunct` would hide 200 live
bodies.

**403.** 385 URLs returned 403, including `claude.ai`, `americanbar.org`, `nvcourts.gov` and
several EPA and Army Corps pages. Those are live sites refusing a scripted client. 403 means
"not to you", never "not here".

What this does differently
--------------------------
- One request at a time with a delay, so DNS and rate limiters are not the variable.
- Three attempts per URL with backoff, and a browser-like User-Agent.
- **Also fetches the site root** (`scheme://host/`) for every URL it checks. That is the test
  that separates the two cases the first run could not tell apart: if the deep link 404s but the
  root answers, the organisation is alive and the URL is stale — a link to fix, not a body to
  bury. If the root fails too, the body is a real candidate for `defunct`.

Output adds `root_code` and `root_error` to the same record shape. Feed both files to
build_status_patch.py; the recheck takes precedence.
"""
import json, sys, ssl, time, argparse, os, urllib.request, urllib.error, urllib.parse

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")


def fetch(url, timeout, ctx):
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "text/html,application/xhtml+xml,*/*;q=0.8")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    req.add_header("Range", "bytes=0-2047")
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.getcode(), r.geturl(), None


def try_hard(url, timeout, ctx, tries=3):
    code = final = err = None
    for i in range(tries):
        try:
            return fetch(url, timeout, ctx)
        except urllib.error.HTTPError as e:
            code, final, err = e.code, url, None
            if code not in (429, 500, 502, 503, 504):
                return code, final, err
        except Exception as e:
            code, final = None, url
            err = f"{type(e).__name__}: {e}"[:160]
        time.sleep(1.5 * (i + 1))
    return code, final, err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=25)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    todo = []
    for line in open(a.raw, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        code, err = r.get("code"), r.get("error") or ""
        if r.get("server_msg") or code in (403, 404, 410) or (code is None and err):
            todo.append(r["url"])

    done = set()
    if a.resume and os.path.exists(a.out):
        for line in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(line)["url"])
            except Exception:
                pass
        todo = [u for u in todo if u not in done]
        print(f"resuming — {len(done)} done, {len(todo)} to go")
    else:
        print(f"{len(todo)} URLs to recheck")
    print(f"one at a time, {a.delay}s apart, 3 tries each, plus the site root for every URL")
    print(f"estimate: about {len(todo) * (a.delay + 1.2) / 60:.0f} minutes\n")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    roots = {}
    with open(a.out, "a" if a.resume else "w", encoding="utf-8") as f:
        for i, url in enumerate(todo, 1):
            code, final, err = try_hard(url, a.timeout, ctx)
            p = urllib.parse.urlparse(url)
            root = f"{p.scheme}://{p.netloc}/"
            if root not in roots:
                time.sleep(a.delay)
                roots[root] = try_hard(root, a.timeout, ctx)
            rc, _, re_ = roots[root]
            f.write(json.dumps({
                "url": url, "code": code, "final": final,
                "redirected": bool(final and final.rstrip("/") != url.rstrip("/")),
                "error": err, "elapsed": None, "server_msg": None,
                "root": root, "root_code": rc, "root_error": re_,
            }, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
            time.sleep(a.delay)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()
    except KeyboardInterrupt:
        sys.exit(130)
