# Add to your CLAUDE.md (user-level ~/.claude/CLAUDE.md or a project's CLAUDE.md)

## Skills: ask the cartographer first

At the start of each distinct task, run `cartographer ask --from "<who>" "<the task, 2-10 lines>"` (or call the
`ask_cartographer` MCP tool) and read the SKILL.md files it lists under PICKS before you start; read the first 40 lines
of each MAYBE. `PICKS: none` means carry on. On `CARTOGRAPHER_UNAVAILABLE`, run `cartographer search <2-4 task words>`
instead. A coordinator asks once for all its helpers and puts each helper's picks in that helper's brief.
