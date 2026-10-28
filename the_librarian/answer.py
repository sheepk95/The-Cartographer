"""Parse and check a librarian answer against the catalogue.

A model can still misspell a path or invent a name. Every pick is checked: a known name gets the catalogue's real
path and read mode; an unknown name is dropped with a NOTE. The checked answer is re-rendered in the exact format.
"""
from .prompt import END_MARKER

MAX_PICKS, MAX_MAYBE = 6, 3


class AnswerError(ValueError):
    pass


def _entry(line):
    parts = [p.strip() for p in line.lstrip("-* ").split(" | ")]
    if len(parts) < 3:
        return None
    name, path, why = parts[0], parts[1], parts[2]
    read = parts[3] if len(parts) > 3 else "read: whole"
    return {"name": name.strip("`* "), "path": path.strip("` "), "why": why, "read": read}


def parse(text):
    lines = [l.rstrip() for l in (text or "").strip().splitlines()]
    while lines and lines[-1].strip().startswith("```"):
        lines.pop()
    if not lines or lines[-1].strip() != END_MARKER:
        raise AnswerError("answer does not end with the end marker")
    out = {"picks": [], "maybe": [], "also_grep": "", "notes": []}
    section = None
    for raw in lines[:-1]:
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        # Models sometimes dress headers in markdown ("**PICKS:**", "## Maybe:"); read them the same.
        head = line.lstrip("#").strip().replace("**", "").replace("__", "")
        up = head.upper()
        if up.startswith("PICKS:"):
            section = "picks"
            continue
        if up.startswith("MAYBE:"):
            section = "maybe"
            continue
        if up.startswith("ALSO GREP:"):
            out["also_grep"] = head.split(":", 1)[1].strip()
            section = None
            continue
        if up.startswith("NOTE:"):
            out["notes"].append(head.split(":", 1)[1].strip())
            section = None
            continue
        if section and line.startswith(("-", "*")):
            e = _entry(line)
            if e:
                out[section].append(e)
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
