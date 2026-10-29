"""Parse and check a cartographer answer against the catalogue.

A model can still misspell a path or invent a name. Every pick is checked: a known name gets the catalogue's real
path and read mode; an unknown name is dropped with a NOTE (when every pick is unknown, cli.ask exits 3 instead).
The checked answer is re-rendered in the exact format.
"""
import re

from .prompt import END_MARKER

MAX_PICKS, MAX_MAYBE = 6, 3
# A header, maybe dressed in markdown ("**PICKS:**", "## MAYBE:", "__NOTE:__ x", "**PICKS: none**"). Only the
# wrappers around the label come off; the rest of the line is kept as written.
_HEAD = re.compile(r"#*\s*(\*\*|__)?\s*(PICKS|MAYBE|ALSO GREP|NOTE)\s*(\*\*|__)?\s*:\s*(\*\*|__)?\s*(.*)\Z", re.I)
# Paired wrappers a model may put round a whole none: markdown, code, brackets
_PAIRS = (("**", "**"), ("__", "__"), ("`", "`"), ("*", "*"), ("_", "_"), ("(", ")"), ("[", "]"))
# What may follow "none" before a one-line reason: a comma, semicolon, colon or ". ", a spaced dash, or a space
_SEP = re.compile("\\s*[,;:]|\\.\\s|\\s*[-\u2013\u2014]\\s|\\s+[-\u2013\u2014]|\\s")
_PATHY = "/\\|"

# The pick-field separator the prompt asks for; a bare "|" inside a field ("str|None") is part of the text
_FIELD = re.compile(r"\s\|\s")


class AnswerError(ValueError):
    pass


def _close(s):
    """Index of the bracket that closes s[0] ("(" or "["), or -1 when it is never closed or a bracket mismatches."""
    stack = []
    for i, c in enumerate(s):
        if c in "([":
            stack.append(")]"["([".index(c)])
        elif c in ")]":
            if not stack or stack.pop() != c:
                return -1
            if not stack:
                return i
    return -1


def _unwrap(s):
    s = s.strip()
    while True:
        for a, b in _PAIRS:
            if len(s) >= len(a) + len(b) and s.startswith(a) and s.endswith(b) \
                    and (a not in "([" or _close(s) == len(s) - 1):
                s = s[len(a):len(s) - len(b)].strip()
                break
        else:
            return s


def _prose_ok(s):
    """A reason after "none": brackets matched, and no path or pick-field character outside them."""
    stack = []
    for c in s:
        if c in "([":
            stack.append(")]"["([".index(c)])
        elif c in ")]":
            if not stack or stack.pop() != c:
                return False
        elif not stack and c in _PATHY:
            return False
    return not stack


def _says_none(text):
    """An explicit none: "none", "None.", "(none)", "- none", "**none**", or "none" with a reason after it
    ("none (mechanical task)", "none: copying needs no skill", "none - ..."). Never a name or path that starts or ends
    with it ("none-such", ".none", "none_", "none.md", "none/testing", "none(foo)/SKILL.md")."""
    s = _unwrap(text)
    bullet = re.match(r"-\s*|\*\s+", s)  # "- none", "* none"; never the first "*" of "**none**"
    if bullet:
        s = _unwrap(s[bullet.end():])
    token = re.match(r"(\*\*|__|`|\*|_)(none\.?)\1", s, re.I)  # "**none** (reason)": the wrapper is on none alone
    if token:
        s = token.group(2) + s[token.end():]
    if s.endswith("."):  # one trailing period, then any wrapper it closed ("(none).", "**None.**")
        s = _unwrap(s[:-1])
    s = s.lower()
    if not s.startswith("none"):
        return False
    rest = s[4:]
    if rest.lstrip().startswith("("):  # "none (reason)", then nothing or a separator and more reason
        rest = rest.lstrip()
        end = _close(rest)
        if end < 0 or _FIELD.search(rest[:end]):  # unclosed, mismatched, or a pick row inside the brackets
            return False
        rest = rest[end + 1:]
        if not rest.strip():
            return True
    if not rest:
        return True
    sep = _SEP.match(rest)
    return bool(sep) and _prose_ok(rest[sep.end():])


def _entry(line):
    """One pick or maybe row: exactly four fields, a name, a path and a why that are not empty, then "read: ..."."""
    body = line.lstrip("-* ")
    parts = [p.strip() for p in _FIELD.split(body)]
    if len(parts) != 4:  # no spaced separators at all ("a|b|c|read: whole"): split on the bare ones
        parts = [p.strip() for p in body.split("|")]
    if len(parts) != 4:
        return None
    name, path, why, read = parts[0].strip("`* "), parts[1].strip("` "), parts[2], parts[3]
    if not (name and path and why and read.lower().startswith("read:") and read[5:].strip()):
        return None
    return {"name": name, "path": path, "why": why, "read": read}


def parse(text):
    lines = [l.rstrip() for l in (text or "").strip().splitlines()]
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()
    if not lines or lines[-1].strip() != END_MARKER:
        raise AnswerError("answer does not end with the end marker")
    out = {"picks": [], "maybe": [], "also_grep": "", "notes": []}
    section = None
    # A missing or unreadable PICKS section is a malformed answer, not "no skill fits": only an explicit
    # "PICKS: none" (or readable pick lines) says that, so a failed parse can never pass as a confident "none".
    saw_picks = said_none = False
    unread = []
    for raw in lines[:-1]:
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        # Models sometimes dress headers in markdown ("**PICKS:**", "## Maybe:"); read them the same.
        m = _HEAD.match(line)
        if m:
            wrap, up, rest = m.group(1), " ".join(m.group(2).upper().split()), m.group(5).strip()
            # "PICKS: **none**" or "**PICKS**: **none**": that wrapper belongs to the value, not the header
            if m.group(4) and (not wrap or m.group(3)):
                rest = m.group(4) + rest
            if wrap and not (m.group(3) or m.group(4)) and rest.endswith(wrap):  # "**PICKS: none**"
                rest = rest[:-len(wrap)].strip()
        else:
            up = rest = ""
        if up == "PICKS":
            section, saw_picks = "picks", True
            if _says_none(rest):
                said_none = True
            elif rest:
                unread.append(line)
            continue
        if up == "MAYBE":
            section = "maybe"
            continue
        if up == "ALSO GREP":
            out["also_grep"] = rest
            section = None
            continue
        if up == "NOTE":
            out["notes"].append(rest)
            section = None
            continue
        e = _entry(line) if section and line.startswith(("-", "*")) else None
        if e:
            out[section].append(e)
        elif section == "picks":
            if not out["picks"] and _says_none(line):  # "PICKS:" with "none" on the next line
                said_none = True
            else:
                unread.append(line)
    if not saw_picks:
        raise AnswerError("answer has no PICKS section")
    if not out["picks"] and not said_none:
        raise AnswerError("PICKS lists nothing readable" + (": %r" % unread[0][:80] if unread else ""))
    if unread:  # the answer is usable, but a line under PICKS was not a pick: say so rather than drop it silently
        out["notes"].append("ignored %d line(s) under PICKS that are not in the pick format, first: %r"
                            % (len(unread), unread[0][:80]))
    return out


def check(parsed, skills):
    """Return a corrected copy: real paths and read modes for known names, unknown names dropped."""
    by_name = {s.name.lower(): s for s in skills}
    by_path = {s.path.replace("\\", "/").lower(): s for s in skills}
    fixed = {"picks": [], "maybe": [], "also_grep": parsed.get("also_grep", ""), "notes": list(parsed.get("notes", []))}
    dropped = []
    seen = set()
    for section in ("picks", "maybe"):
        for e in parsed.get(section, []):
            s = by_name.get(e["name"].lower()) or by_path.get(e["path"].replace("\\", "/").lower())
            if s is None:
                dropped.append(e["name"])
                continue
            if s.name in seen:
                continue
            seen.add(s.name)
            fixed[section].append({"name": s.name, "path": s.path.replace("\\", "/"), "why": e["why"],
                                   "read": "read: LARGE read in parts" if s.large else "read: whole",
                                   "origin": s.origin})
    if len(fixed["picks"]) > MAX_PICKS:  # the format allows 6; an agent opens every pick it is given
        extra = [e["name"] for e in fixed["picks"][MAX_PICKS:]]
        fixed["picks"] = fixed["picks"][:MAX_PICKS]
        fixed["notes"].append("dropped picks over %d: %s" % (MAX_PICKS, ", ".join(extra)))
    fixed["maybe"] = fixed["maybe"][:MAX_MAYBE]
    if dropped:
        fixed["notes"].append("dropped names not in the catalogue: " + ", ".join(dropped))
    return fixed


def render(a):
    out = []
    if a["picks"]:
        out.append("PICKS:")
        out += ["- %s | %s | %s | %s" % (e["name"], e["path"], e["why"], e["read"]) for e in a["picks"]]
    else:
        out.append("PICKS: none")
    if a["maybe"]:
        out.append("MAYBE:")
        out += ["- %s | %s | %s | %s" % (e["name"], e["path"], e["why"], e["read"]) for e in a["maybe"]]
    if a.get("also_grep"):
        out.append("ALSO GREP: " + a["also_grep"])
    out += ["NOTE: " + n for n in a.get("notes", []) if n]
    out.append(END_MARKER)
    return "\n".join(out)
