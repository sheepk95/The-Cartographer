# Running C# in the Editor

Two routes: a connected (or resident headless) editor runs a script live, and a headless launch runs a static method at startup. Take the connected route when one exists (see [ENVIRONMENTS.md](ENVIRONMENTS.md)). List a command's current parameters with `unity command --project-path <project> --query <name>`.

## Connected: `run_script` and `eval`

`run_script` compiles one project C# file in memory, with no domain reload, and calls a named static entry point (`--file`, a path relative to the project; `--entry`, `Class.Method`). Its return value comes back as `result.result`. `eval` runs a snippet the same way. Both run arbitrary code in the user's editor, gated by Pipeline's capability setting.

- Put a throwaway script **outside `Assets/`** (for example a scratch folder beside it in the project): `run_script` still finds it, and Unity never imports or compiles it into the project. Delete it when done.
- Check compilation first with `--dry_run true`, which compiles without loading or running anything. Read its verdict from `result.success` and `result.diagnostics`, not the exit code (see [READING-RESULTS.md](READING-RESULTS.md)).
- A script that throws, or returns an error, reports it in `result`; the CLI can still exit 0. Read `result` every time.
- `EditorApplication.Exit(code)` from `run_script` closes the editor: only for a resident headless editor you started, never the user's.

## Headless: `-executeMethod`

On a headless launch, `-executeMethod Class.Method` runs a static method from a compiled **Editor** assembly once the project has imported (through `unity run <project> -- -executeMethod Class.Method`; `unity skill show` has the current form, since `unity run` adds `-batchmode` and `-quit` itself).

- The method must live in the project's compiled code (an `Editor` folder or an Editor-only assembly), so it is a real project file: add it for the check and remove it after, with its `.meta`.
- Report failure through the exit code: throw (editor exit 1) or call `EditorApplication.Exit(nonZero)`; call `EditorApplication.Exit(0)` on success so the run ends deterministically.
- Write any structured output to a file the method names, or to the log with a tag you can grep; stdout is the log.
- A compile error anywhere in the project stops the run before the method runs (exit 6, `Scripts have compiler errors`).
