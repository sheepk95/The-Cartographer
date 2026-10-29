"""`cartographer install`: vet one skill from GitHub, then copy it into a local skills folder with its licence and
its source.

Steps (nothing downloaded is ever run):
  1. The target: a skills.sh page URL, or owner/repo[/skill]. A skills.sh page (robots permitting) gives the repo,
     the install count, the stars and the audits at fetch time.
  2. The repo's current commit: one unauthenticated GitHub API call (or --ref <40-hex sha>, which needs none).
  3. The tarball of exactly that commit from codeload.github.com, into a staging folder, under a size cap.
  4. The skill folder at that commit: the folder named like the skill, or whose SKILL.md is named like it.
  5. The licence: SKILL.md front matter, and the licence files of the nearest folder that has any (the skill folder,
     then each parent up to the repository root). Their text is carried into the installed folder. When the two
     disagree, both apply, and a refused one decides. Unknown, missing, non-commercial, no-derivatives and
     source-available licences (and any in $CARTOGRAPHER_REFUSE_LICENCES) are refused unless --allow-any-licence.
     Copyleft licences are allowed, with a note. A skills.sh audit that says Fail is refused unless
     --allow-audit-fail.
  6. The file list, with scripts, binaries, executable files and agent configuration flagged. Agent configuration
     (a plugin manifest, MCP or hook settings, front matter `hooks` or `allowed-tools`, a SKILL.md shell command) can
     be run by an agent host with no command from you, so it is refused unless --allow-agent-config. These are pattern
     checks that fail closed (quoted or spaced keys and YAML forms they cannot read count too); agent configuration
     names below the top of the skill folder are listed as a warning. Names that cannot be written the same way on
     every OS are refused. Then a yes/no question unless --yes.
  7. The copy: into <dest>/<safe name> (never over an existing folder), files written without execute bits, plus
     .cartographer-source.json (repository, commit, path, licence, SHA-256 per file, the skills.sh figures and the
     time).

Exit codes: 0 installed, 1 refused (licence, audit, exists, declined, not found), 2 bad arguments, 3 transient failure
(network, rate limit): run it again later.
"""
import hashlib, json, os, re, secrets, shutil, sys, tarfile, time, unicodedata

from . import __version__, frontmatter, licences, skillsh, web

SOURCE_FILE = ".cartographer-source.json"
FORMAT = "the-cartographer/source-1"
MAX_TARBALL = 200 * 1024 * 1024
MAX_FILES = 500
MAX_SKILL_BYTES = 20 * 1024 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SEG = r"[A-Za-z0-9_.-]{1,100}"
TARGET_RE = re.compile(r"^(%s)/(%s)(?:/([A-Za-z0-9_.:&%%-]{1,160}))?$" % (SEG, SEG))
SCRIPT_EXT = {".py", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".bat", ".cmd", ".js", ".mjs", ".cjs", ".ts",
              ".rb", ".pl", ".php", ".lua", ".exe", ".dll", ".so", ".dylib", ".jar", ".vbs", ".applescript"}
# Windows device names (Python 3.13's ntpath.isreserved list, plus COM0 and LPT0): "aux.md" is the device AUX there.
RESERVED = ({"con", "prn", "aux", "nul", "conin$", "conout$"} | {"com" + c for c in "0123456789\u00b9\u00b2\u00b3"}
            | {"lpt" + c for c in "0123456789\u00b9\u00b2\u00b3"})
MAX_MEMBERS = 100000                      # archive members read at most (the whole repository, not just the skill)
MAX_UNPACKED = 2 * 1024 * 1024 * 1024     # bytes the members say they hold, at most (a small archive can claim more)
NOT_PORTABLE_RE = re.compile(r'[<>:"|?*\x00-\x1f\x7f]|[. ]$')  # a name Windows cannot write, or writes as another
# Agent configuration that a host may load and run with no command from you: a plugin manifest (hooks, MCP servers),
# MCP and settings files, hook folders. Refused unless --allow-agent-config.
AGENT_DIRS = {".claude-plugin", ".codex-plugin", ".cursor-plugin", ".claude", "hooks"}
AGENT_FILES = {".mcp.json", ".lsp.json", "settings.json", "settings.local.json", "hooks.json", "plugin.json"}
AGENT_KEYS = ("hooks", "allowed-tools", "allowed_tools")
# A SKILL.md command the host runs when the skill loads. Claude Code's own patterns are /```!\s*\n?[\s\S]*?\n?```/g
# (a fence anywhere) and /(?<=^|\s)!`[^`]+`/gm with JavaScript's \s (NBSP, U+2028, U+3000, U+FEFF and the rest).
# Python's \s plus U+FEFF covers that \s; zero-width and other format characters are added so it fails closed.
SKILL_SHELL_RE = re.compile(r"(?:```|~~~)!|(?<![^\s\ufeff\u00ad\u180e\u200b-\u200f\u2060-\u2064])!`")
# Front matter lines a YAML host may read as an agent key: quoted, spaced or underscored ("hooks" :, 'allowed_tools':).
AGENT_KEY_RE = re.compile(r"""(?i)^[ \t]*["']?(hooks|allowed[-_ ]?tools)["']?[ \t]*:(.*)$""")
# Top-level front matter written in YAML forms this check cannot read (a flow mapping, an explicit "? key", a merge key,
# an anchor, alias or tag, a double-quoted key with escapes such as "ho\x6fks"): flagged, since any could hide a key.
ODD_FRONT_MATTER_RE = re.compile(r'^(\?|<<|[!&*{\[]|"[^"]*\\)')
# Below the top of the skill folder, or under these names anywhere, agent configuration is only listed as a warning: a
# host loads it from a plugin or project root, not from inside a skill.
WARN_DIRS = AGENT_DIRS | {".codex", ".cursor", ".vscode", "agents", "commands"}


class Refusal(Exception):
    """A decision not to install (exit 1). Not a network problem."""


class BadTarget(ValueError):
    """Exit 2: the target or an option cannot be read."""


def default_dest():
    return os.path.join(os.path.expanduser("~"), ".agents", "skills")


def safe_name(name):
    """A folder name that is the same on every OS: lower case, [a-z0-9._-], no leading dot, at most 64 characters."""
    s = re.sub(r"[^a-z0-9._-]+", "-", (name or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("._-")[:64].strip("._-")
    if not s:
        raise BadTarget("cannot make a folder name from %r" % name)
    if s.split(".")[0] in RESERVED:
        s = "skill-" + s
    return s


def parse_target(t):
    """(owner, repo, skill or None, skills.sh page URL or None)."""
    t = (t or "").strip()
    if t.startswith(("http://", "https://")):
        sid = skillsh.skill_id(t)
        if not sid:
            raise BadTarget("not a skills.sh skill page URL: %s" % t[:200])
        o, r, s = sid.split("/", 2)
        return o, r, s, skillsh.page_url(sid)
    m = TARGET_RE.match(t.strip("/"))
    if not m:
        raise BadTarget("give a skills.sh page URL or owner/repo[/skill], not %r" % t[:200])
    o, r, s = m.groups()
    return o, r, s, (skillsh.page_url("%s/%s/%s" % (o, r, s)) if s else None)


# ---------------------------------------------------------------- remote steps

def page_facts(f, url):
    """The skills.sh figures for the provenance record, or None. Failure here is not fatal: the page is optional."""
    try:
        if f.robots is None:
            f.load_robots(max_age=skillsh.NAMES_MAX_AGE)
        st, _, body = f.get(url, skillsh.PAGE_CAP, kind="page")
    except web.Refused as e:
        return {"error": str(e)}
    except web.WebError as e:
        return {"error": str(e)}
    if st != 200:
        return {"error": "HTTP %s" % st}
    d = skillsh.parse_skill_page(body.decode("utf-8", "replace"))
    return {"page": url, "name": d.get("name"), "repo": d.get("repo"), "installs": d.get("installs"),
            "installs_note": skillsh.INSTALLS_NOTE, "stars": d.get("stars"), "stars_text": d.get("stars_text"),
            "stars_note": skillsh.STARS_NOTE, "audits": d.get("audits"), "first_seen": d.get("first_seen"),
            "fetched_at": web.utc()}


def resolve_commit(f, owner, repo, ref="HEAD"):
    url = "https://api.github.com/repos/%s/%s/commits/%s" % (owner, repo, ref)
    st, _, body = f.get(url, 4096, accept="application/vnd.github.sha")
    if st in (404, 422):
        raise Refusal("GitHub has no repository %s/%s with ref %s" % (owner, repo, ref))
    if st != 200:
        raise web.WebError("the GitHub API answered HTTP %s for %s/%s" % (st, owner, repo))
    sha = body.decode("ascii", "replace").strip()
    if not SHA_RE.match(sha):
        raise web.WebError("the GitHub API did not return a commit sha")
    return sha


def download(f, owner, repo, sha, dest, cap=MAX_TARBALL):
    try:
        st, _, body = f.get("https://codeload.github.com/%s/%s/tar.gz/%s" % (owner, repo, sha), cap,
                            accept="application/gzip")
    except web.TooLarge:  # not transient: the same commit is the same size tomorrow
        raise Refusal("the repository tarball is over the %d MB cap" % (cap // 1048576))
    if st == 404:
        raise Refusal("GitHub has no tarball for %s/%s at %s" % (owner, repo, sha))
    if st != 200:
        raise web.WebError("codeload answered HTTP %s" % st)
    with open(dest, "wb") as fh:  # data only: it is read with tarfile below and never run
        fh.write(body)
    return len(body)


# ---------------------------------------------------------------- reading the tarball (never extractall)

def _clean_rel(name):
    """The path inside the repository (top folder removed), or raise Refusal for an unsafe member name.

    Refused anywhere in the name: a NUL, a backslash and a colon. On Windows, os.path.join starts a new path at a
    part like "Q:evil" (drive Q), so a colon in ANY part escapes the folder; a backslash is a second separator there.
    Refused too: an absolute name and a ".." part."""
    if "\x00" in name or "\\" in name:
        raise Refusal("the archive has a member name with a backslash or NUL: %r" % name[:120])
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise Refusal("the archive has an absolute member path: %r" % name[:120])
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise Refusal("the archive has a member path that climbs out: %r" % name[:120])
    if any(":" in p for p in parts):
        raise Refusal("the archive has a member name with a colon (a drive or stream on Windows): %r" % name[:120])
    return "/".join(parts[1:])  # GitHub tarballs hold one top folder: <repo>-<sha>/


class Archive:
    def __init__(self, path):
        self.tf = tarfile.open(path, "r:gz")
        try:
            self._index()
        except BaseException:
            self.tf.close()  # else the open file keeps Windows from deleting the staging folder
            raise

    def _index(self):
        self.members = {}
        self.skipped = []
        self.pax_commit = (self.tf.pax_headers or {}).get("comment")
        count = claimed = 0
        for m in self.tf:  # one member at a time, so the limits apply before the whole archive is read
            count += 1
            claimed += max(0, m.size)
            if count > MAX_MEMBERS or claimed > MAX_UNPACKED:
                raise Refusal("the archive is too big to read (over %d members or %d GB unpacked)" % (
                    MAX_MEMBERS, MAX_UNPACKED // 1024 ** 3))
            rel = _clean_rel(m.name)
            if not rel:
                continue
            if m.isdir():
                continue
            if not m.isfile():  # symlinks, hard links, devices, fifos: never written
                self.skipped.append((rel, "link or special file"))
                continue
            self.members[rel] = m

    def read(self, rel, cap=None):
        fh = self.tf.extractfile(self.members[rel])
        return fh.read() if cap is None else fh.read(cap)

    def close(self):
        self.tf.close()

    def skill_dirs(self):
        return sorted(os.path.dirname(r) if "/" in r else "" for r in self.members
                      if r.rsplit("/", 1)[-1] == "SKILL.md")


def pick_folder(arc, slug, path=None):
    dirs = arc.skill_dirs()
    if path is not None:
        p = path.strip("/")
        if p not in dirs:
            raise Refusal("no SKILL.md at %s/ in this commit" % (p or "(repo root)"))
        return p
    if not dirs:
        raise Refusal("this commit holds no SKILL.md at all")
    if slug:
        want = slug.casefold()
        hits = []
        for d in dirs:
            meta = frontmatter.parse(arc.read((d + "/" if d else "") + "SKILL.md", 16384).decode("utf-8", "replace"))
            if d.rsplit("/", 1)[-1].casefold() == want or (meta.get("name") or "").strip().casefold() == want:
                hits.append(d)
        if len(hits) == 1:
            return hits[0]
        raise Refusal("%s folders match %r%s; pick one with --path" % (
            "no" if not hits else len(hits), slug, ": " + ", ".join(hits[:10]) if hits else
            " (folders with a SKILL.md: %s)" % ", ".join((d or ".") for d in dirs[:20])))
    if len(dirs) == 1:
        return dirs[0]
    raise Refusal("this repository holds %d skills; name one (owner/repo/skill) or use --path: %s" % (
        len(dirs), ", ".join((d or ".") for d in dirs[:20])))


def _file_licence(ids):
    """One id for the licence files of one folder: COPYING plus COPYING.LESSER is the LGPL; several others all apply."""
    ids = list(dict.fromkeys(ids))
    lesser = [i for i in ids if i.startswith("LGPL-")]
    if lesser and all(i.startswith(("GPL-", "LGPL-")) for i in ids):
        return lesser[0]
    return " AND ".join(ids)


def detect_licence(arc, folder):
    """(spdx, source, evidence, texts, repo_wide).

    Read: the SKILL.md front matter `license:` field, and the nearest folder (the skill folder, then each parent up to
    the repository root) that holds licence files. texts: those licence files; their text is carried into the
    installed folder even when the front matter names the licence, since MIT and Apache-2.0 ask for it. When the
    front matter and the files disagree, both apply: "A AND B" when both are open, else the refused one decides.
    repo_wide: the decision rests on a file above the skill folder (or on there being none), so it holds for the
    whole repository."""
    pre = folder + "/" if folder else ""
    evidence = []
    meta = frontmatter.parse(arc.read(pre + "SKILL.md", 65536).decode("utf-8", "replace"))
    field = meta.get("license") or meta.get("licence")
    fm = None
    if field:
        fm = licences.from_field(field if isinstance(field, str) else str(field))
        evidence.append({"source": "SKILL.md front matter", "value": skillsh.clean(field, 120),
                         "spdx": fm or "(points to a file)"})
    d, texts, ids, where = folder, [], [], None
    while True:
        files = sorted(r for r in arc.members if (r.rsplit("/", 1)[0] if "/" in r else "") == d
                       and licences.LICENCE_FILE_RE.match(r.rsplit("/", 1)[-1]))
        if files:
            where = "the skill folder" if d == folder else ("the repository root" if not d else "%s/" % d)
            for rel in files:
                spdx = licences.from_text(arc.read(rel, 262144).decode("utf-8", "replace"))
                evidence.append({"source": "licence file in %s" % where, "path": rel, "spdx": spdx})
                texts.append(rel)
                ids.append(spdx)
            break
        if not d:
            break
        d = d.rsplit("/", 1)[0] if "/" in d else ""
    above = bool(texts) and d != folder
    if fm is None and not texts:
        return "NONE", "no licence found", evidence, [], True
    fsource = "%s in %s" % (", ".join(r.rsplit("/", 1)[-1] for r in texts), where)
    if fm is None:
        return _file_licence(ids), fsource, evidence, texts, above
    filed = _file_licence(ids) if texts else None
    if filed is None or filed == fm:
        return fm, "SKILL.md front matter", evidence, texts, False
    fm_ok, file_ok = licences.policy(fm)[0], licences.policy(filed)[0]
    source = "SKILL.md front matter says %s, %s says %s" % (fm, fsource, filed)
    if fm_ok and file_ok:
        if " OR " in fm:  # a choice in the front matter: the file is one of the choices, or its terms are the ones
            return (fm if filed in licences.split(fm)[1] else filed), source, evidence, texts, False
        return "%s AND %s" % (fm, filed), source, evidence, texts, False
    return (filed, source, evidence, texts, above) if not file_ok else (fm, source, evidence, texts, False)


def notices_on_path(arc, folder):
    """NOTICE files in the parent folders of the skill, up to the root (Apache-2.0 and others ask to keep them)."""
    out, d = [], folder
    while d:
        d = d.rsplit("/", 1)[0] if "/" in d else ""
        out += sorted(r for r in arc.members if (r.rsplit("/", 1)[0] if "/" in r else "") == d
                      and licences.NOTICE_FILE_RE.match(r.rsplit("/", 1)[-1]))
    return out


def flags_for(rel, data, mode):
    out = []
    ext = os.path.splitext(rel)[1].lower()
    if ext in SCRIPT_EXT or data[:2] == b"#!":
        out.append("script")
    if b"\x00" in data[:8192]:
        out.append("binary")
    if mode & 0o111:
        out.append("executable bit (dropped)")
    if len(data) > 1024 * 1024:
        out.append("large")
    return out


# ---------------------------------------------------------------- the install

def sha256(b):
    return hashlib.sha256(b).hexdigest()


def plan(arc, folder):
    """[(rel inside the skill, data, flags)] for every regular file of the skill folder, within the limits."""
    pre = folder + "/" if folder else ""
    files, total = [], 0
    for rel in sorted(arc.members):
        if not rel.startswith(pre):
            continue
        inner = rel[len(pre):]
        if inner.split("/", 1)[0] == ".git" or inner == SOURCE_FILE:
            continue
        if len(files) >= MAX_FILES or total + arc.members[rel].size > MAX_SKILL_BYTES:  # checked BEFORE reading
            raise Refusal("the skill folder is over the limit (%d files, %d MB)" % (MAX_FILES,
                                                                                 MAX_SKILL_BYTES // 1048576))
        data = arc.read(rel, arc.members[rel].size)
        total += len(data)
        files.append((inner, data, flags_for(inner, data, arc.members[rel].mode)))
    return files


def unportable(names):
    """[(name, why)] for names that cannot be written the same way on every OS: a part Windows refuses or changes
    (reserved device names, <>:"|?*, control characters, a trailing dot or space), or two names that differ only in
    case (one would overwrite the other on Windows and macOS)."""
    out, seen = [], {}
    for n in names:
        for part in n.split("/"):
            if NOT_PORTABLE_RE.search(part) or part.split(".")[0].rstrip(" ").lower() in RESERVED:
                out.append((n, "a name Windows cannot write as it is"))
                break
        k = unicodedata.normalize("NFC", n).casefold()
        if k in seen:
            out.append((n, "differs from %s only in case" % seen[k]))
        else:
            seen[k] = n
    return out


def _front_lines(text):
    """The front matter lines of a SKILL.md, read leniently so a host's parser never sees more than this does: leading
    blank lines and BOMs are skipped, and front matter with no closing line runs to the end of the file. Only a "---"
    at the start of a line closes it, as in the host: a YAML "..." or an indented "---" does not, so keys after one
    are still checked."""
    t = (text or "").lstrip("\ufeff \t\r\n")
    lines = t.splitlines()
    if not lines or not lines[0].startswith("---"):
        return []
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return lines[1:i]
    return lines[1:]


_EMPTY = {"", "{}", "[]", "~", "null", '""', "''"}


def front_matter_agent_keys(text):
    """Why the front matter may give the host hooks or pre-approved tools: [reason], empty when it cannot."""
    lines = _front_lines(text)
    out = []
    content = [l for l in lines if l.strip() and not l.lstrip().startswith("#")]
    for n, line in enumerate(content):
        if not line[:1].isspace() and ODD_FRONT_MATTER_RE.match(line):
            out.append("front matter in a YAML form the cartographer cannot check (%s)" % skillsh.clean(line, 40))
            continue
        m = AGENT_KEY_RE.match(line)
        if not m:
            continue
        value = re.sub(r"[ \t]+#.*$", "", m.group(2)).strip()
        nxt = content[n + 1] if n + 1 < len(content) else ""
        new_key = not nxt or (not nxt[:1].isspace() and not nxt.startswith("-"))
        if value.lower() not in _EMPTY or (value == "" and not new_key):
            out.append("front matter %s" % m.group(1))
    return list(dict.fromkeys(out))


def agent_config(files, meta, skill_md):
    """[(name, why)] for what an agent host may load and run with no command from you (see AGENT_DIRS)."""
    out = []
    for inner, _, _ in files:
        parts = inner.split("/")
        if len(parts) > 1 and parts[0].lower() in AGENT_DIRS:
            out.append((inner, "agent config folder %s/" % parts[0]))
        elif len(parts) == 1 and parts[0].lower() in AGENT_FILES:
            out.append((inner, "agent config file"))
    keys = [k for k in meta if k.lower() in AGENT_KEYS and str(meta[k]).strip() not in _EMPTY]
    why = ["front matter %s" % k for k in keys] + front_matter_agent_keys(skill_md)
    if why:
        out.append(("SKILL.md", "; ".join(dict.fromkeys(why))))
    if SKILL_SHELL_RE.search(skill_md):
        out.append(("SKILL.md", "a command the host runs when the skill loads (!`...`)"))
    return out


def agent_config_warnings(files, refused=()):
    """[(name, why)] for agent configuration names that are not refused (see WARN_DIRS): listed, not refused."""
    out = []
    for inner, _, _ in files:
        if inner in refused:
            continue
        parts = inner.split("/")
        dirs = [d for d in parts[:-1] if d.lower() in WARN_DIRS]
        if dirs:
            out.append((inner, "inside %s/: a host loads it only from a plugin or project root" % dirs[-1]))
        elif len(parts) > 1 and parts[-1].lower() in AGENT_FILES:
            out.append((inner, "an agent config file below the top: a host loads it only from a plugin or project "
                               "root"))
    return out


def _inside(root, p):
    """True when p resolves (links followed) to a path strictly inside root."""
    try:
        r, q = os.path.realpath(root), os.path.realpath(p)
        return q != r and os.path.commonpath([r, q]) == r
    except ValueError:  # another drive on Windows
        return False


def write_skill(dest_root, name, files, added, record):
    """Copy into dest_root/name through a hidden temporary folder and one rename; never over an existing folder."""
    final = os.path.join(dest_root, name)
    if os.path.lexists(final):
        raise Refusal("%s already exists; nothing was changed (remove it yourself or use --name)" % final)
    os.makedirs(dest_root, exist_ok=True)
    tmp = os.path.join(dest_root, ".cartographer-tmp-%s" % secrets.token_hex(4))
    os.mkdir(tmp)
    try:
        for inner, data in [(i, d) for i, d, _ in files] + [(i, d) for i, (d, _) in added.items()]:
            p = os.path.join(tmp, *inner.split("/"))
            if not _inside(tmp, p):  # the last guard: whatever the name checks missed, nothing lands outside tmp
                raise Refusal("%r would be written outside the new folder; nothing was installed" % inner[:120])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as fh:  # plain data files: no execute bit is ever set
                fh.write(data)
        with open(os.path.join(tmp, SOURCE_FILE), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(record, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        if os.path.lexists(final):
            raise Refusal("%s appeared while installing; nothing was changed" % final)
        for attempt in range(5):
            try:
                os.rename(tmp, final)
                break
            except PermissionError:  # Windows: a virus scanner can hold a file it was just shown for a moment
                if attempt == 4 or os.path.lexists(final):
                    raise
                time.sleep(0.2 * (attempt + 1))
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


def run(target, dest=None, name=None, path=None, ref=None, yes=False, allow_any_licence=False,
        allow_audit_fail=False, no_page=False, fetcher=None, cache=None, out=print, ask=None, record_refusals=True,
        allow_agent_config=False):
    """Returns an exit code. All output goes through out()."""
    from . import finder  # for record_refusal (the finder's refused.jsonl)
    try:
        owner, repo, slug, page = parse_target(target)
    except BadTarget as e:
        out("cartographer install: %s" % e)
        return 2
    if ref is not None and not SHA_RE.match(ref):
        out("cartographer install: --ref must be a full 40-character commit sha")
        return 2
    try:
        name = safe_name(name or slug or repo) if name or slug else None
    except BadTarget as e:
        out("cartographer install: %s" % e)
        return 2
    fdir = skillsh.finder_dir(cache)
    f = fetcher or skillsh.fetcher_for(fdir, out=out)
    tok = os.environ.get("CARTOGRAPHER_GITHUB_TOKEN")
    if tok and not fetcher:
        f.extra_headers["api.github.com"] = {"Authorization": "Bearer " + tok}
    stage = os.path.join(skillsh.cache_dir() if cache is None else cache, "staging", secrets.token_hex(6))
    arc = None
    try:
        os.makedirs(stage)
        facts = None
        if page and not no_page:
            facts = page_facts(f, page)
            if facts and facts.get("repo") and facts["repo"].lower() != ("%s/%s" % (owner, repo)).lower():
                out("note: the skills.sh page names the repository %s; using it" % facts["repo"])
                owner, repo = facts["repo"].split("/", 1)
            if facts and facts.get("error"):
                out("note: skills.sh page not read (%s); installing without its figures" % facts["error"])
                facts = None
        fails = [a for a in (facts or {}).get("audits") or [] if str(a.get("status")).lower() == "fail"]
        if fails and not allow_audit_fail:
            raise Refusal("skills.sh audit says Fail (%s); pass --allow-audit-fail to install anyway" % ", ".join(
                a["provider"] for a in fails))
        sha = ref or resolve_commit(f, owner, repo)
        tgz = os.path.join(stage, "repo.tar.gz")
        size = download(f, owner, repo, sha, tgz)
        arc = Archive(tgz)
        if arc.pax_commit and SHA_RE.match(arc.pax_commit) and arc.pax_commit != sha:
            raise Refusal("the tarball is for commit %s, not %s" % (arc.pax_commit, sha))
        folder = pick_folder(arc, slug, path)
        pre = folder + "/" if folder else ""
        spdx, lsource, evidence, texts, repo_wide = detect_licence(arc, folder)
        ok, why = licences.policy(spdx)
        files = plan(arc, folder)
        taken = {i.casefold() for i, _, _ in files}
        added = {}
        for rel in [r for r in texts if not r.startswith(pre)] + notices_on_path(arc, folder):
            if arc.members[rel].size > 1024 * 1024:
                raise Refusal("%s is over 1 MB; a licence or NOTICE file that size is not carried" % rel)
            base = rel.rsplit("/", 1)[-1]
            inner, n = base, 1
            while inner.casefold() in taken:  # the skill has a file of that name: keep both
                inner, n = base + (".upstream" if n == 1 else ".upstream%d" % n), n + 1
            taken.add(inner.casefold())
            added[inner] = (arc.read(rel, arc.members[rel].size), rel)
        text_names = [r[len(pre):] for r in texts if r.startswith(pre)] + [i for i, (_, r) in added.items()
                                                                           if r in texts]
        skill_md = dict((i, d) for i, d, _ in files).get("SKILL.md", b"").decode("utf-8", "replace")
        meta = frontmatter.parse(skill_md)
        agent = agent_config(files, meta, skill_md)
        warn = agent_config_warnings(files, {n for n, _ in agent})
        if agent or warn:
            bad, nested = {n for n, _ in agent}, {n for n, _ in warn}
            files = [(i, d, fl + ["agent config (can run commands)"] if i in bad else
                      fl + ["agent config name (warning: not loaded from here)"] if i in nested else fl)
                     for i, d, fl in files]
        name = name or safe_name(meta.get("name") or folder.rsplit("/", 1)[-1] or repo)
        copyleft = licences.copyleft(spdx) if ok else []
        dest_root = os.path.abspath(dest or default_dest())
        out("%s/%s @ %s, folder %s/ (tarball %d KB)" % (owner, repo, sha[:12], folder or ".", size // 1024))
        out("licence: %s (from %s)%s" % (spdx, lsource, "" if ok else "  REFUSED: " + why))
        for e in evidence:
            out("  evidence: %s: %s" % (e["source"], e["spdx"]))
        if text_names:
            out("licence text: %s (kept in the installed folder)" % ", ".join(text_names))
        elif spdx != "NONE":
            out("note: upstream has no licence text, only the licence's name in SKILL.md; nothing to carry")
        if copyleft:
            out("note: %s is copyleft: if you pass this skill or a changed copy on, it must go under the same "
                "licence" % " and ".join(copyleft))
        if facts:
            aud = ", ".join("%s %s" % (a["provider"], a["status"]) for a in facts.get("audits") or []) or "none"
            out("skills.sh: installs %s (CLI telemetry), stars %s (whole repo, rounded), audits: %s" % (
                facts.get("installs"), facts.get("stars_text"), aud))
        out("files (%d):" % len(files))
        for inner, data, fl in files:
            out("  %-60s %8d B%s" % (inner, len(data), ("  [" + ", ".join(fl) + "]") if fl else ""))
        for rel, why_skip in arc.skipped:
            if rel.startswith((folder + "/") if folder else ""):
                out("  skipped %s (%s)" % (rel, why_skip))
        for inner, (_, rel) in added.items():
            out("  + %s (from %s, kept for the licence terms)" % (inner, rel))
        if any(fl for _, _, fl in files):
            out("Read the flagged files before you let an agent run them. The cartographer never runs them.")
        for n, why_agent in agent:
            out("  agent config: %s (%s)" % (n, why_agent))
        for n, why_warn in warn:
            out("  warning, agent config name: %s (%s); not refused, but do not copy it into place unread" % (
                n, why_warn))
        if not ok and not allow_any_licence:
            if record_refusals:
                entry = {"reason": "licence: %s (%s)" % (spdx, why)}
                entry.update({"repo": "%s/%s" % (owner, repo)} if repo_wide or not folder
                             else {"id": "%s/%s/%s" % (owner, repo, slug or name)})
                finder.record_refusal(entry, cache)
            raise Refusal("licence %s: %s. Pass --allow-any-licence only if you have the right to use it" % (
                spdx, why))
        if agent and not allow_agent_config:
            raise Refusal("the skill holds agent configuration that an agent host can load and run without asking "
                          "(%s). Read it, then pass --allow-agent-config to install it anyway" % "; ".join(
                              "%s: %s" % a for a in agent[:5]))
        bad = unportable([i for i, _, _ in files] + list(added))
        if bad:
            raise Refusal("names that cannot be written the same way on every system: %s" % "; ".join(
                "%s (%s)" % (skillsh.clean(n, 80), w) for n, w in bad[:5]))
        target_dir = os.path.join(dest_root, name)
        if os.path.lexists(target_dir):
            raise Refusal("%s already exists; nothing was changed (remove it yourself or use --name)" % target_dir)
        if not yes:
            if ask is None and not sys.stdin.isatty():
                raise Refusal("not a terminal, so no one can answer the question: add --yes to install")
            reply = (ask or input)("Install into %s? [y/N] " % target_dir)
            if (reply or "").strip().lower() not in ("y", "yes"):
                raise Refusal("not installed (you said no)")
        record = {
            "format": FORMAT, "id": name, "upstream_name": meta.get("name") or "", "repo": "%s/%s" % (owner, repo),
            "commit": sha, "path": folder, "licence": spdx, "licence_source": lsource, "licence_evidence": evidence,
            "licence_override": bool(not ok and allow_any_licence), "licence_text": text_names or None,
            "copyleft": bool(copyleft), "agent_config": [n for n, _ in agent] or None,
            "agent_config_warnings": [n for n, _ in warn] or None,
            "review": "not reviewed: installed by `cartographer install`; read it before an agent uses it",
            "files": {i: sha256(d) for i, d, _ in files},
            "added": {i: {"sha256": sha256(d), "from": rel} for i, (d, rel) in added.items()},
            "flags": {i: fl for i, _, fl in files if fl},
            "skills_sh": facts, "fetched_at": web.utc(), "tool": "the-cartographer %s" % __version__,
        }
        final = write_skill(dest_root, name, files, added, record)
        out("installed: %s (%s; provenance in %s)" % (final, spdx, SOURCE_FILE))
        return 0
    except Refusal as e:
        out("NOT INSTALLED: %s" % e)
        return 1
    except web.Refused as e:
        out("NOT INSTALLED: %s" % e)
        return 1
    except web.WebError as e:
        out("INSTALL FAILED (transient, nothing was changed): %s. Run it again later." % e)
        return 3
    except (tarfile.TarError, EOFError, OSError) as e:
        out("INSTALL FAILED (nothing was changed): %s" % e)
        return 3
    finally:
        if arc is not None:
            arc.close()
        shutil.rmtree(stage, ignore_errors=True)


# ---------------------------------------------------------------- reading records back (list, doctor, the catalogue)

def read_record(skill_dir):
    from .catalogue import provenance
    return provenance(skill_dir)


def changed_files(skill_dir, record):
    """Files whose SHA-256 no longer matches the record (edited, missing), relative names."""
    want = dict(record.get("files") or {})
    want.update({k: v.get("sha256") for k, v in (record.get("added") or {}).items() if isinstance(v, dict)})
    bad = []
    for rel, h in sorted(want.items()):
        p = os.path.join(skill_dir, *rel.split("/"))
        try:
            with open(p, "rb") as fh:
                if sha256(fh.read()) != h:
                    bad.append(rel)
        except OSError:
            bad.append(rel)
    return bad
