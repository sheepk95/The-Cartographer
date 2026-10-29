# Add to your AGENTS.md (~/.codex/AGENTS.md or a project's AGENTS.md)

## Skills: ask the cartographer first

At the start of each distinct task, call the `ask_cartographer` tool from the `the-cartographer` MCP server (or run
`cartographer ask --from "<who>" "<the task, 2-10 lines>"`) and read the SKILL.md files it lists under PICKS before you
start; read the first 40 lines of each MAYBE. If your sandbox cannot open a listed path, use the `read_skill` tool.
`PICKS: none` means carry on. If the cartographer is unavailable, use the `search_skills` tool instead.
