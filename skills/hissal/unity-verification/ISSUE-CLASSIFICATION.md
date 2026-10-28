# Unity involvement in issues

For issue creation, triage and selection, read the consuming repo's Unity config and the conventions it points at. Unity involvement classification is optional: without an adopted convention or an enabled config field, leave it disabled. An explicit `disabled` overrides a discovered convention. Classify when enabled; follow the repo's tracker conventions for reading and updating the recorded value.

## Meanings

Classify the minimum Unity involvement required to complete the whole issue, including implementation and required verification. Use the highest required level:

| Level | Requirement |
|---|---|
| `none` | Completion and required verification need no Unity execution. |
| `headless` | Completion requires Unity execution, and headless execution is sufficient. |
| `interactive` | Completion requires interaction with or observation of a Unity Editor or player beyond headless execution. Required visual checks count as interactive. |

Interactive work may be performed by an agent or a human. Determine human involvement and readiness separately from the repo's existing rules; this classification does not change triage-role definitions. Automated tests or a player build can be headless, and using an open Editor for a check that could run headless does not raise the requirement.

## Repo representation

Default label names, when a repo adopts labels, are `unity:none`, `unity:headless` and `unity:interactive`. The Unity config may map different labels, fields or combinations of metadata to these meanings through Markdown rules and tables, or point to the repo's canonical convention or classifier command. Follow that convention for updates and permissions; preserve existing representations instead of adding duplicate labels.

If a repo's definition conflicts with these meanings, surface the disagreement and resolve it with the user before applying a classification. Keep the recorded value visible while reporting the discrepancy.

## Creation and triage

- Read the whole issue and its required verification. Use the repo's classifier when configured, then check whether its result covers the issue's actual requirements.
- When evidence is sufficient, propose the level with a short reason in the issue or brief and record it through the workflow's normal approval and write steps.
- Missing classification means unknown, never `none`. Unclear requirements stay unknown until triage resolves them.
- Multiple levels, or a recorded level contradicted by an explicit requirement, are inconsistent. Name the evidence and propose a correction during triage.
- Reassess when scope or acceptance criteria change. Available tools in the current session do not change the issue's requirement.

## Selection

Apply the requested level filter through the repo's configured representation. For work requiring no Unity, include only confirmed `none` issues. Report unknown candidates separately rather than silently classifying or updating a backlog. Exclude inconsistent issues from filters that depend on a trustworthy level, explaining the discrepancy.

Check repo readiness, unresolved blockers and current capabilities separately before recommending an issue as actionable. Report a missing capability without changing the recorded requirement or readiness. When classification is disabled, selection may still reason about required checks, but cannot treat an absent value as a confirmed level.
