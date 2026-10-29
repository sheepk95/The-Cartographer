# Changelog

## 0.1.1 (2026-10-29)

- Reject output from failed Codex runs before reading answer files; report malformed custom commands through the
  normal CLI/MCP unavailable response.
- Refuse unknown licence exceptions and prevent pointer-looking SPDX clauses from bypassing licence checks.
- Keep fetch ownership for slow live processes with persistent OS locks, merge robots metadata under the shared
  lock, and normalize escaped unreserved and UTF-8 paths before robots matching.
- Refuse legacy, unknown and incompatible Windows/POSIX cache-lock markers without modifying them.
- Refresh local skills on each MCP search and read, so additions, removals and renames take effect immediately.
- Resolve the bundled Playwright wrapper from its installed location, invoke it explicitly with Bash, and convert
  Windows-hosted paths inside WSL while preserving the pinned upstream skill files.
- Increase the Codex MCP client timeout example to 600 seconds for normal-attempt headroom; document that API
  timeouts apply per attempt and server-directed retry waits can exceed the client timeout.

**Upgrading:** stop every Cartographer process and waiter using a cache before upgrading or manually removing a
legacy lock marker. Follow the README's shared-fetch-lock migration instructions. Windows and WSL must use separate
`CARTOGRAPHER_CACHE` folders; their request caps, spacing and block state are independent.

## 0.1.0 (2026-10-29)

First public version.

- Licence: the code is under the Apache License 2.0, with a NOTICE file (copyright 2026 Blake W). The bundled
  skills keep their own licences.
- Install: `pipx install the-cartographer`, `pip install the-cartographer` or `uvx the-cartographer ...` (the package also
  installs the command under its own name, `the-cartographer`). Claude Code: the repository is a plugin marketplace
  (`/plugin marketplace add sheepk95/The-Cartographer`, then `/plugin install the-cartographer@the-cartographer`). MCP
  Registry metadata in `server.json`; releases publish to PyPI through Trusted Publishing (`publish.yml`).
- `cartographer ask`: one model call reads a 2-10 line brief against the whole skill catalogue and answers with
  PICKS / MAYBE / ALSO GREP / NOTE, ending in `--- end of cartographer answer ---`. Every name is checked against the
  catalogue; invented names are dropped and wrong paths corrected. An answer with no readable PICKS (a pick line
  needs all four fields) and no explicit `PICKS: none`, or whose every pick is invented, exits 3
  (`CARTOGRAPHER_UNAVAILABLE`) instead of reading as "no skill needed".
- Backends: `anthropic` (official SDK, catalogue in a 1-hour prompt cache), `claude` (Claude Code print mode),
  `codex` (`codex exec`, read-only) and `command` (any stdin-to-stdout command).
- Offline commands: `search`, `list`, `show`, `catalogue`, `doctor`.
- `cartographer mcp`: stdio MCP server with `ask_cartographer`, `read_skill`, `search_skills` and `find_skills` (search
  only: it never judges or installs).
- Integrations for Claude Code (skill, CLAUDE.md snippet, `.mcp.json`) and Codex (AGENTS.md snippet, `config.toml`).
- 193 bundled third-party skills from 59 upstream repositories, pinned by commit and SHA-256
  (`tools/vendor.py verify | fetch | notices`).
- `cartographer find`: skills on skills.sh that the catalogue lacks, by a lexicon fit rule over the sitemap names and
  the current pages of the best matches (at most 8 fetched per search), with a popularity bar; installs nothing.
  Polite by construction: robots.txt first, one request at a time at least 1.3 s apart across processes, a stop on
  429/403, daily caps (300 pages, 12 robots/sitemap requests), conditional requests (an unchanged page costs a
  304), a URL whitelist checked before any connection and on every redirect (robots.txt too; each hop waits the
  gap, and a hop on skills.sh spends the daily cap), and a User-Agent
  that names the project's URL. Options `--offline`, `--lexicon`, `--limit` (1-10, else exit 2), `--json`,
  `--brief-file` (`-` reads stdin), and `--judge` (one model call that marks each find KEEP or DROP; third-party
  text is fenced with `<` and `>` replaced; an unreadable reply exits 3 with `JUDGE FAILED`). Exit 3 also when no
  find was printed while some name matches could not be checked.
- `cartographer install`: vets a skills.sh find or `owner/repo[/skill]` at a pinned commit (file list with flags, safe
  archive reading with member and size caps, never overwrites, never runs anything) and writes a
  `.cartographer-source.json` provenance record. Licence refusals (and `--judge` prompt-injection flags) go to the
  finder's `refused.jsonl`, so `find` stops offering them.
  - Licence: the SKILL.md `license` field (SPDX ids and flat `OR` / `AND` expressions) and the nearest licence
    files; when they disagree both apply and a refused one decides. Missing, unknown, non-commercial,
    no-derivatives, source-available and proprietary licences are refused (`--allow-any-licence` to override), and
    so is any id in `CARTOGRAPHER_REFUSE_LICENCES`. A permissive text with a use rider (not for commercial use,
    personal use only, no redistribution) is refused as restrictive. Copyleft licences, OFL-1.1 included, are
    allowed with a note and recorded as `"copyleft": true`.
  - The licence text is always carried into the installed folder, and the record's `licence_text` names it.
  - Agent configuration that a host can run on its own is refused unless `--allow-agent-config`: plugin manifests,
    MCP and hook settings, front matter `hooks` or `allowed-tools` in any quoting or spacing, front matter in YAML
    forms that cannot be checked, and SKILL.md shell commands after any whitespace or in a `!` fence anywhere. The
    same names deeper in the skill folder are listed as warnings and recorded as `agent_config_warnings`.
  - Archives with a colon or backslash in a member name, and names that cannot be written the same way on every
    system, are refused; Windows device names include COM0, LPT0, COM¹-³, LPT¹-³, CONIN$ and CONOUT$. A GitHub
    token is never sent on to a redirect.
- `cartographer finder index | status`: an optional, resumable bulk index of skills.sh pages (at least 3 s apart, its
  own daily cap of 2,000 via `CARTOGRAPHER_FINDER_DAILY_BULK`, repo pages counted), and the cache and today's request
  counts.
- `CARTOGRAPHER_NO_NETWORK`: the finder and installer send no request (the test suite sets it).
- MCP `find_skills` stops fetching pages after 45 seconds and returns failures as tool errors.
- Package metadata: a licence expression covering the code and the bundled skills, `LICENSE` and
  `THIRD_PARTY_NOTICES.md` as licence files, project URLs, and Python version classifiers (3.9 to 3.13).
- `cartographer list` shows where each installed skill came from; `cartographer doctor` reports installed skills whose
  files changed or whose licence needed an override, and the finder cache.
