# Environments

What each environment can run, how to tell which one you are in, and the traps of each.

## Capabilities

| Rung | Connected editor | Resident headless | Headless CLI (editor closed) | Cloud agent (no Unity) | CI runner |
|---|---|---|---|---|---|
| Text checks | Yes | Yes | Yes | Yes | Yes |
| Compile | `unity recompile` | `unity recompile` | Folded into the test or build run; alone, a batch import (`unity run` with no method), which exits 6 on a compile error | No | Yes |
| Targeted tests, full EditMode | `run_tests` | `run_tests` | `unity test` | No | Yes |
| PlayMode | `run_tests` in PlayMode | `run_tests`; without a graphics device, rendering-dependent tests may fail | `unity test` | No | Yes, GPU caveats |
| Player build | Possible; a batch job is usual | Possible | `unity build` | No | Yes |
| Running C# in the Editor | `run_script`, `eval` | `run_script`, `eval` | `-executeMethod` | No | `-executeMethod` |
| Costs | Nothing extra | A licence seat while it lives | Editor start per run (about a minute on a tiny warm project), a licence seat | Installing an editor plus a licence, with no documented unattended route for Personal | The repo's CI minutes |

A connected editor verifies its in-memory state, which can differ from disk (unsaved scenes), and a modal dialog blocks it.

## Detecting the environment

1. **Is an editor connected?** `unity status --format json` lists every editor running Pipeline, GUI or resident headless, with its project path and `state`. Every failure exits 6, so tell them apart by `errors[0].code`:
   - `STATUS_NO_INSTANCES`: no editor with Pipeline found for the project, or the CLI could not locate it (run from the project folder or pass `--project-path`). It cannot see an editor without Pipeline, so an editor may still hold the project.
   - `STATUS_PIPELINE_LOAD_PENDING`: an editor holds the project with Pipeline in its manifest, but nothing is serving. It is still opening or importing, it needs a refresh to load a newly added package (see [Pending editor](#pending-editor)), or it is in [Safe Mode](#safe-mode).
   - `STATUS_NOT_READY`: still starting.
   - `STATUS_ALL_UNREACHABLE`: every editor found is unreachable, such as one with a stale heartbeat.

   To wait for an editor to come up, run `unity status --until-ready --timeout <seconds>`; on timeout it exits 6 with the last state it saw.
2. **Is the project locked?** `unity test` against a project an editor holds refuses in seconds with exit 6 and "already open in a running Editor (PID n)", and changes nothing (other headless commands are expected, not confirmed, to refuse the same way). That refusal is the lock check: drive the open editor instead (install Pipeline if it lacks it) or hand off.
3. **Can an editor launch here?** `unity` on PATH, the project's editor version installed (`ProjectSettings/ProjectVersion.txt`), the Unity config's allowed environments permitting it, and an active licence (`unity license` lists them). Any missing piece is an environment gap: text checks and hand-off.

Pass `--project-path` on every Pipeline command whenever more than one editor may be open; per the CLI reference, an ambiguous target fails with `AMBIGUOUS_EDITOR`.

## The Pipeline nudge

An editor open on the project without `com.unity.pipeline` forces a hand-off for every Unity rung, which is why the nudge is worth its one mention. Installing it is the user's decision: it adds a package to their manifest.

## Pending editor

`STATUS_PIPELINE_LOAD_PENDING` that persists after the editor has finished opening (typically after `unity pipeline install` into an editor that was already open) means the editor has not loaded the package. Ask the user to switch to the editor. If they have Auto Refresh off (Preferences > Asset Pipeline), focus is not enough: they need Assets > Refresh (Ctrl+R). Then re-run `unity status --until-ready`. If a refresh does not clear it, check for Safe Mode.

## Safe Mode

A GUI editor that opens with C# compile errors boots into Safe Mode: packages do not load, so Pipeline serves nothing. `unity status` reports `STATUS_PIPELINE_LOAD_PENDING`, and connected commands fail (`unity recompile` exits 7, "No Pipeline instance found for project"). Recognise it by a pending state that a refresh does not clear, together with `error CS` lines and `Safe Mode` in the project's Editor log (see [READING-RESULTS.md](READING-RESULTS.md)), or `SAFE MODE` in the editor's window title. `unity pipeline list` may not report it (on 6000.6 it read `safeMode: null` for an editor in Safe Mode), so its negative proves nothing.

Recover by fixing the source, then asking the user to refresh the editor (Assets > Refresh, or switching to it when Auto Refresh is on). The same editor leaves Safe Mode in place, with no restart. Batch mode never enters Safe Mode; it exits on compile errors instead.

## Resident headless editor

Launch the editor binary in batch mode without `-quit` on a project no editor holds (`unity editors --installed --json` gives each editor's binary path). Wait for it with `unity status --until-ready`; once ready it serves the same commands as a connected editor.

- Stop it with `EditorApplication.Exit(0)` run through `run_script` (see [RUNNING-CSHARP.md](RUNNING-CSHARP.md)). The call that stops it reports `COMMAND_FAILED` ("Invalid response format") because the editor quits before replying; confirm the stop with `unity status`.

## Cloud agents and licences

A cloud agent without Unity stops at text checks and hands off. Installing an editor there does not help without a licence: Personal has no documented unattended activation, and service accounts cannot activate. A licence failure (CLI exit 4, or exit 6 when the editor could not acquire a licence) is reported as an environment gap.
