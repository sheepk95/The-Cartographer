"""The finder's only door to the network: a URL whitelist, robots.txt, and a polite one-at-a-time fetcher (stdlib).

Every request the finder or the installer makes goes through `Fetcher.get`, which refuses any URL that is not on the
whitelist (also after a redirect) and, for skills.sh, any path robots.txt disallows. Requests from every librarian
process share one lock and one state file, so two commands never hit a host at once, the gap holds across processes,
and a 429 or 403 stops every fetch until the host's wait is over. Tests pass their own `opener`, so no test touches
the network.
"""
import http.client, json, os, re, secrets, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import PROJECT_URL, __version__

# Generic on purpose: the tool, its version and where to read about it or report a problem; nothing about the user.
USER_AGENT = ("the-librarian/%s (+%s; skill finder; reads robots.txt; one request at a time, at least 1.3 s apart)"
              % (__version__, PROJECT_URL))
ROBOTS_TOKEN = "the-librarian"
SKILLS_SH = "https://www.skills.sh"
MIN_GAP = 1.3          # seconds between requests to one host, across every librarian process; never lower
DEFAULT_GAP = 1.5
BULK_MIN_GAP = 3.0     # the optional bulk index goes slower than a live search
BLOCK_403_S = 6 * 3600  # a 403 stops every request to that host for six hours
MAX_BLOCK_S = 30 * 86400  # a longer Retry-After is read as 30 days (a date past year 3000 breaks gmtime on Windows)
LOCK_STALE_S = 120
NO_NETWORK_ENV = "LIBRARIAN_NO_NETWORK"  # set (to anything) and no request leaves this machine
DAILY = {"page": ("LIBRARIAN_FINDER_DAILY_PAGES", 300),   # live skill page fetches per UTC day
         "list": ("LIBRARIAN_FINDER_DAILY_LISTS", 12),    # robots.txt and sitemap requests per UTC day
         "bulk": ("LIBRARIAN_FINDER_DAILY_BULK", 2000)}   # bulk index pages (skill and repo pages) per UTC day
CAP_NAMES = {"page": "skill page", "list": "robots and sitemap", "bulk": "bulk index"}

_SEG = r"[A-Za-z0-9_.-]{1,100}"
# Each allowed host with the path shapes the finder needs. Anything else is refused before a socket opens.
WHITELIST = {
    "www.skills.sh": [re.compile(r"^/robots\.txt$"), re.compile(r"^/sitemap[A-Za-z0-9_.-]*\.xml$"),
                      re.compile(r"^/%s/%s$" % (_SEG, _SEG)),                       # repo page
                      re.compile(r"^/%s/%s/[A-Za-z0-9_.:&%%-]{1,160}$" % (_SEG, _SEG))],  # skill page
    "api.github.com": [re.compile(r"^/repos/%s/%s/commits/[A-Za-z0-9_.-]{1,100}$" % (_SEG, _SEG)),
                       re.compile(r"^/repositories/[0-9]{1,20}/commits/[A-Za-z0-9_.-]{1,100}$")],  # renamed repo
    "codeload.github.com": [re.compile(r"^/%s/%s/tar\.gz/[0-9a-f]{40}$" % (_SEG, _SEG))],
}


class WebError(RuntimeError):
    """A transient failure (network, server error, rate limit). Never a verdict on the skill."""


class Blocked(WebError):
    """The host said stop (HTTP 429 or 403). Every request to it is refused until `until`."""

    def __init__(self, msg, until=0):
        super().__init__(msg)
        self.until = until


class TooLarge(WebError):
    """The answer was bigger than the cap the caller set (not transient: the same request will be as big again)."""


class Refused(RuntimeError):
    """A request the rules forbid (not whitelisted, disallowed by robots.txt, or over a daily cap)."""


def normalise(url):
    """skills.sh links come with and without www; the whitelist knows one host."""
    p = urllib.parse.urlsplit(url or "")
    host = (p.hostname or "").lower()
    if host == "skills.sh":
        host = "www.skills.sh"
    return urllib.parse.urlunsplit((p.scheme.lower(), host, p.path, p.query, ""))


def allowed_url(url):
    """True only for https URLs on the whitelist: no query strings, no userinfo, no ports, no other hosts."""
    p = urllib.parse.urlsplit(url or "")
    try:
        port = p.port
    except ValueError:
        return False
    if p.scheme != "https" or p.query or p.fragment or p.username or p.password or port not in (None, 443):
        return False
    # "." and ".." segments (also percent-encoded) would let a server resolve the path to one robots.txt forbids
    if any(urllib.parse.unquote(s) in (".", "..") for s in p.path.split("/")):
        return False
    pats = WHITELIST.get((p.hostname or "").lower())
    return bool(pats) and any(rx.match(p.path) for rx in pats)


# ---------------------------------------------------------------- robots.txt (RFC 9309: groups, longest match wins)

def parse_robots(text, token=ROBOTS_TOKEN):
    """Rules [(allow?, pattern)] for our token's group, else the * group."""
    groups, cur, in_rules = [], None, False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        k = k.lower()
        if k == "user-agent":
            if cur is None or in_rules:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
                in_rules = False
            cur["agents"].append(v.lower())
        elif k in ("allow", "disallow") and cur is not None:
            in_rules = True
            if v:
                cur["rules"].append((k == "allow", v))
    mine = [g for g in groups if any(a not in ("", "*") and a == token.lower() for a in g["agents"])]
    star = [g for g in groups if "*" in g["agents"]]
    return [r for g in (mine or star) for r in g["rules"]]


def _pattern(p):
    rx = "".join(".*" if c == "*" else re.escape(c) for c in p.rstrip("$"))
    return re.compile("^" + rx + ("$" if p.endswith("$") else ""))


def robots_allows(rules, path):
    """Longest matching rule wins; on a tie Allow wins; no match means allowed."""
    best = None
    for allow, pat in rules:
        if _pattern(pat).match(path):
            n = len(pat)
            if best is None or n > best[0] or (n == best[0] and allow):
                best = (n, allow)
    return True if best is None else best[1]


# ---------------------------------------------------------------- shared state: one lock and one file per cache

def _gm(t):
    # clamped to 1970..2999: Windows' gmtime refuses dates outside that range (a bad Retry-After must not crash)
    return time.gmtime(min(max(0.0, float(time.time() if t is None else t)), 32503680000.0 - 1))


def utc(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", _gm(t))


def today(t=None):
    return time.strftime("%Y-%m-%d", _gm(t))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sane_state(d):
    """net.json with every part of the wrong type dropped (a hand-edited or foreign file must not crash a fetch)."""
    if not isinstance(d, dict):
        return {}
    out = {}
    if isinstance(d.get("day"), dict):
        out["day"] = {k: v for k, v in d["day"].items() if (k == "date" and isinstance(v, str)) or _num(v)}
    if isinstance(d.get("last"), dict):
        out["last"] = {h: t for h, t in d["last"].items() if _num(t)}
    if isinstance(d.get("blocked"), dict):
        out["blocked"] = {h: b for h, b in d["blocked"].items() if isinstance(b, dict) and _num(b.get("until"))}
    rb = d.get("robots")
    if isinstance(rb, dict) and _num(rb.get("epoch")) and isinstance(rb.get("rules"), list) and all(
            isinstance(r, list) and len(r) == 2 and isinstance(r[1], str) for r in rb["rules"]):
        out["robots"] = rb
    return out


class NetState:
    """net.json (last request per host, blocks, today's counts, robots) under fetch.lock. With no folder (tests) the
    state lives in memory."""

    def __init__(self, folder=None, clock=time.time, sleep=time.sleep):
        self.folder = folder
        self.clock, self.sleep = clock, sleep
        self.mem = {}
        self._held = False

    def path(self, name):
        return os.path.join(self.folder, name)

    def read(self):
        if not self.folder:
            return _sane_state(json.loads(json.dumps(self.mem)))
        try:
            with open(self.path("net.json"), encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return {}
        return _sane_state(d)

    def write(self, d):
        if not self.folder:
            self.mem = json.loads(json.dumps(d))
            return
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.path("net.json.tmp-%d-%s" % (os.getpid(), secrets.token_hex(4)))  # threads of one process too
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(d, f, indent=1)
        for i in range(10):
            try:
                os.replace(tmp, self.path("net.json"))
                return
            except PermissionError:  # Windows: a reader holds the file for a moment
                time.sleep(0.05 * (i + 1))
        os.replace(tmp, self.path("net.json"))

    def lock(self, wait=90.0):
        """One request at a time across processes. A lock older than LOCK_STALE_S is a crashed holder's."""
        if not self.folder:
            self._held = True
            return
        os.makedirs(self.folder, exist_ok=True)
        p, t0 = self.path("fetch.lock"), time.time()
        while True:
            try:
                fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                self._token = "%d %s" % (os.getpid(), secrets.token_hex(8))
                os.write(fd, self._token.encode())
                os.close(fd)
                self._held = True
                return
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(p) > LOCK_STALE_S:
                        os.remove(p)
                        continue
                except OSError:
                    continue
                if time.time() - t0 > wait:
                    raise WebError("another librarian process holds the fetch lock (%s)" % p)
                time.sleep(0.2)

    def unlock(self):
        """Remove the lock only while it is still ours: a holder slower than LOCK_STALE_S may have lost it to another
        process, and must not delete that process's lock."""
        if self.folder and self._held:
            p = self.path("fetch.lock")
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    mine = f.read() == getattr(self, "_token", None)
                if mine:
                    os.remove(p)
            except OSError:
                pass
        self._held = False

    def count(self, d, kind):
        day = d.setdefault("day", {})
        if day.get("date") != today(self.clock()):
            day.clear()
            day["date"] = today(self.clock())
        return day.get(kind, 0)

    def take(self, kind):
        """Spend one of today's requests of this kind; Refused when the cap is reached. Call while locked.
        A kind without a cap in DAILY is only counted, so `librarian finder status` can show it."""
        if not kind:
            return
        if kind not in DAILY:
            d = self.read()
            d["day"][kind] = self.count(d, kind) + 1
            self.write(d)
            return
        env, default = DAILY[kind]
        try:
            limit = int(os.environ.get(env) or default)
        except ValueError:
            limit = default
        d = self.read()
        n = self.count(d, kind)
        if n >= limit:
            raise Refused("today's %s cap is reached (%d; set %s to change it); try again tomorrow (UTC)"
                          % (CAP_NAMES.get(kind, kind), limit, env))
        d["day"][kind] = n + 1
        self.write(d)


# ---------------------------------------------------------------- the fetcher

class _NoBlindRedirects(urllib.request.HTTPRedirectHandler):
    """Every redirect target passes the same check as a first request: the whitelist, and robots.txt when the
    Fetcher hands its check in."""

    def __init__(self, check=None):
        super().__init__()
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urljoin(req.full_url, newurl)
        if not allowed_url(target):
            raise Refused("redirect to a URL that is not on the whitelist: %s" % target[:200])
        if self.check:
            self.check(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def default_opener(url, headers, cap, timeout=30, check=None):
    """(status, headers dict, body bytes up to cap + 1). HTTP errors come back as a status, not an exception.
    An Authorization header is sent to `url` only: urllib would copy it onto a redirect to another host."""
    if os.environ.get(NO_NETWORK_ENV):  # a switch for offline runs and test suites; refused, so never retried
        raise Refused("the network is switched off (%s is set)" % NO_NETWORK_ENV)
    op = urllib.request.build_opener(_NoBlindRedirects(check))
    plain = {k: v for k, v in headers.items() if k.lower() != "authorization"}
    req = urllib.request.Request(url, headers=plain)
    for k, v in headers.items():
        if k.lower() == "authorization":
            req.add_unredirected_header("Authorization", v)
    try:
        with op.open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(cap + 1)
    except urllib.error.HTTPError as e:
        hdrs = {k.lower(): v for k, v in (e.headers or {}).items()}
        try:
            body = e.read(4096)
        except Exception:  # noqa: BLE001
            body = b""
        return e.code, hdrs, body
    except Refused:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        # HTTPException: a cut-off body (IncompleteRead) or a garbled status line is a network failure too
        raise WebError("cannot reach %s: %s" % (urllib.parse.urlsplit(url).hostname, getattr(e, "reason", e)))


def retry_after(value, now=None):
    """Seconds from a Retry-After header (seconds or an HTTP date), at least 60 and at most MAX_BLOCK_S; 60 when
    missing or unreadable."""
    if not value:
        return 60
    try:
        return min(MAX_BLOCK_S, max(60, int(str(value).strip())))
    except ValueError:
        try:
            dt = parsedate_to_datetime(str(value))
            if dt.tzinfo is None:  # "-0000" or no zone: RFC 9110 dates are GMT
                dt = dt.replace(tzinfo=timezone.utc)
            return min(MAX_BLOCK_S, max(60, int((dt - (now or datetime.now(timezone.utc))).total_seconds())))
        except (TypeError, ValueError, IndexError, OverflowError):
            return 60


class Fetcher:
    """One request at a time, at least `gap` seconds apart, whitelist and robots enforced on every call.

    opener(url, headers, cap) -> (status, headers, body) is injectable; so are sleep and clock, so tests run at once.
    state: a NetState (shared through the cache folder in real use, in memory in tests).
    """

    def __init__(self, gap=DEFAULT_GAP, opener=None, state=None, sleep=time.sleep, clock=time.time, log=None,
                 retries=2, extra_headers=None):
        self.gap = max(MIN_GAP, float(gap))
        # the real opener gets this Fetcher's redirect check, so a redirect obeys robots.txt as well as the whitelist
        self.opener = opener or (lambda u, h, c: default_opener(u, h, c, check=self.redirect_check))
        self.state = state or NetState(None, clock=clock, sleep=sleep)
        self.sleep, self.clock = sleep, clock
        self.log = log or (lambda msg: None)
        self.retries = retries
        self.extra_headers = extra_headers or {}
        self.robots = None          # rules for www.skills.sh, read by load_robots()
        self.robots_info = {}
        self.requests = 0
        self._hop_kind = None       # the cap a redirect hop of the request in flight spends

    def load_robots(self, max_age=0):
        """Read skills.sh/robots.txt (live; a copy from this cache no older than max_age seconds is reused). 404 means
        no rules (RFC 9309); any other failure means no crawling at all."""
        d = self.state.read()
        rb = d.get("robots") or {}
        if max_age and rb.get("epoch") and self.clock() - float(rb["epoch"]) < max_age and "rules" in rb:
            self.robots = [(bool(a), str(p)) for a, p in rb["rules"]]
            self.robots_info = {k: v for k, v in rb.items() if k != "rules"}
            return self.robots
        url = SKILLS_SH + "/robots.txt"
        status, _, body = self._request(url, 256 * 1024, robots_check=False, kind="list", accept="text/plain")
        if status in (404, 410):
            rules = []
        elif status == 200:
            rules = parse_robots(body.decode("utf-8", "replace"))
        else:
            raise WebError("robots.txt answered HTTP %s, so the finder will not crawl" % status)
        self.robots = rules
        self.robots_info = {"url": url, "status": status, "read_at": utc(self.clock()), "epoch": self.clock(),
                            "disallow": [p for a, p in rules if not a]}
        d = self.state.read()
        d["robots"] = dict(self.robots_info, rules=[[a, p] for a, p in rules])
        self.state.write(d)
        return rules

    def check(self, url):
        if not allowed_url(url):
            raise Refused("not on the finder's URL whitelist: %s" % url[:200])
        p = urllib.parse.urlsplit(url)
        if p.hostname == "www.skills.sh":
            if self.robots is None:
                raise Refused("robots.txt has not been read in this run")
            if not robots_allows(self.robots, p.path):
                raise Refused("robots.txt disallows %s" % p.path)

    def redirect_check(self, url):
        """A redirect target: on the whitelist, and on skills.sh allowed by robots.txt (once it has been read). A hop
        is a request too (urllib follows up to 10): on skills.sh it spends the daily cap of the request it belongs to,
        and every hop waits the gap. Called by the real opener while the request holds the lock."""
        if not allowed_url(url):
            raise Refused("redirect to a URL that is not on the whitelist: %s" % url[:200])
        p = urllib.parse.urlsplit(url)
        if p.hostname == "www.skills.sh" and self.robots is not None and not robots_allows(self.robots, p.path):
            raise Refused("redirect to %s, which robots.txt disallows" % p.path[:200])
        if p.hostname == "www.skills.sh":
            self.state.take(self._hop_kind or "page")
        self.sleep(self.gap)

    def _request(self, url, cap, robots_check=True, kind=None, accept="text/html", headers=None):
        url = normalise(url)
        if robots_check:
            self.check(url)
        elif not allowed_url(url):
            raise Refused("not on the finder's URL whitelist: %s" % url[:200])
        host = urllib.parse.urlsplit(url).hostname
        extra = dict(headers or {})
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        headers.update(extra)
        headers.update(self.extra_headers.get(host, {}))
        attempt = 0
        while True:
            self.state.lock()
            try:
                d = self.state.read()
                blk = (d.get("blocked") or {}).get(host) or {}
                if self.clock() < float(blk.get("until") or 0):
                    raise Blocked("%s answered HTTP %s; no request to it until %s" % (
                        host, blk.get("status"), utc(float(blk["until"]))), float(blk["until"]))
                if host == "www.skills.sh":
                    self.state.take(kind)
                last = float((d.get("last") or {}).get(host) or 0)
                left = self.gap - (self.clock() - last)
                if left > 0:
                    self.sleep(left)
                try:
                    self._hop_kind = kind
                    status, hdrs, body = self.opener(url, headers, cap)
                except WebError:
                    status, hdrs, body = None, {}, b""
                    if attempt >= self.retries:
                        raise
                finally:
                    d = self.state.read()
                    d.setdefault("last", {})[host] = self.clock()
                    self.state.write(d)
                    self.requests += 1
                if status in (429, 403):
                    wait = retry_after(hdrs.get("retry-after")) if status == 429 else BLOCK_403_S
                    reset = hdrs.get("x-ratelimit-reset")  # GitHub's API says when its hourly limit resets
                    if reset and str(reset).strip().isdigit():
                        wait = min(MAX_BLOCK_S, max(60, int(reset) - int(self.clock())))
                    d = self.state.read()
                    d.setdefault("blocked", {})[host] = {"status": status, "until": self.clock() + wait,
                                                         "at": utc(self.clock())}
                    self.state.write(d)
                    raise Blocked("%s answered HTTP %s: stopping; no request to it for %d s" % (host, status, wait),
                                  self.clock() + wait)
            finally:
                self.state.unlock()
            if status is None or status >= 500:
                attempt += 1
                if attempt > self.retries:
                    raise WebError("%s answered HTTP %s %d times" % (host, status, attempt))
                self.sleep(5 * attempt)
                continue
            if len(body) > cap:
                raise TooLarge("%s sent more than %d bytes for %s" % (host, cap, urllib.parse.urlsplit(url).path))
            return status, hdrs, body

    def get(self, url, cap=1024 * 1024, kind=None, accept="text/html", headers=None):
        """(status, headers, body bytes). On skills.sh, kind "page" (live finds), "list" (robots.txt and sitemaps) and
        "bulk" (the bulk index, its repo pages included) each spend their own daily cap; None spends none (GitHub,
        which has its own limits). headers: extra request headers (If-None-Match, If-Modified-Since). Raises Refused
        or WebError (Blocked and TooLarge are WebErrors)."""
        return self._request(url, cap, robots_check=True, kind=kind, accept=accept, headers=headers)


def cut(s, n):
    """Truncate text by characters (never by bytes: a byte cut splits a multi-byte character)."""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[:n].rstrip() + "..."
