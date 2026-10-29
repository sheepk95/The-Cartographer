"""Minimal YAML front matter reader for SKILL.md files (stdlib only).

Reads top-level scalar keys: plain, quoted, folded (>) and literal (|) values, and plain values continued on indented
lines. Nested mappings are skipped. That covers the `name` and `description` fields every skill uses.
"""
import re

_KEY = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s+(.*))?$")
_BLOCK = {"|", "|-", "|+", ">", ">-", ">+"}


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return v[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return v


def _finish(mode, buf):
    if mode == "literal":
        lines = [l for l in buf]
        pad = min((len(l) - len(l.lstrip()) for l in lines if l.strip()), default=0)
        return "\n".join(l[pad:] for l in lines).strip()
    joined = " ".join(l.strip() for l in buf if l.strip())
    return joined if mode == "folded" else _unquote(joined)


def split(text):
    """Return (front matter lines, body) or (None, text) when the file has no front matter."""
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def parse(text):
    """Parse the front matter of a SKILL.md text into a dict of top-level string values."""
    fm, _ = split(text)
    if fm is None:
        return {}
    out, key, mode, buf = {}, None, None, []
    for line in fm:
        if not line.strip() or line.lstrip().startswith("#") and not line[:1].isspace():
            if key is not None and mode == "literal":
                buf.append("")
            continue
        m = _KEY.match(line) if not line[:1].isspace() else None
        if m:
            if key is not None:
                out[key] = _finish(mode, buf)
            key, rest = m.group(1), (m.group(2) or "").strip()
            if rest in _BLOCK:
                mode, buf = ("literal" if rest[0] == "|" else "folded"), []
            else:
                mode, buf = "plain", [rest]
        elif key is not None:
            buf.append(line)
    if key is not None:
        out[key] = _finish(mode, buf)
    return out
