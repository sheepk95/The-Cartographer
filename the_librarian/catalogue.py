"""Build the skill catalogue the librarian reads: bundled skills plus the user's own skill folders.

The catalogue text is deterministic (sorted, no timestamps), so an unchanged set of skills gives a byte-identical
prompt and the backend's prompt cache keeps hitting.
"""
import hashlib, json, os, re
from dataclasses import dataclass, field

from . import frontmatter

LARGE_BYTES = 50_000
MAX_DESCRIPTION = 1200
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_BUNDLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundle")  # inside a regular (wheel) install


def bundled_home():
    """Folder that holds catalogue/bundled.json and skills/: LIBRARIAN_HOME, else the copy a regular install carries
    in the package, else the cloned repository (an editable install)."""
    env = os.environ.get("LIBRARIAN_HOME")
    if env:
        return env
    for d in (PACKAGE_BUNDLE, REPO_ROOT):
        if os.path.isfile(os.path.join(d, "catalogue", "bundled.json")):
            return d
    return REPO_ROOT


def default_user_dirs(cwd=None):
    """Skill folders the common agent CLIs use, user-level then project-level. Only existing ones are scanned."""
    home = os.path.expanduser("~")
    cwd = cwd or os.getcwd()
    return [os.path.join(home, ".claude", "skills"), os.path.join(home, ".codex", "skills"),
            os.path.join(home, ".agents", "skills"), os.path.join(cwd, ".claude", "skills"),
            os.path.join(cwd, ".codex", "skills"), os.path.join(cwd, ".agents", "skills")]


@dataclass
class Skill:
    name: str
    path: str
    description: str
    size: int
    origin: str  # "bundled" or "local"
    source: str = ""
    licence: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def large(self):
        return self.size > LARGE_BYTES


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


def read_skill_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _describe(text):
    meta = frontmatter.parse(text)
    desc = re.sub(r"\s+", " ", (meta.get("description") or "").strip())
    if not desc:  # no front matter description: first prose line of the body
        _, body = frontmatter.split(text)
        for line in body.splitlines():
            s = line.strip()
            if s and not s.startswith(("#", "---", "<!--")):
                desc = s
                break
    if len(desc) > MAX_DESCRIPTION:
        desc = desc[:MAX_DESCRIPTION].rstrip() + " ..."
    return meta.get("name", ""), desc


def load_bundled(home=None):
    home = home or bundled_home()
    meta_path = os.path.join(home, "catalogue", "bundled.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            entries = json.load(f)["skills"]
    except (OSError, ValueError, KeyError):
        return []
    out = []
    for e in entries:
        p = os.path.join(home, "skills", *e["id"].split("/"), "SKILL.md")
        try:
            text = read_skill_file(p)
        except OSError:
            continue
        _, desc = _describe(text)
        out.append(Skill(name=e["id"], path=os.path.abspath(p), description=desc, size=os.path.getsize(p),
                         origin="bundled", source="%s@%s" % (e["repo"], e["commit"][:12]), licence=e.get("licence", ""),
                         extra={"review": e.get("review", "")}))
    return out


def scan_dir(d):
    """Skills directly under d: d/<name>/SKILL.md (dot folders are skipped)."""
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if n.startswith("."):
            continue
        p = os.path.join(d, n, "SKILL.md")
        if not os.path.isfile(p):
            continue
        try:
            text = read_skill_file(p)
        except OSError:
            continue
        fm_name, desc = _describe(text)
        prov = provenance(os.path.join(d, n))
        out.append(Skill(name=fm_name.strip() or n, path=os.path.abspath(p), description=desc,
                         size=os.path.getsize(p), origin="local", source=os.path.abspath(d),
                         licence=str(prov.get("licence") or "") if prov else "",
                         extra={"provenance": prov} if prov else {}))
    return out


SOURCE_FILE = ".librarian-source.json"  # written by `librarian install` beside the skill's files


def provenance(skill_dir):
    """The install record of a skill folder, or None when it has none (or an unreadable one)."""
    try:
        with open(os.path.join(skill_dir, SOURCE_FILE), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("format") == "the-librarian/source-1" else None


def build(extra_dirs=(), user_skills=True, bundled=True, home=None):
    """Return the sorted, de-duplicated skill list: bundled first claim on a file, then user folders in order."""
    skills, seen_paths, seen_names = [], set(), set()
    groups = []
    if bundled:
        groups.append(load_bundled(home))
    dirs = list(extra_dirs)
    if user_skills:
        dirs += default_user_dirs()
    env_dirs = os.environ.get("LIBRARIAN_SKILLS_DIRS", "")
    dirs += [d for d in env_dirs.split(os.pathsep) if d.strip()]
    for d in dirs:
        groups.append(scan_dir(d))
    for group in groups:
        for s in group:
            key = _norm(s.path)
            if key in seen_paths:
                continue  # the same folder reached twice (for example through a link)
            seen_paths.add(key)
            base, n = s.name, 2
            while s.name.lower() in seen_names:
                s.name = "%s#%d" % (base, n)
                n += 1
            seen_names.add(s.name.lower())
            skills.append(s)
    skills.sort(key=lambda s: (s.name.lower(), s.path))
    return skills


def render(skills):
    """The catalogue text given to the model. Paths use forward slashes so they copy cleanly on every OS."""
    lines = ["# Skill catalogue: %d skills" % len(skills),
             "# Entry: name, SKILL.md path, (LARGE - read in parts with offset/limit) when the SKILL.md is over "
             "%d bytes, [bundled] or [local], then the description." % LARGE_BYTES, ""]
    for s in skills:
        flag = " (LARGE - read in parts with offset/limit)" if s.large else ""
        lines.append("- **%s** `%s`%s [%s]" % (s.name, s.path.replace("\\", "/"), flag, s.origin))
        lines.append("  " + (s.description or "(no description)"))
    return "\n".join(lines) + "\n"


def fingerprint(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def search(skills, words, limit=15):
    """Plain keyword search over names and descriptions: the offline fallback when no model is reachable."""
    terms = [w.lower().strip() for w in words if w.strip()]
    # a term matches at the start of a word: "form" finds "forms" and "form-filling", "forms" does not find "transforms"
    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(t)) for t in terms]
    scored = []
    for s in skills:
        hay_name, hay = s.name.lower(), s.description.lower()
        # distinct terms matter most (a name hit counts triple); repeats only break ties
        score = sum(3 if p.search(hay_name) else (1 if p.search(hay) else 0) for p in pats)
        score += 0.01 * sum(min(len(p.findall(hay)), 5) for p in pats)
        if score:
            scored.append((-score, s.name.lower(), s))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [s for _, _, s in scored[:limit]]
