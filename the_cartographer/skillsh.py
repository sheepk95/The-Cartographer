"""Read public skills.sh pages into a local index (stdlib only).

What is read, and only through web.Fetcher (whitelist, robots.txt, shared lock and daily caps):
  /robots.txt                     before anything else (re-read at least daily; every bulk index run reads it live)
  /sitemap.xml and its children   the skill names list (the skills sitemaps hold the most-installed skills)
  /<owner>/<repo>/<skill>         one skill page at a time, at least 1.3 s apart
  /<owner>/<repo>                 repo pages, only with `finder index --repo-pages` (the sitemap leaves out slugs
                                  with ":" or "&")

Each page gives: the JSON-LD name and description, the exact install count (anonymous CLI telemetry), the repo's
GitHub stars as the page rounds them ("36.0K", whole repo), the first-seen date, topic labels and the security audit
verdicts. Raw HTML is not kept.
"""
import html as htmlmod, json, os, re, secrets, time, unicodedata, urllib.parse
import xml.etree.ElementTree as ET

from . import web

PAGE_CAP = 1024 * 1024
SITEMAP_CAP = 16 * 1024 * 1024
DESCRIPTION_CHARS = 1200
SKILL_PATH_RE = re.compile(r"^/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.:&%-]{1,160})$")
NOT_SKILL_OWNERS = {"site", "topic", "official", "audits", "picks", "hot", "trending", "docs", "api", "search",
                    "internal", "debug-security", "terms", "privacy"}
LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
TOPIC_RE = re.compile(r'href="/topic/([a-z0-9-]{1,60})"')
AUDIT_A_RE = re.compile(r'<a\b[^>]*href="(/[^"]+/security/([a-z0-9-]{1,40}))"[^>]*>(.*?)</a>', re.S)
SPAN_RE = re.compile(r"<span\b[^>]*>([^<]*)</span>")
GITHUB_RE = re.compile(r'href="https://github\.com/([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})/?"')
ROW_RE = re.compile(r'<a\b[^>]*href="(/[^"]+)"[^>]*>\s*<div[^>]*>\s*<h3[^>]*>([^<]*)</h3>', re.S)
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                                      "Dec"], 1)}
INSTALLS_NOTE = "skills.sh install count: anonymous CLI telemetry, inflated by clones and automated installs"
STARS_NOTE = "GitHub stars of the whole repository, rounded by skills.sh"


UNSAFE_SLUG_RE = re.compile(r"[\x00-\x20\x7f<>\"'`\\/]")


def skill_id(url):
    """'owner/repo/skill' for a skills.sh skill page URL, else None. /site/<domain> mirrors are not skills, and nor is
    a slug that decodes to a space, a control character, a slash or a quote or angle bracket (it would be printed and
    quoted to the judge as an id)."""
    p = urllib.parse.urlsplit(web.normalise(url))
    if p.hostname != "www.skills.sh":
        return None
    m = SKILL_PATH_RE.match(p.path)
    if not m or m.group(1).lower() in NOT_SKILL_OWNERS:
        return None
    slug = urllib.parse.unquote(m.group(3))
    if UNSAFE_SLUG_RE.search(slug) or slug in (".", "..") or any(unicodedata.category(c) == "Cf" for c in slug):
        return None
    return "%s/%s/%s" % (m.group(1), m.group(2), slug)


def page_url(sid):
    o, r, s = sid.split("/", 2)
    return "%s/%s/%s/%s" % (web.SKILLS_SH, o, r, urllib.parse.quote(s, safe=":&-._"))


# ---------------------------------------------------------------- sitemaps

def parse_sitemap(xml_bytes):
    """(child sitemap URLs, page URLs) of a sitemap index or url set, in document order."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise web.WebError("unreadable sitemap: %s" % e)
    kids, locs = [], []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("sitemap", "url"):
            loc = next(((c.text or "").strip() for c in el if c.tag.rsplit("}", 1)[-1] == "loc"), "")
            if loc:
                (kids if tag == "sitemap" else locs).append(loc)
    return kids, locs


def skill_sitemaps(index_kids):
    """The child sitemaps that list skill pages, in order (sitemap-skills-1, -2, ...)."""
    def key(u):
        m = re.search(r"(\d+)\.xml$", u)
        return int(m.group(1)) if m else 0
    return sorted([u for u in index_kids if re.search(r"/sitemap-skills[^/]*\.xml$", u)], key=key)


# ---------------------------------------------------------------- page parsing

def parse_abbrev(s):
    """'4.0M' -> 4000000, '36.0K' -> 36000, '11' -> 11; None when unreadable."""
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB]?)", (s or "").strip().replace(",", ""))
    if not m:
        return None
    return int(round(float(m.group(1)) * {"": 1, "K": 1000, "M": 1000000, "B": 1000000000}[m.group(2)]))


def parse_date(s):
    m = re.fullmatch(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", (s or "").strip())
    if not m or m.group(1) not in MONTHS:
        return None
    return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))


def _text(h):
    return " ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", h or "")).split())


def visible_lines(h):
    i, j = h.find("<main"), h.find("</main>")
    seg = h[i:j] if (i >= 0 and j > i) else h
    seg = re.sub(r"<(script|style|svg)\b[^>]*>.*?</\1>", " ", seg, flags=re.S)
    seg = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/a|/span|/dt|/dd|/td|/th)\b[^>]*>", "\n", seg)
    seg = htmlmod.unescape(re.sub(r"<[^>]+>", "", seg))
    return [" ".join(x.split()) for x in seg.splitlines() if x.strip()]


def _after(lines, label):
    for k, ln in enumerate(lines):
        if ln == label and k + 1 < len(lines):
            return lines[k + 1]
    return None


def clean(s, n):
    """Third-party text made safe to print and to quote as data: one line, control characters dropped, cut by
    characters."""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", " ", str(s or ""))
    # format characters (bidi overrides, zero-width spaces and joiners) can hide or reorder text on a terminal
    s = "".join(c for c in s if unicodedata.category(c) != "Cf")
    return web.cut(" ".join(s.split()), n)


def parse_skill_page(h):
    """The fields the finder keeps from one skill page. Missing fields come back as None or []."""
    d = {"name": None, "description": None, "installs": None, "publisher": None}
    for m in LD_RE.finditer(h):
        try:
            b = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(b, dict) and b.get("@type") == "SoftwareApplication":
            d["name"] = clean(b.get("name"), 120) or None
            d["description"] = clean(b.get("description"), DESCRIPTION_CHARS) or None
            pub = b.get("publisher")
            d["publisher"] = clean(pub.get("name") if isinstance(pub, dict) else pub, 100) or None
            stats = b.get("interactionStatistic")  # schema.org allows one object or a list of them
            stats = [x for x in (stats if isinstance(stats, list) else [stats]) if isinstance(x, dict)]
            n = next((x.get("userInteractionCount") for x in stats if "userInteractionCount" in x), None)
            d["installs"] = n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None
            break
    lines = visible_lines(h)
    if d["installs"] is None:  # the JSON-LD count is exact; the page's "4.0M" is a fallback
        d["installs"] = parse_abbrev(_after(lines, "Installs"))
    gh = GITHUB_RE.search(h)
    d["repo"] = "%s/%s" % (gh.group(1), gh.group(2).rstrip(".")) if gh else None
    d["repo_url"] = "https://github.com/%s" % d["repo"] if d["repo"] else None
    d["verified"] = 'title="Verified organization on GitHub"' in h
    stars = _after(lines, "GitHub Stars")
    d["stars_text"] = clean(stars, 12) or None
    d["stars"] = parse_abbrev(stars)
    d["first_seen"] = parse_date(_after(lines, "First Seen"))
    cut_at = h.find(">Installation<")
    topics = []
    for t in TOPIC_RE.findall(h[:cut_at] if cut_at > 0 else ""):
        if t not in topics:
            topics.append(t)
    d["topics"] = topics[:12]
    audits, seen = [], set()
    for m in AUDIT_A_RE.finditer(h):
        slug, spans = m.group(2), SPAN_RE.findall(m.group(3))
        if slug in seen or len(spans) < 2:
            continue
        seen.add(slug)
        audits.append({"provider": clean(htmlmod.unescape(spans[0]), 40), "slug": slug,
                       "status": clean(htmlmod.unescape(spans[1]), 12)})
    d["audits"] = audits
    return d


def parse_repo_page(h):
    """Skill page paths listed on a repo page (hrefs are HTML-escaped there: '&amp;' is '&')."""
    out = []
    for href, _name in ROW_RE.findall(h):
        path = htmlmod.unescape(href)
        if SKILL_PATH_RE.match(path) and path not in out:
            out.append(path)
    return out


# ---------------------------------------------------------------- the cache and the index

def cache_dir():
    """CARTOGRAPHER_CACHE, else %LOCALAPPDATA%/the-cartographer on Windows, else $XDG_CACHE_HOME or ~/.cache."""
    env = os.environ.get("CARTOGRAPHER_CACHE")
    if env:
        return os.path.abspath(env)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], "the-cartographer")
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "the-cartographer")


def finder_dir(root=None):
    return os.path.join(root or cache_dir(), "finder")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d-%s" % (path, os.getpid(), secrets.token_hex(4))  # threads of one process (MCP) too
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
    _replace(tmp, path)


def _replace(tmp, path):
    for i in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: a reader holds the file for a moment
            time.sleep(0.05 * (i + 1))
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_pages(path):
    """{url: last record} from pages.jsonl; a torn last line (Ctrl-C mid-write) is skipped."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("url"):
                    out[rec["url"]] = rec
    except OSError:
        pass
    return out


def append_page(fdir, rec):
    os.makedirs(fdir, exist_ok=True)
    with open(os.path.join(fdir, "pages.jsonl"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()


def compact_pages(fdir):
    """Rewrite pages.jsonl with one record per page when re-fetches have doubled it."""
    path = os.path.join(fdir, "pages.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            lines = sum(1 for _ in f)
    except OSError:
        return
    pages = read_pages(path)
    if lines <= 2 * len(pages) + 100:
        return
    tmp = path + ".tmp-%d-%s" % (os.getpid(), secrets.token_hex(4))
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for rec in pages.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _replace(tmp, path)


DATA_TYPES = {"name": str, "description": str, "installs": int, "publisher": str, "repo": str, "repo_url": str,
              "verified": bool, "stars_text": str, "stars": int, "first_seen": str, "topics": list, "audits": list}


def _sane_data(data):
    """The page fields with the types parse_skill_page gives them (None allowed), else None: a cache line edited by
    hand or written by another version must not crash a search."""
    for k, t in DATA_TYPES.items():
        v = data.get(k)
        if v is None:
            continue
        if not isinstance(v, t) or (t is int and isinstance(v, bool)):
            return None
    if not all(isinstance(a, dict) and isinstance(a.get("provider"), str) and isinstance(a.get("status"), str)
               for a in data.get("audits") or []):
        return None
    if not all(isinstance(t, str) for t in data.get("topics") or []):
        return None
    return {k: data.get(k) for k in DATA_TYPES}


def row_of(rec):
    """A finder row from a pages.jsonl record of a fetched skill page, else None."""
    if rec.get("status") != 200 or not isinstance(rec.get("data"), dict):
        return None
    sid = skill_id(rec.get("url"))
    data = _sane_data(rec["data"])
    if not sid or data is None or not web._num(rec.get("epoch")):
        return None
    return dict(data, id=sid, url=rec["url"], fetched_at=rec.get("fetched_at"), epoch=rec["epoch"],
                etag=rec.get("etag") if isinstance(rec.get("etag"), str) else None,
                last_modified=rec.get("last_modified") if isinstance(rec.get("last_modified"), str) else None)


def page_rows(fdir):
    """{skill id: row} of every skill page this cache holds (from the bulk index and from live searches)."""
    out = {}
    for rec in read_pages(os.path.join(fdir, "pages.jsonl")).values():
        r = row_of(rec)
        if r:
            out[r["id"]] = r
    return out


def fetcher_for(fdir, gap=web.DEFAULT_GAP, out=None, opener=None, clock=None, sleep=None):
    """A Fetcher whose lock and state are shared with every other cartographer process using this cache."""
    kw = {}
    if clock:
        kw["clock"] = clock
    if sleep:
        kw["sleep"] = sleep
    st = web.NetState(fdir, **kw)
    return web.Fetcher(gap=gap, opener=opener, state=st, log=(lambda m: out("  " + m)) if out else None, **kw)


def validators(old):
    """Conditional request headers from an earlier fetch of the same page (a row or a record), so an unchanged page
    costs the site a 304 and no body."""
    h = {}
    if isinstance(old, dict) and isinstance(old.get("etag"), str) and old["etag"]:
        h["If-None-Match"] = old["etag"]
    if isinstance(old, dict) and isinstance(old.get("last_modified"), str) and old["last_modified"]:
        h["If-Modified-Since"] = old["last_modified"]
    return h


def fetch_one(f, url, kind="page", old=None):
    """GET one skill page; the record that goes into pages.jsonl. Blocked and Refused propagate (they stop a run).
    old: the cached row of this page (row_of), if any; its validators make the request conditional, and a 304 keeps
    its data.
    A 200 page with none of the fields the finder reads is recorded as "unreadable": skills.sh has changed its page
    layout, and that must be said, not read as a skill with no installs."""
    t = f.clock()
    rec = {"url": url, "kind": "skill", "fetched_at": web.utc(t), "epoch": t}
    old_data = _sane_data(old) if isinstance(old, dict) else None
    try:
        status, hdrs, body = f.get(url, PAGE_CAP, kind=kind, headers=validators(old) if old_data else None)
    except web.Blocked:
        raise
    except web.WebError as e:
        rec.update(status="error", error=str(e)[:200])
        return rec
    if status == 304 and old_data:
        rec.update(status=200, data=old_data, revalidated=True, etag=old.get("etag"),
                   last_modified=old.get("last_modified"))
        return rec
    rec["status"] = status
    if status == 200:
        for k, h in (("etag", "etag"), ("last_modified", "last-modified")):
            if isinstance(hdrs.get(h), str) and 0 < len(hdrs[h]) <= 200:
                rec[k] = hdrs[h]
        try:
            data = parse_skill_page(body.decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001  a page we cannot parse is recorded, not fatal
            rec.update(status="parse-error", error=repr(e)[:200])
            return rec
        if not (data.get("name") or data.get("installs") is not None or data.get("repo")):
            rec.update(status="unreadable", error="no name, install count or repository found on the page")
        else:
            rec["data"] = data
    return rec


# ---------------------------------------------------------------- the names list (sitemaps, cached about a day)

NAMES_MAX_AGE = 24 * 3600


def names_path(fdir):
    return os.path.join(fdir, "names.json")


def load_names(fdir):
    d = read_json(names_path(fdir))
    return d if isinstance(d, dict) and isinstance(d.get("ids"), list) else None


def sitemap_ids(f, out=print):
    """Skill ids from the skills sitemaps, in sitemap order (most installed first), /site/ mirrors dropped."""
    for path in ("/sitemap.xml",):
        if not web.robots_allows(f.robots, path):
            raise web.Refused("robots.txt disallows %s" % path)
    status, _, body = f.get(web.SKILLS_SH + "/sitemap.xml", SITEMAP_CAP, kind="list", accept="application/xml")
    if status != 200:
        raise web.WebError("sitemap.xml answered HTTP %s" % status)
    kids, locs = parse_sitemap(body)
    maps = skill_sitemaps(kids)
    if not maps:
        raise web.WebError("sitemap.xml lists no sitemap-skills file (has the site changed?)")
    urls = list(locs)
    for child in maps[:10]:
        st, _, b = f.get(child, SITEMAP_CAP, kind="list", accept="application/xml")
        if st != 200:
            raise web.WebError("%s answered HTTP %s" % (child, st))
        urls += parse_sitemap(b)[1]
    ids, seen = [], set()
    for u in urls:
        sid = skill_id(u)
        if sid and sid.lower() not in seen:
            seen.add(sid.lower())
            ids.append(sid)
    if not ids:  # an empty list would read as "no skill fits"; it means the site has changed
        raise web.WebError("the skills sitemaps list no skill pages (has the site changed?)")
    return ids, maps


def refresh_names(f, fdir, max_age=NAMES_MAX_AGE, out=print, force=False):
    """names.json, rebuilt from the sitemaps when older than max_age (robots.txt is read first). Returns the dict."""
    old = load_names(fdir)
    if old and not force and time.time() - float(old.get("epoch") or 0) < max_age:
        return old
    if f.robots is None:
        f.load_robots(max_age=max_age)
    ids, maps = sitemap_ids(f, out)
    d = {"format": "the-cartographer/finder-names-1", "built_at": web.utc(), "epoch": time.time(),
         "sitemaps": maps, "ids": ids}
    write_json(names_path(fdir), d)
    return d


# ---------------------------------------------------------------- the optional bulk index

def estimate(n, gap):
    """Rough wall time for n page fetches: the gap plus about half a second per response."""
    s = n * (gap + 0.5)
    return "%d s" % s if s < 120 else ("%d min" % round(s / 60) if s < 7200 else "%.1f h" % (s / 3600))


LIVE_MARK = "live.active"


def live_active(fdir, fresh=120):
    p = os.path.join(fdir, LIVE_MARK)
    try:
        return time.time() - os.path.getmtime(p) < fresh
    except OSError:
        return False


def mark_live(fdir, on=True):
    p = os.path.join(fdir, LIVE_MARK)
    try:
        if on:
            os.makedirs(fdir, exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(str(os.getpid()))
        else:
            os.remove(p)
    except OSError:
        pass


def run_index(top=2000, gap=web.BULK_MIN_GAP, root=None, fetcher=None, out=print, repo_pages=False,
              max_failures=25, refresh=False, wait=time.sleep):
    """The optional bulk index: robots.txt (read live), the sitemaps, then up to `top` skill pages into pages.jsonl.

    Resumable: pages already fetched (200 or 404) are skipped unless refresh, and a refresh asks for each page with
    its saved validators, so an unchanged page costs a 304. It goes at least BULK_MIN_GAP seconds apart, counts every
    page (repo pages too) against its own daily cap, gives way to live searches (it waits while one is running), stops
    on HTTP 429 or 403 or at the cap, and Ctrl-C stops it cleanly. Returns an exit code.
    """
    fdir = finder_dir(root)
    os.makedirs(fdir, exist_ok=True)
    f = fetcher or fetcher_for(fdir, max(float(gap), web.BULK_MIN_GAP), out)
    f.gap = max(float(f.gap), web.BULK_MIN_GAP)
    rules = f.load_robots()
    out("robots.txt read live: %d rules for us; disallowed: %s" % (len(rules), ", ".join(
        f.robots_info["disallow"]) or "nothing"))
    names = refresh_names(f, fdir, max_age=0, out=out, force=True)
    wanted = [page_url(i) for i in names["ids"]][:max(0, int(top))]
    pages_path = os.path.join(fdir, "pages.jsonl")
    cached = read_pages(pages_path)
    done = set() if refresh else {u for u, r in cached.items() if r.get("status") in (200, 404)}
    todo = [u for u in wanted if u not in done]
    out("sitemaps list %d skill pages; taking the first %d (sitemap order, most installed first); %d already "
        "fetched, %d to fetch, about %s at %.1f s apart" % (len(names["ids"]), len(wanted), len(wanted) - len(todo),
                                                          len(todo), estimate(len(todo), f.gap), f.gap))
    n = fails = consec = 0
    reason = "complete"
    seen = set(wanted)
    repos_done = set()
    queue = list(todo)
    try:
        while queue:
            while live_active(fdir):  # a live search is running: let it go first
                wait(1.0)
            url = queue.pop(0)
            if not web.robots_allows(f.robots, urllib.parse.urlsplit(url).path):
                continue
            old = row_of(cached[url]) if url in cached else None
            rec = fetch_one(f, url, kind="bulk", old=old)  # its own daily cap, apart from live finds
            append_page(fdir, rec)
            n += 1
            if rec["status"] in (200, 404):
                consec = 0
            else:
                fails += 1
                consec += 1
                if consec >= max_failures:
                    reason = "%d failures in a row (blocked or down?)" % consec
                    break
            if repo_pages and rec["status"] == 200:
                o, r = skill_id(url).split("/")[:2]
                if (o, r) not in repos_done:
                    repos_done.add((o, r))
                    for extra in fetch_repo_extras(f, o, r, seen):
                        seen.add(extra)
                        queue.append(extra)
            if n % 100 == 0:
                out("  %d fetched, %d left, %d failed" % (n, len(queue), fails))
    except KeyboardInterrupt:
        reason = "stopped by Ctrl-C (run again to resume)"
    except web.Blocked as e:
        reason = "stopped: %s (run again later to resume)" % e
    except (web.WebError, web.Refused) as e:
        reason = "stopped: %s (run again to resume)" % e
    compact_pages(fdir)
    out("fetched %d pages (%d failed): %s. The cache now holds %d skill pages (%s)" % (
        n, fails, reason, len(page_rows(fdir)), pages_path))
    return 0 if reason == "complete" else 3


def fetch_repo_extras(f, owner, repo, seen):
    """Skill pages on a repo page that the sitemap leaves out (slugs with ':' or '&')."""
    try:
        st, _, body = f.get("%s/%s/%s" % (web.SKILLS_SH, owner, repo), PAGE_CAP, kind="bulk")
    except (web.Blocked, web.Refused):
        raise  # blocked, or the bulk cap is spent: the run stops and says why
    except web.WebError:
        return []
    if st != 200:
        return []
    out = []
    for path in parse_repo_page(body.decode("utf-8", "replace")):
        u = web.normalise(web.SKILLS_SH + path)
        if u not in seen and skill_id(u) and re.search(r"[:&]", urllib.parse.unquote(path)):
            out.append(u)
    return out


def summary(root=None):
    """What the finder cache holds, for `cartographer doctor` and `finder status`."""
    fdir = finder_dir(root)
    names = load_names(fdir)
    pages_path = os.path.join(fdir, "pages.jsonl")
    st = web.NetState(fdir).read() if os.path.isdir(fdir) else {}
    day = st.get("day") or {}
    out = {"dir": fdir, "names": len(names["ids"]) if names else 0,
           "names_age_h": round((time.time() - float(names.get("epoch") or 0)) / 3600, 1) if names else None,
           "pages": len(page_rows(fdir)) if os.path.exists(pages_path) else 0,
           "pages_bytes": os.path.getsize(pages_path) if os.path.exists(pages_path) else 0,
           "today": {"date": day.get("date"), "pages": day.get("page", 0), "lists": day.get("list", 0),
                     "bulk": day.get("bulk", 0)},
           "blocked": {h: b for h, b in (st.get("blocked") or {}).items() if time.time() < float(b.get("until") or 0)},
           "robots_read_at": (st.get("robots") or {}).get("read_at")}
    return out
