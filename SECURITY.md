# Security

## Reporting a vulnerability

Please report security problems privately, through the repository's private vulnerability reporting (the
"Report a vulnerability" button on the Security tab), not in a public issue. Include the version
(`cartographer --version`), the backend, and the steps to reproduce.

## What The Cartographer does and does not do

- **It runs no skill code.** It reads `SKILL.md` front matter and text to build the catalogue. Scripts that ship
  inside skills are never executed by The Cartographer. Your agent may run them if a skill tells it to, so read them as
  you would any third-party code. An installed skill can also carry agent configuration that an agent host runs on
  its own (plugin manifests, MCP or hook settings, front matter `hooks` or `allowed-tools`, SKILL.md shell commands).
  `cartographer install` refuses what it finds at the top of the skill folder and in SKILL.md unless you pass
  `--allow-agent-config`, and lists the same names deeper in the folder as warnings. These are pattern checks that
  fail closed, not a guarantee: any whitespace before `` !` `` counts, and so do a `` ```! `` fence anywhere, quoted
  or spaced keys, and front matter in YAML forms the check cannot read. Read a skill before your agent uses it.
- **The model gets no tools.** The `claude` backend runs `claude -p --safe-mode --tools ""` (hooks, skills, plugins,
  MCP servers and CLAUDE.md files off). The `codex` backend runs `codex exec` in a read-only sandbox with the shell
  tool off, approvals set to never, and your user config ignored unless `CARTOGRAPHER_CODEX_KEEP_CONFIG` is set. The
  `anthropic` backend sends a plain request with no tools.
- **The brief is data.** The prompt tells the model never to follow instructions inside a brief. The answer is
  parsed and every pick is matched to the catalogue, so a manipulated answer can't name a path outside it.
- **The `command` backend runs what you give it.** `--command` and `CARTOGRAPHER_COMMAND` are executed as given, with
  the prompt on stdin (no shell, except that on Windows a `.cmd` or `.bat` file runs through `cmd /c`). Only set
  them to commands you trust.
- **Your skills go where your backend goes.** The catalogue, including your local skills' names, paths and
  descriptions, is sent to the backend you chose and nowhere else.
- **The finder only reads whitelisted URLs.** All its network access goes through one fetcher with a fixed
  whitelist of https URL shapes. `cartographer find` requests skills.sh pages and sitemaps (after its robots.txt) and
  nothing else; `cartographer install` adds one `api.github.com` call (none with `--ref`) and one
  `codeload.github.com` tarball for a pinned commit. Any other host or path, plain http, a URL with a query string,
  and a redirect off the whitelist or to a path robots.txt disallows are refused before a connection to it opens.
  Each redirect hop that is followed waits the same gap, and a hop on skills.sh counts against the daily cap.
  `CARTOGRAPHER_GITHUB_TOKEN`, if set, is sent to `api.github.com` only, never on to a redirect. Text from skills.sh is
  shown as data, and the optional `--judge` sends the brief and the shortlist to your backend fenced as data (with
  `<` and `>` replaced, so the text cannot close the fence); no judge verdict installs anything. The MCP
  `find_skills` tool can search but never judges or installs. `CARTOGRAPHER_NO_NETWORK` switches all of this off.
- **`cartographer install` writes, but never runs.** It downloads the tarball (at most 200 MB) into a temporary
  folder in the cache and reads it member by member (never `extractall`), with caps of 100,000 members and 2 GB
  unpacked, and checks each file's size before reading it. It refuses the whole archive if any member has an
  absolute or `..` path or a colon or backslash in its name (a colon part is a drive on Windows), refuses names that
  differ between systems, and checks before each write that the resolved path is inside its temporary folder. It
  skips symlinks, hard links and devices, drops executable bits, flags scripts and binaries, stops above 500 files or
  20 MB, refuses agent configuration at the top of the skill folder or in SKILL.md unless `--allow-agent-config` (and
  warns about it deeper down), refuses a missing or restrictive licence (a permissive text with a use rider, such as
  "not for commercial use" or "personal use only", counts as restrictive) or one in `CARTOGRAPHER_REFUSE_LICENCES`
  unless you pass `--allow-any-licence`, refuses to overwrite an existing folder, and
  asks before writing (with no terminal and no `--yes`, it refuses).
- **Bundled files are pinned.** `python tools/vendor.py verify` checks every bundled file against its recorded
  SHA-256. `fetch` downloads from `raw.githubusercontent.com` only and executes nothing it downloads.
