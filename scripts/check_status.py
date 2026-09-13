#!/usr/bin/env python3
"""Check every URL in trackerdata.json and write a result line per URL.

    python3 check_status.py trackerdata.json status_raw.jsonl
    python3 check_status.py trackerdata.json status_raw.jsonl --workers 24 --timeout 20
    python3 check_status.py trackerdata.json status_raw.jsonl --resume

Run this OUTSIDE the Claude sandbox — its egress proxy allows only package registries and
raw.githubusercontent.com, so every other host returns 403 `host_not_allowed`. Everything else
in this pipeline works in the sandbox; this one step needs a normal network.

Standard library only. No pip install.

~7,900 distinct URLs. At 16 workers and a 15s timeout expect roughly 20-40 minutes, longer if
many hosts are slow to fail. `--resume` skips URLs already in the output file, so you can stop
it and restart.

Output: one JSON object per line —

    {"url": "...", "code": 200, "final": "...", "redirected": false,
     "error": null, "elapsed": 0.42, "server_msg": null}

Feed it to build_status_patch.py, which turns it into a status patch. Nothing here decides
anything; a 404 is evidence, not a verdict, and the classification is deliberately separate.
"""
import json, sys, ssl, time, gzip, io, os, argparse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (compatible; WelcomeToYourGalaxy-linkcheck/1.0; "
      "+mailto:wheelock.chris@gmail.com)")


def urls_from(td_path):
    td = json.load(open(td_path, encoding="utf-8"))
    out = []
    seen = set()

    def walk(node):
        for t in node.get("trackers", []) or []:
            u = t.get("url")
            if u and u.startswith(("http://", "https://")) and u not in seen:
                seen.add(u)
                out.append(u)
        for _, v in (node.get("sub") or {}).items():
            walk(v)

    for _, c in td.items():
        if isinstance(c, dict):
            walk(c)
    return out


def check(url, timeout):
    """HEAD first; fall back to a ranged GET, because a lot of government servers
    return 403 or 405 to HEAD and 200 to GET. A HEAD-only checker invents dead links."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # expired certs are a finding, not a fetch failure
    t0 = time.time()

    def attempt(method):
        req = urllib.request.Request(url, method=method)
        req.add_header("User-Agent", UA)
        req.add_header("Accept", "*/*")
        req.add_header("Accept-Encoding", "gzip")
        if method == "GET":
            req.add_header("Range", "bytes=0-2047")
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = b""
            if method == "GET":
                raw = r.read(2048)
                if r.headers.get("Content-Encoding") == "gzip":
                    try:
                        body = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(2048)
                    except Exception:
                        body = raw
                else:
                    body = raw
            return r.getcode(), r.geturl(), body

    code = final = None
    err = None
    body = b""
    for method in ("HEAD", "GET"):
        try:
            code, final, body = attempt(method)
            err = None
            if code and code < 400:
                break
        except urllib.error.HTTPError as e:
            code, final, err = e.code, url, None
            if method == "GET" or code not in (403, 405, 501):
                break
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:160]
            code, final = None, url
            if method == "GET":
                break

    msg = None
    if body:
        low = body.decode("utf-8", "ignore").lower()
        for m in ("domain is for sale", "buy this domain", "account suspended",
                  "site is no longer", "has been discontinued", "parked domain",
                  "this domain may be for sale", "404 not found", "page not found"):
            if m in low:
                msg = m
                break

    return {"url": url, "code": code, "final": final,
            "redirected": bool(final and final.rstrip("/") != url.rstrip("/")),
            "error": err, "elapsed": round(time.time() - t0, 2), "server_msg": msg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trackerdata")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()

    urls = urls_from(a.trackerdata)
    done = set()
    if a.resume and os.path.exists(a.out):
        for line in open(a.out, encoding="utf-8"):
            try:
                done.add(json.loads(line)["url"])
            except Exception:
                pass
        urls = [u for u in urls if u not in done]
        print(f"resuming — {len(done)} already checked, {len(urls)} to go")
    else:
        print(f"{len(urls)} distinct URLs")

    mode = "a" if a.resume else "w"
    n = 0
    with open(a.out, mode, encoding="utf-8") as f, ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(lambda u: check(u, a.timeout), urls):
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            n += 1
            if n % 100 == 0:
                print(f"  {n}/{len(urls)}", flush=True)
    print(f"wrote {a.out} — {n} results")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()   # piping into head closes stdout early; not an error
    except KeyboardInterrupt:
        sys.exit(130)
