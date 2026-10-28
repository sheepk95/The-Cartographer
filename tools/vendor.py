"""Check or rebuild the bundled skills from catalogue/bundled.json.

  python tools/vendor.py verify     every bundled file matches its recorded sha256 (no network)
  python tools/vendor.py fetch      re-download every file from upstream at its pinned commit, then verify
  python tools/vendor.py notices    rewrite THIRD_PARTY_NOTICES.md from bundled.json

fetch reads raw.githubusercontent.com only; nothing it downloads is executed.
"""
import hashlib, json, os, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "catalogue", "bundled.json")


def load():
    with open(META, encoding="utf-8") as f:
        return json.load(f)["skills"]


def folder(e):
    return os.path.join(ROOT, "skills", *e["id"].split("/"))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def expected(e):
    want = dict(e["files"])
    for name, add in (e.get("added") or {}).items():
        want[name] = add["sha256"]
    return want


def verify(entries):
    bad = 0
    for e in entries:
        d = folder(e)
        for rel, h in expected(e).items():
            p = os.path.join(d, *rel.split("/"))
            if not os.path.isfile(p):
                print("MISSING %s/%s" % (e["id"], rel))
                bad += 1
            elif sha(p) != h:
                print("CHANGED %s/%s" % (e["id"], rel))
                bad += 1
    n = sum(len(expected(e)) for e in entries)
    print("verify: %d skills, %d files, %d problems" % (len(entries), n, bad))
    return 1 if bad else 0


def raw_url(repo, commit, path):
    return "https://raw.githubusercontent.com/%s/%s/%s" % (repo, commit, urllib.parse.quote(path))


def fetch(entries):
    for e in entries:
        d = folder(e)
        prefix = (e["path"].strip("/") + "/") if e["path"] else ""
        jobs = [(prefix + rel, rel) for rel in e["files"]]
        jobs += [(add["from"], name) for name, add in (e.get("added") or {}).items()]
        for src, rel in jobs:
            with urllib.request.urlopen(raw_url(e["repo"], e["commit"], src), timeout=60) as r:
                data = r.read()
            p = os.path.join(d, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
        print("fetched %s" % e["id"])
    return verify(entries)


def notices(entries):
    lines = ["# Third-party notices", "",
             "The `skills/` folder bundles %d agent skills written by other people. Each skill keeps its own "
             "licence: the LICENSE file inside its folder applies to that folder. They are copied unchanged from "
             "the upstream commit listed below. The Librarian's own code (everything outside `skills/`) is under "
             "the MIT licence in `LICENSE`." % len(entries), "",
             "| skill | licence | source (pinned commit) |", "|---|---|---|"]
    for e in entries:
        src = "https://github.com/%s/tree/%s/%s" % (e["repo"], e["commit"], e["path"]) if e["path"] else \
            "https://github.com/%s/tree/%s" % (e["repo"], e["commit"])
        lines.append("| `%s` | %s | [%s@%s](%s) |" % (e["id"], e["licence"], e["repo"], e["commit"][:10], src))
    with open(os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote THIRD_PARTY_NOTICES.md (%d skills)" % len(entries))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "verify"
    fn = {"verify": verify, "fetch": fetch, "notices": notices}.get(cmd)
    if fn is None:
        print(__doc__)
        return 2
    return fn(load())


if __name__ == "__main__":
    sys.exit(main())
