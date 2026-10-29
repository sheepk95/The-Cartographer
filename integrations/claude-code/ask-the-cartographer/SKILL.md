---
name: ask-the-cartographer
description: At the start of every distinct task, ask The Cartographer which skills to read before doing the work. Use before planning or writing code for a new task, before handing a task to a helper or subagent, and whenever you are unsure which skill covers what you are about to do.
---

# Ask the cartographer

Before you start a new task, run:

```bash
cartographer ask --from "<who you are>" "<what the task is, in 2-10 lines>"
```

(Or call the `ask_cartographer` tool if the `the-cartographer` MCP server is connected.)

Then:

- Read every skill under `PICKS:` in full before you start. For a pick marked `read: LARGE read in parts`, read it in
  parts (offset/limit) or search it for your topic; never skip it.
- Read only the first 40 lines of each `MAYBE:` skill, and the rest only if it fits.
- `PICKS: none` means no skill is needed: carry on.
- If the answer has `ALSO GREP:`, run `cartographer search <those words>` once.
- If the command prints `CARTOGRAPHER_UNAVAILABLE`, run `cartographer search <2-4 task words>` and read what fits. Never
  block on the cartographer.

When you hand work to helpers, ask once for all of them (list every helper's task in one brief) and put each helper's
picks in its brief, so they do not each ask again.
