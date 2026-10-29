# Design notes

## The problem

A skill is a SKILL.md file of instructions an agent reads before a kind of task. They work well in small numbers.
At a few hundred, two things break:

- **Context.** Putting every name and description in the agent's prompt costs tens of thousands of tokens on every
  turn of every agent, most of it irrelevant to the task at hand.
- **Picking.** Agents pick from names and one-line descriptions, under time pressure, mid-task. They miss the skill
  that fits and open ones that only share a word with the task. Every opened skill costs context, so wrong picks
  are expensive.

## The approach

Ask once, at the start of a task, with a short brief. One model call reads the brief against the whole catalogue and
returns a short, checked list.

- **The whole catalogue, not a shortlist.** Search-then-pick tools (embeddings, keyword ranking) are cheap and fast,
  but they decide what the model gets to consider. Here the model sees every description and judges fit the way a
  person would: by what the task needs, not by shared words. Search is still there as the offline fallback
  (`cartographer search`, `search_skills`).
- **Precision first.** The prompt asks for as few skills as do the job, puts doubtful ones under MAYBE (agents read
  only their first 40 lines), and treats "PICKS: none" as a good answer. The usual failure of skill pickers is
  naming something for a task that needs nothing.
- **Cached, so it stays cheap.** The catalogue text is deterministic: sorted, no timestamps, forward-slash paths. The
  same skills give the same bytes, so the API backend's prompt cache (1 hour TTL) keeps hitting; only the brief and
  the answer are new tokens. With the CLI backends the CLI's own caching applies.
- **Checked output.** The answer is parsed and every name is matched to the catalogue before anyone sees it. Paths are
  rewritten to the real ones, invented names are dropped, LARGE marks come from the file size, not the model.
- **Never blocking.** Every failure (no backend, timeout, malformed answer) exits 3 with one line,
  `CARTOGRAPHER_UNAVAILABLE (reason)`, telling the agent to use keyword search instead.
- **Isolated.** The model gets no tools. The CLI backends switch off the user's hooks, skills, MCP servers and
  project instructions, so an "always ask the cartographer" rule cannot recurse, and the brief is treated as data.
- **Coordinators ask once.** An agent that hands work to helpers lists every helper's task in one brief and passes
  each helper its picks, instead of every helper asking.

## Trade-offs

- **A model call per task.** Seconds of latency and, outside the cache, about 30k input tokens with the bundled
  catalogue. Keyword search is instant and free; that is why it stays as the fallback.
- **The catalogue grows with every skill**, at roughly 150-180 tokens each (the full path to each SKILL.md is part of it). At some size it would outgrow one prompt and
  need a search step in front of the model. The bundled 193 are far from that.
- **Descriptions are the only signal.** The model sees names, paths and descriptions, not the skill bodies, so a skill
  with a vague description is easy to miss.
- **Checked is not correct.** The checker guarantees that every name and path is real. Whether the pick is the right
  one is still the model's judgement.

## The finder

`cartographer ask` can only pick from skills you have. The finder answers the other question, "is there a good skill
for this that I don't have?", from skills.sh, without a model and without installing anything.

- **Live by default, small by design.** A search uses the skills.sh names list (from its sitemaps, cached a day),
  screens it with a word-based rule, and fetches the current pages of the best 8 matches at most. A full crawl of
  20,000 pages at the bulk index's pace (at least 3 seconds a page) would take about 20 hours, its daily cap of
  2,000 spreads it over ten days, and its descriptions would go stale; a search that needs 8 fresh pages takes
  about 15 seconds. The bulk index stays as an opt-in for `--offline` use, at least 3 s apart, with its own daily
  cap.
- **Polite before clever.** robots.txt first, one request at a time at least 1.3 seconds apart across every process
  that shares the cache folder, a hard stop on 429 or 403 that every later process honours, daily caps, conditional
  requests (an unchanged page costs a 304), and a URL whitelist that is checked before a socket opens, redirects
  included (whitelist and robots.txt). Search makes no GitHub API calls; install makes one (none with `--ref`), and
  a GitHub token never follows a redirect.
- **Words, not a model, by default.** The fit rule is a lexicon of concepts with IDF weights over all known names,
  a name bonus, scope rules and platform conflicts. It is fast, free and explainable ("fits: testing (fuzzing)"),
  and it is wrong in plain ways a reader can see. `--judge` adds one model call for meaning. The judge's input is
  fenced as data, its reply is parsed strictly against a fresh request id, an unreadable reply fails loudly instead
  of reading as "drop everything", a bad item is UNJUDGED rather than dropped, and no verdict ever installs.
- **Install is where trust is decided.** A find is UNVETTED. `cartographer install` pins a commit, reads the tarball
  member by member (never `extractall`), refuses unsafe and unportable names, writes no links or devices, drops
  executable bits, shows every file with flags, finds the licence (front matter and the nearest licence files; when
  they disagree both apply), carries its text, refuses anything that does not plainly allow use, refuses agent
  configuration a host could run on its own (at the top of the skill folder and in SKILL.md; pattern checks that
  fail closed) without a flag and warns about the same names deeper down, never overwrites, and runs nothing. Copyleft is allowed
  with a note: installing a skill for your own agent is neither passing it on nor offering it as a service, and
  `CARTOGRAPHER_REFUSE_LICENCES` lets an organisation refuse more. Its provenance record uses the bundle's fields
  (repository, commit, path, licence, SHA-256 per file) plus the licence evidence and text, and the skills.sh
  figures, so `doctor` can tell when an installed skill's files change.

Trade-offs:

- **Names first.** The first screen sees only names, so a well-described skill with an opaque name is missed unless
  the bulk index has its page. Ranking within the shortlist uses descriptions.
- **The figures are weak signals.** Installs are skills.sh CLI telemetry (easy to inflate); stars belong to the whole
  repository and arrive rounded; audits are automated scans. The popularity bar uses them only to cut noise.
- **Pages, not the API.** skills.sh has a public API, but its robots.txt disallows `/api/` and `/search`, and the
  finder obeys robots.txt on every request, so it reads the public sitemaps and skill pages instead. Parsing pages
  can break when the site changes; the finder then reports fewer finds with notes rather than guessing, and the
  parser tests pin the shapes it reads.
- **Install copies the whole folder.** Unlike the bundle, which leaves out hidden tool folders such as `.github/`,
  `cartographer install` keeps every file of the skill folder except `.git/`, so what you review is what upstream
  ships. Agent configuration at its top or in SKILL.md (plugin manifests, hook and MCP settings, front matter
  `hooks` or `allowed-tools`, `!` shell commands) is refused unless you pass `--allow-agent-config` after reading
  it; deeper copies are listed as warnings.

## Where it came from

The Cartographer started as a long-lived session in a multi-agent setup: one chat kept the catalogue in context, other
agents dropped briefs into a file mailbox, and a keep-alive ping every 55 minutes kept its prompt cache warm. That
worked, but it needed a chat kept open and a watcher to wake it. Prompt caching gives the same warm catalogue with a
plain request, so this version is a single call: no daemon, no mailbox, any backend.

## The bundled catalogue

The bundled skills are third-party work, fetched from each upstream repository at a pinned commit and kept byte for
byte (`.gitattributes` turns off line-ending conversion so the hashes hold on every OS). Each folder holds every file
in the skill's upstream folder except hidden tool folders such as `.github/`; nothing is edited. Skills were left out when their licence does not plainly
allow redistribution, or when their review had not finished.
