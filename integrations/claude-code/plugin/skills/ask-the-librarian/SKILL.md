---
name: ask-the-librarian
description: At the start of every distinct, non-trivial task, ask The Librarian which skills to read before doing the work. Use before planning or writing code for a new task, before handing a task to a helper or subagent, and whenever you are unsure which skill covers what you are about to do.
---

# Ask the librarian

Before you start a new task that is more than a quick answer, call the `ask_librarian` tool from The Librarian's MCP
server with a 2-10 line brief of the task (`brief`) and who is asking (`from`).

Then:

- Read every skill under `PICKS:` in full before you start. For a pick marked `read: LARGE read in parts`, read it in
  parts or search it for your topic; never skip it. If you cannot open a listed path, use the `read_skill` tool.
- Read only the first 40 lines of each `MAYBE:` skill, and the rest only if it fits.
- `PICKS: none` means no skill is needed: carry on.
- If the answer has `ALSO GREP:`, call `search_skills` once with those words.
- If the tool fails or says `LIBRARIAN_UNAVAILABLE`, call `search_skills` with 2-4 task words and read what fits.
  Never block on the librarian.

When you hand work to helpers, ask once for all of them (list every helper's task in one brief) and put each helper's
picks in its brief, so they do not each ask again.
