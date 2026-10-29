"""Name a skill's licence and decide whether `cartographer install` may take it without an explicit override.

skills.sh shows no licence, so the installer reads one from the repository itself, nearest first: the SKILL.md front
matter `license:` field, a LICENSE/LICENCE/COPYING file in the skill folder, then the same in each parent folder up to
the repository root. Texts are classified by their wording; ids in front matter are matched to SPDX ids.
"""
import os, re

# Licences that allow use, copying and redistribution. Anything else needs --allow-any-licence.
OPEN = {"MIT", "MIT-0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "0BSD", "Unlicense", "CC0-1.0",
        "CC-BY-4.0", "CC-BY-SA-4.0", "MPL-2.0", "Zlib", "BSL-1.0", "GPL-2.0", "GPL-3.0", "LGPL-2.0", "LGPL-2.1",
        "LGPL-3.0", "AGPL-3.0", "EPL-2.0", "Python-2.0", "Artistic-2.0", "NCSA", "OFL-1.1"}
# Open licences whose terms follow the skill when it is passed on (share-alike): install prints a one-line note and
# records "copyleft" in .cartographer-source.json. They are allowed: installing a skill for your own agent is neither
# passing it on nor offering it as a network service. (OFL-1.1: changed fonts stay under the OFL, and the fonts may
# not be sold on their own.)
COPYLEFT = {"GPL-2.0", "GPL-3.0", "LGPL-2.0", "LGPL-2.1", "LGPL-3.0", "AGPL-3.0", "MPL-2.0", "EPL-2.0", "CC-BY-SA-4.0",
            "OFL-1.1"}
# An organisation that bans some open licences lists them here, comma-separated (for example AGPL-3.0,GPL-3.0).
REFUSE_ENV = "CARTOGRAPHER_REFUSE_LICENCES"
REFUSED_WHY = {
    "NONE": "no licence found: without one you have no right to copy it",
    "UNKNOWN": "the licence text was not recognised",
    "NON-COMMERCIAL": "non-commercial licence",
    "NO-DERIVATIVES": "no-derivatives licence",
    "PROPRIETARY": "proprietary or all rights reserved",
    "SOURCE-AVAILABLE": "source-available licence that limits use",
}
LICENCE_FILE_RE = re.compile(r"(?i)^(licen[cs]e|copying|unlicense)([._-][A-Za-z0-9._-]*)?$")
NOTICE_FILE_RE = re.compile(r"(?i)^notice([._-][A-Za-z0-9._-]*)?$")

_IDS = {  # lower-cased front matter spellings -> SPDX id
    "mit": "MIT", "mit license": "MIT", "the mit license": "MIT", "mit-0": "MIT-0",
    "apache-2.0": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache2": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0", "apache license, version 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause", "bsd-3-clause": "BSD-3-Clause", "isc": "ISC", "0bsd": "0BSD",
    "unlicense": "Unlicense", "the unlicense": "Unlicense", "cc0-1.0": "CC0-1.0", "cc0": "CC0-1.0",
    "cc-by-4.0": "CC-BY-4.0", "cc by 4.0": "CC-BY-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc by-sa 4.0": "CC-BY-SA-4.0",
    "mpl-2.0": "MPL-2.0", "zlib": "Zlib", "bsl-1.0": "BSL-1.0", "epl-2.0": "EPL-2.0", "artistic-2.0": "Artistic-2.0",
    "gpl-2.0": "GPL-2.0", "gpl-2.0-only": "GPL-2.0", "gpl-2.0-or-later": "GPL-2.0", "gplv2": "GPL-2.0",
    "gpl-3.0": "GPL-3.0", "gpl-3.0-only": "GPL-3.0", "gpl-3.0-or-later": "GPL-3.0", "gplv3": "GPL-3.0",
    "lgpl-2.1": "LGPL-2.1", "lgpl-3.0": "LGPL-3.0", "agpl-3.0": "AGPL-3.0", "agpl-3.0-only": "AGPL-3.0",
    "proprietary": "PROPRIETARY", "all rights reserved": "PROPRIETARY", "unlicensed": "PROPRIETARY",
    "busl-1.1": "SOURCE-AVAILABLE", "bsl-1.1": "SOURCE-AVAILABLE", "elastic-2.0": "SOURCE-AVAILABLE",
    "sspl-1.0": "SOURCE-AVAILABLE", "commons-clause": "SOURCE-AVAILABLE",
    "cc-by-nc-4.0": "NON-COMMERCIAL", "cc-by-nc-sa-4.0": "NON-COMMERCIAL", "cc-by-nc-nd-4.0": "NON-COMMERCIAL",
    "cc-by-nd-4.0": "NO-DERIVATIVES", "polyform-noncommercial-1.0.0": "NON-COMMERCIAL",
    "bsd 2-clause": "BSD-2-Clause", "bsd 3-clause": "BSD-3-Clause", "mpl 2.0": "MPL-2.0", "isc license": "ISC",
    "lgpl-2.0": "LGPL-2.0", "python-2.0": "Python-2.0", "psf-2.0": "Python-2.0", "ncsa": "NCSA",
    "ofl-1.1": "OFL-1.1", "json": "JSON",
}
_SPDX = {i.lower(): i for i in OPEN}
_SPDX.update(_IDS)


def _one(term):
    """SPDX id for one licence id (not an expression): "-only", "-or-later" and "+" are dropped, and so is a "WITH"
    exception (an exception only adds permissions). None when it is not an id this module knows."""
    k = re.sub(r"\s+", " ", (term or "").strip().strip("()").strip().lower())
    k = re.sub(r" with .*$", "", k)
    if k in _SPDX:
        return _SPDX[k]
    k = re.sub(r"(\+|-only|-or-later)$", "", k)
    return _SPDX.get(k)


# Phrases that put a use restriction on a text, a permissive one included ("MIT, but not for commercial use"). They
# are checked before the Unlicense and the titles below, so a rider decides, and when unsure this fails closed
# (refused, with the evidence printed). Not riders: a licence's own permissive wording ("for any purpose, commercial or
# non-commercial") and the GNU licences' "noncommercial distribution" clause.
_NC_USE = r"(personal|private|educational|academic|evaluation|research|internal|hobby|non[- ]?commercial)"
NON_COMMERCIAL_RE = re.compile(
    r"(?i)polyform noncommercial|attribution-noncommercial|\bnot for (any )?commercial\b|"
    r"(?<!commercial or )(?<!commercial and )(?<!commercial, )\bnon[- ]?commercial\b"
    r"(?!ly| distribution| (or|and) commercial)|"
    r"\b(may|must|shall|can|could|will) not (be )?(use[ds]?|sell|sold|exploit(ed)?|licen[cs]e[ds]?|offer(ed)?)\b"
    r"[^.;]{0,80}\bcommercial(ly)?\b|"
    r"\bcommercial(ly)? (use|usage|purposes?|exploitation|redistribution|distribution)\b[^.;]{0,60}"
    r"\b(is|are|being) (strictly )?(prohibited|forbidden|not (permitted|allowed))|"
    r"\bno commercial (use|usage|purposes?|exploitation|redistribution|distribution)\b|"
    r"\bcommercial (use|usage|purposes?|exploitation|redistribution|distribution)\b[^.;]{0,60}"
    r"\b(requires?|needs?|is subject to) (a |an )?(separate|commercial|paid|written|different|additional)|"
    r"\b%s( (and|or|and/or) %s)*,? (use|usage|purposes?)( purposes)? only\b|"
    r"\b(only|solely|exclusively|strictly) (for|to be used for) (your )?(own )?%s\b(?! distribution)"
    % (_NC_USE, _NC_USE, _NC_USE))
# Riders that forbid passing the text on at all ("you may not redistribute"): all rights reserved, in effect. Not
# riders: the GNU licences' "you may not distribute the Program at all" (when a court order conflicts), the OFL's
# "must not be distributed under any other license" and "may not be copied ... except according to those terms".
_BY_THE_LICENCE = (r"(?![^.;]{0,80}\b(at all|under (any|an|the|this)|except (according to|under|in accordance with|as "
                   r"(expressly )?(provided|permitted|stated|set out))|in accordance with)\b)")
NO_REDISTRIBUTION_RE = re.compile(
    r"(?i)\b(may|must|shall|can) not (re)?distribute\b" + _BY_THE_LICENCE + "|"
    r"\b(may|must|shall) not be (copied|redistributed|distributed|shared|republished)\b" + _BY_THE_LICENCE + "|"
    r"\b(re)?distribution\b[^.;]{0,80}\b(is |are )?(strictly )?(prohibited|forbidden|not (permitted|allowed))"
    + _BY_THE_LICENCE)
NO_DERIVATIVES_RE = re.compile(r"(?i)attribution-noderivatives|attribution-noderivs")
SOURCE_AVAILABLE_RE = re.compile(r"(?i)business source license|elastic license|server side public license|"
                                 r"commons clause")


def _gnu(kind):
    def pick(t, m):
        v = re.search(r"(?i)\bversion (\d(?:\.\d)?)", t[m.end():m.end() + 160])
        v = v.group(1) if v else ("3" if re.search(r"(?i)\bversion 3\b", t) else "2")
        if kind == "AGPL":
            return "AGPL-3.0"
        if kind == "LIBRARY":
            return "LGPL-2.0"
        if kind == "LGPL":
            return "LGPL-3.0" if v.startswith("3") else "LGPL-2.1"
        return {"1": "GPL-1.0", "2": "GPL-2.0"}.get(v[:1], "GPL-3.0")
    return pick


# Licence titles and grant sentences. Many licence texts name other licences (GPL-3.0 section 13 names the Affero
# licence, MPL-2.0 and EPL-2.0 list the GNU licences, LGPL-3.0 incorporates the GPL, and Boost, OFL and NCSA grant in
# MIT's own words), so the one that comes FIRST in the text is the text's own licence.
TITLES = [
    (re.compile(r"(?i)apache license,? version 2\.0|\bApache License\b(?=.{0,40}Version 2\.0)"), "Apache-2.0"),
    (re.compile(r"(?i)MIT No Attribution"), "MIT-0"),
    (re.compile(r"(?i)Boost Software License"), "BSL-1.0"),
    (re.compile(r"(?i)SIL OPEN FONT LICEN[CS]E"), "OFL-1.1"),
    (re.compile(r"(?i)University of Illinois ?/ ?NCSA Open Source License"), "NCSA"),
    (re.compile(r"(?i)PYTHON SOFTWARE FOUNDATION LICEN[CS]E VERSION 2"), "Python-2.0"),
    (re.compile(r"(?i)SGI FREE SOFTWARE LICEN[CS]E B"), "SGI-B-2.0"),
    (re.compile(r"(?i)Bitstream Vera Fonts Copyright"), "Bitstream-Vera"),
    (re.compile(r"(?i)Permission is hereby granted, free of charge"),  # NCSA grants in MIT's words, "deal WITH"
     lambda t, m: "NCSA" if re.search(r"(?i)to deal with the Software without restriction", t) else "MIT"),
    (re.compile(r"(?i)Redistribution and use in source and binary forms"),
     lambda t, m: "BSD-3-Clause" if re.search(r"(?i)neither the name", t) else "BSD-2-Clause"),
    (re.compile(r"(?i)permission to use, copy, modify, and/?or distribute this software for any purpose"),
     lambda t, m: "ISC" if "copyright notice and this permission notice appear" in t else "0BSD"),
    (re.compile(r"(?i)\bCC0 1\.0\b|Creative Commons Zero"), "CC0-1.0"),
    (re.compile(r"(?i)Attribution-ShareAlike 4\.0"), "CC-BY-SA-4.0"),
    (re.compile(r"(?i)Attribution 4\.0 International"), "CC-BY-4.0"),
    (re.compile(r"(?i)Mozilla Public License,? (Version )?2\.0"), "MPL-2.0"),
    (re.compile(r"(?i)Eclipse Public License,? -? ?(v|version) ?2\.0"), "EPL-2.0"),
    (re.compile(r"(?i)The Artistic License 2\.0"), "Artistic-2.0"),
    (re.compile(r"(?i)GNU AFFERO GENERAL PUBLIC LICEN[CS]E"), _gnu("AGPL")),
    (re.compile(r"(?i)GNU LESSER GENERAL PUBLIC LICEN[CS]E"), _gnu("LGPL")),
    (re.compile(r"(?i)GNU LIBRARY GENERAL PUBLIC LICEN[CS]E"), _gnu("LIBRARY")),
    (re.compile(r"(?i)GNU GENERAL PUBLIC LICEN[CS]E"), _gnu("GPL")),
    (re.compile(r"(?i)This software is provided 'as-is'.*?altered source versions must be plainly marked"), "Zlib"),
]


def from_text(text):
    """SPDX id (or one of the REFUSED_WHY keys) for a licence file's text. Use riders come first, so MIT plus "not for
    commercial use" is NON-COMMERCIAL, not MIT; the Unlicense's own "commercial or non-commercial" is no rider."""
    t = re.sub(r"\s+", " ", text or "")
    if not t.strip():
        return "NONE"
    if NON_COMMERCIAL_RE.search(t):
        return "NON-COMMERCIAL"
    if NO_REDISTRIBUTION_RE.search(t):
        return "PROPRIETARY"
    if NO_DERIVATIVES_RE.search(t):
        return "NO-DERIVATIVES"
    if SOURCE_AVAILABLE_RE.search(t):
        return "SOURCE-AVAILABLE"
    if re.search(r"(?i)shall be used for good,? not evil", t):
        return "UNKNOWN"  # the JSON licence: MIT's words plus a use restriction no one can check
    if "This is free and unencumbered software released into the public domain" in t:
        return "Unlicense"  # after the riders above: an Unlicense with a Commons Clause is not the Unlicense
    first = None
    for rx, name in TITLES:
        m = rx.search(t)
        if m and (first is None or m.start() < first[0].start()):
            first = (m, name)
    if first:
        m, name = first
        return name(t, m) if callable(name) else name
    if re.search(r"(?i)all rights reserved|proprietary", t):
        return "PROPRIETARY"
    return "UNKNOWN"


def from_field(value):
    """SPDX id or flat SPDX expression ("MIT OR Apache-2.0") for a front matter `license:` value, or None when the
    value points elsewhere ('see LICENSE.txt'). A term this module does not know becomes UNKNOWN."""
    v = (value or "").strip().strip("'\"").strip()
    if not v:
        return None
    key = v.lower()
    if key in _IDS:
        return _IDS[key]
    if re.search(r"(?i)\b(see|in|complete terms)\b.*\b(licen[cs]e|copying)", v) or LICENCE_FILE_RE.match(v):
        return None  # a pointer to a file: classify that file instead
    inner = v
    while inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1].strip()
    ops = {o.upper() for o in re.findall(r"(?i)\s(OR|AND)\s", inner)}
    if ops:
        if len(ops) > 1 or "(" in inner or ")" in inner:
            return "UNKNOWN"  # a nested expression: not read, so refused unless --allow-any-licence
        ids = []
        for term in re.split(r"(?i)\s(?:OR|AND)\s", inner):
            i = _one(term) or "UNKNOWN"
            if i not in ids:
                ids.append(i)
        return (" %s " % ops.pop()).join(ids)
    one = _one(inner)
    if one:
        return one
    got = from_text(v)
    return got if got not in ("UNKNOWN", "NONE") else "UNKNOWN"


def split(spdx):
    """("OR" | "AND" | None, [ids]) for an id or a flat expression made by from_field or the installer."""
    s = (spdx or "").strip()
    for op in (" OR ", " AND "):
        if op in s:
            return op.strip(), [p.strip() for p in s.split(op)]
    return None, [s]


def refused_here(env=None):
    """The licence ids this machine refuses on top of the policy ($CARTOGRAPHER_REFUSE_LICENCES), lower-cased."""
    raw = (os.environ if env is None else env).get(REFUSE_ENV) or ""
    return {(_one(x) or x.strip()).lower() for x in raw.split(",") if x.strip()}


def _verdict(i, deny):
    if i.lower() in deny:
        return False, "licence %s is refused on this machine (%s)" % (i, REFUSE_ENV)
    if i in OPEN:
        return True, ""
    return False, REFUSED_WHY.get(i, "licence %s is not on the open list" % i)


def policy(spdx, env=None):
    """(ok, reason). One id: ok when it is in OPEN and not refused here. "A OR B": ok when any of them is. "A AND B":
    ok only when all of them are."""
    op, ids = split(spdx)
    deny = refused_here(env)
    got = [_verdict(i, deny) for i in ids]
    if op == "OR":
        if any(ok for ok, _ in got):
            return True, ""
        return False, "; ".join(dict.fromkeys(why for _, why in got))
    for ok, why in got:
        if not ok:
            return False, why
    return True, ""


def taken(spdx, env=None):
    """The ids whose terms apply: for "A OR B" the one you take (an allowed one, permissive before copyleft), else
    every id."""
    op, ids = split(spdx)
    if op != "OR":
        return ids
    deny = refused_here(env)
    ok = sorted((i for i in ids if _verdict(i, deny)[0]), key=lambda i: i in COPYLEFT)
    return ok[:1] or ids


def copyleft(spdx, env=None):
    """The copyleft ids among the terms that apply (empty when none)."""
    return [i for i in taken(spdx, env) if i in COPYLEFT]
