#!/usr/bin/env python3
"""patch_index_commentneutral.py — make the how-to-comment text work outside the anglosphere.

The guidance is shown on every town hall box worldwide, but it was written in
UK/US vocabulary: "case officer", "planning portal", "clerk's office". Those
names do not exist in most of the countries it appears in, and a reader looking
for a clerk in Lyon or Jakarta finds nothing.

The country-specific mechanism is already named in the line directly above this
one (enquête publique, zienswijze, askı, información pública, deposito e
osservazioni...). So this text should describe the SHAPE of the act, not the
British name for the desk. Idempotent.
"""
import re, sys

MARKER = "/* commentneutral */"

OLD_START = "<b>How to comment, and what makes it count.</b>"

NEW = (
    "<b>How to comment, and what makes it count.</b> Every notice names the "
    "office handling the file and gives a reference \\u2014 send your comment there, "
    "in writing, quoting that reference; the same office (or the council "
    "secretariat) says how to register to speak, usually days before the meeting. "
    "Include your <b>name, address and the file reference</b>, and file <b>before "
    "the deadline</b>: late comments are frequently never put before the "
    "decision-makers. Whether yours is weighed turns on relevance to the "
    "grounds the law allows \\u2014 drainage, traffic, contamination, noise, protected "
    "habitat, conflict with the adopted plan \\u2014 not on how strongly it is "
    "written. <b>One specific, evidenced objection beats a hundred signatures</b>, "
    "and a hundred signatures each making the same specific point beats both."
)


def patch(text):
    if MARKER in text:
        return text, "already patched"
    m = re.search(r'var COMMENT_HOWTO="(.*?)";', text, re.S)
    if not m:
        raise SystemExit("could not find COMMENT_HOWTO — run patch_index_commentnote.py first")
    if OLD_START not in m.group(1):
        raise SystemExit("COMMENT_HOWTO is not the expected text — aborting")
    import json
    text = (text[:m.start()] + MARKER + "\nvar COMMENT_HOWTO="
            + json.dumps(NEW, ensure_ascii=False) + ";" + text[m.end():])
    return text, "patched"


def selftest():
    fails = []
    for w in ("case officer", "planning portal", "clerk"):
        if w in NEW:
            fails.append(f"neutral/still-anglo: {w}")
    for w in ("names the office handling the file", "file reference",
              "before the deadline", "relevance to the grounds the law allows",
              "beats a hundred signatures"):
        if w not in NEW:
            fails.append(f"neutral/lost: {w}")
    sample = 'var COMMENT_HOWTO="<b>How to comment, and what makes it count.</b> old";'
    out, st = patch(sample)
    if st != "patched" or "case officer" in out:
        fails.append("patch/applies")
    again, st2 = patch(out)
    if st2 != "already patched" or again != out:
        fails.append("patch/idempotent")
    try:
        patch("nothing"); fails.append("patch/missing-anchor not caught")
    except SystemExit:
        pass
    if fails:
        print("SELFTEST FAILED"); [print("  -", f) for f in fails]; return 1
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
