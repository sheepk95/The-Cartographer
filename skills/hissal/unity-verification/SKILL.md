---
name: unity-verification
description: Unity verification rules. Use when checking that a Unity change compiles or works, running Unity tests, building a player, running C# in the Editor, classifying Unity involvement for issue triage or selection, or when Unity cannot run here or the editor is locked.
---

# Unity verification

This repo's Unity config (`docs/agents/unity.md`), if present, overrides these defaults.

This skill decides which check runs, where, and how to read its result. What to test is `unity-testing`'s call; this skill runs it. For `unity` CLI syntax, search with `unity commands --grep <term>` first, then run `unity skill show` and `unity <command> --help`: the CLI is beta and moves every few weeks, so the commands named in this skill mark the traps, and their current form comes from the CLI.

## The Verification ladder

1. Text checks
2. Compile
3. Targeted tests
4. Full EditMode suite
5. PlayMode
6. Player build
7. CI

**Rung rule:** for each behaviour the change touches, or failure it risks, pick the cheapest rung that establishes it, and stop there. Rungs are not cumulative gates: a higher rung never requires every cheaper one first. The one prerequisite is that code compiles and changed assets import before anything runs them. The test rungs, the full EditMode suite at final review among them, run when `unity-testing`'s **Choosing tests** names them. A change is verified by the rungs it passed, each for what it established.

- **Compile** is a gate of each batch run, not a separate recurring check: a headless test run compiles first and fails on a compile error. With a connected editor, `unity recompile` is cheap enough to run more often. It also imports changed assets.
- **Focused inspection**: looking at the changed thing itself, by driving the scene through `unity-debugging` or as a manual check in the report. It is how an edit that changes no code behaviour (moving, restyling or rewording existing content) is checked after its import. Entering Play to inspect a scene or a prototype is a focused inspection, not the PlayMode rung.
- **Player build** runs only when the change can break a build-only path (`#if` and `UNITY_EDITOR` branches, `UnityEditor` in a runtime assembly, stripping or IL2CPP, platform defines), or when the user asks. It builds the Unity config's build targets, with its build method or profile, when the config names them.
- **Test filters**: the test rungs apply the Unity config's test filters, when it names any.
- **Heavy runs**: a full suite, a PlayMode run or a player build starts without warning, unless the Unity config turns the heavy-run warning on; then ask the user first.
- **Rung commands**: when the Unity config maps a rung to a repo command, run that command for the rung instead of the generic CLI path. A rung with no command falls back to the default. A compile-only (Roslyn) check is not a default rung; it runs only when a rung command names one.
- **Reused evidence**: a result stands, with the revision it ran on, until a later edit touches what it established; only then does that rung run again.
- **Unrelated failures**: a failure the change could not plausibly cause, and that does not block the check at hand, goes in the report as a known failure and gets its own investigation, never one inside this change.

## Where Unity runs

Take the first environment available, in this order. [ENVIRONMENTS.md](ENVIRONMENTS.md) has detection, the capability table, a pending editor and Safe Mode.

1. **Connected editor**: an open editor with `com.unity.pipeline`, driven through `unity recompile` and `unity command --project-path <project>`. Fastest, and it holds the project lock, so it is the only route while the user's editor is open. Unity MCP is deprecated in favour of this CLI route; use it only where the CLI cannot run.
2. **Headless**: `unity test`, `unity build`, `unity run`, when an editor is installed, no editor holds the project, the Unity config's allowed environments permit launching one, and a licence is available.
3. **Neither**: run the text checks, then hand off: name what the user or CI should run.

Hard rules, in every environment:

- Leave the user's editor running. Only the user closes it.
- Launch batch mode only against a project no editor holds. A project that is already open means driving that editor, or handing off.
- Leave licences alone. A licence failure is an environment gap, reported as one, never a code failure; the user activates or returns licences.

An open editor without Pipeline gets one mention per conversation that `unity pipeline install` unlocks the connected route, then carries on down the list.

**Resident headless editor** (batch mode without `-quit`, serving Pipeline commands): only when the Unity config allows it. Otherwise each headless check is one CLI launch. When you start one, name it in the report and stop it when done; ask before stopping one you did not start.

**New checkout**: a checkout with no `Library/` needs one before its first run, and keeps its own copy rather than sharing or linking another checkout's.

- **Warm copy**, the default when another checkout of the same project has a `Library/`: copy it into the new checkout before Unity first opens it. Use a parallel copy (`robocopy <src> <dst> /E /MT` on Windows), since a file-by-file copy of a large `Library/` can take longer than the import it saves. Prefer a source no editor holds, since an editor can write mid-copy. Delete `EditorInstance.json` and `ProtocolInstance.json` from the copied `Library/` when present: they mark the source as open, and the CLI refuses the copy as already open. The first run then recompiles scripts once and reimports only what differs between the two commits.
- **Cold import**, when no warm checkout exists: ask the user once before the first run (a full import can take many minutes), unless the Unity config says cold imports are fine. A run that creates several worktrees asks once for all of them and runs their cold imports one at a time: on a 15 GB machine, two at once ran out of memory and crashed the editor. Warm runs in separate checkouts can run side by side (observed on one Personal licence).

## Reading results

A result is green only when it names a nonzero test count and zero failures, from a compile that finished clean. Exit codes and envelopes lie in both directions: `unity test` exits 0 when a filter matched nothing, a connected `run_tests` exits 0 on a failing test, and a connected run started before its compile finished tests the old code. Read [READING-RESULTS.md](READING-RESULTS.md) before trusting any Unity result.

Running C# in the Editor (a validation script, a probe, a scope script another Unity skill ships): see [RUNNING-CSHARP.md](RUNNING-CSHARP.md).

## CI

Leave pushing and triggering CI to the user. Name the rungs CI would cover and which workflow runs them (the Unity config's authoritative CI workflow, else "CI, if the repo has one"); those rungs stay unvalidated. If the user already pushed, read the run's result from the CI host (`gh run view` on GitHub Actions) and report it as that rung.

## Report

Every verification ends with a report:

- **Ran**: each rung or focused inspection run or reused, with the environment, the revision and the result (for tests, the counts).
- **Skipped**: each rung the risk needed that did not run, with the environment gap that stopped it (no editor, locked project, no licence, cold import declined, CI not triggered).
- **Unvalidated**: each behaviour or risk whose rung did not run.
- **Known failures**: unrelated failures seen, left uninvestigated.
- **Manual checks**: what no rung can judge (feel, visuals, audio, timing), as concrete steps for the user.

## Slicing work into tickets

A ticket's acceptance criteria name the rungs it needs and whether any needs a connected editor. What runs where: text checks anywhere, including a cloud agent; compile and tests with a local editor, headless or connected; driving live scenes only with a connected editor; judging feel, visuals or a device only with a human (those tickets take the `ready-for-human` triage role). An agent claiming a ticket first checks it can reach the named rungs, and passes the ticket up if it cannot, rather than claiming it done.

For issue creation, triage or selection, read [ISSUE-CLASSIFICATION.md](ISSUE-CLASSIFICATION.md) for the optional Unity involvement classification and its repo mapping.
