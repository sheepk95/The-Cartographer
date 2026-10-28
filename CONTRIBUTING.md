# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Set up

```bash
pip install -e ".[api]"
python -m unittest discover -s tests
python tools/vendor.py verify
librarian doctor
```

The tests call no model and use no network, so they run offline and cost nothing. To try a change end to end without
a model, point the `command` backend at any script that prints a fixed answer:

```bash
librarian ask --command "python my_stub.py" "fix a flaky test"
```

The finder and installer tests are in `tests/test_finder.py`. They serve skills.sh pages, sitemaps, GitHub API
answers and tarballs from fixtures in the test file, and the real network is switched off for the whole module (the
module sets `LIBRARIAN_NO_NETWORK`, which also reaches the subprocesses it starts): a test that tries to reach it
fails. Run them alone with:

```bash
python -m unittest discover -s tests -p "test_finder.py"
```

To try the finder by hand without touching your real cache or skills folder, point `LIBRARIAN_CACHE` at a scratch
folder, use `librarian find --offline` once a cache exists (or set `LIBRARIAN_NO_NETWORK=1` to be sure nothing is
sent), and install with `--dest <scratch folder>`.

## Code changes

- Python 3.9+, standard library only. The `anthropic` SDK stays optional (the `[api]` extra).
- Keep the catalogue text deterministic: sorted, no dates, no machine-specific values in the prompt. The prompt cache
  depends on the same skills giving the same bytes.
- Keep the answer format stable. Agents and scripts parse it, and the end line `--- end of librarian answer ---` is
  how they tell a complete answer from a cut-off one.
- Add a test for anything that changes parsing, checking or a backend's command line.
- The finder and installer tests use a fake skills.sh and fake tarballs; keep them offline. A safety check (robots,
  the URL whitelist, rate limits, licence refusals, never overwriting, never running a download) needs a test that
  fails when the check is removed: break the check once, watch the test go red, then restore it.

## The bundled skills

Files under `skills/` are third-party work, kept byte for byte at a pinned upstream commit. Pull requests that edit
them can't be merged: `tools/vendor.py verify` checks every file against its SHA-256 in `catalogue/bundled.json`, and
`THIRD_PARTY_NOTICES.md` is generated from that file (`python tools/vendor.py notices`).

To propose a skill for the bundle, open an issue with:

- the upstream repository, the commit, and the skill folder's path;
- its licence, which must plainly allow redistribution (the bundle today has MIT, Apache-2.0, CC-BY-SA-4.0 and
  Unlicense; non-commercial, unknown and vendor-restricted licences are left out);
- what kind of task it is for, and whether its description says so clearly enough for a model to pick it.

A fix to a bundled skill belongs upstream. Once it lands there, an issue asking to move the pin to the new commit is
welcome.

## Reporting problems

Bugs: open an issue with the command you ran, the output, `librarian doctor`, and your OS and Python version. A wrong
or missed pick is worth reporting too: include the brief and the answer. Security problems: see `SECURITY.md`.
