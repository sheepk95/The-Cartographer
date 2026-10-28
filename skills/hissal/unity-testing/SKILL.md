---
name: unity-testing
description: Unity test rules. Use when writing, choosing or reviewing Unity tests, setting up a test assembly, choosing EditMode or PlayMode, sketching test seams for Unity code, or when a Unity test fails in a way plain C# would not.
---

# Unity testing

This repo's Unity config (`docs/agents/unity.md`), if present, overrides these defaults, including its **Testing** fields (test assembly layout, mocking library).

This skill decides what to test and what to run: the mode, the test assembly, the tests that cover a change. How a run launches and how to read its result is `unity-verification`'s: call it through the Skill tool for every run. Moving code out of `Assembly-CSharp` is `unity-assemblies`' proposal to make; static state on the production side is `unity-code-lifecycle`'s.

## Mode rule

- **EditMode `[Test]` by default.** It runs synchronously, needs no Play mode, and is the fastest loop.
- **PlayMode** only when the behaviour needs the engine running: the MonoBehaviour lifecycle, frames passing, physics, or a loaded scene.
- **Player tests** only when the user asks.

The mode belongs to the test assembly, not the test: an asmdef with `"includePlatforms": ["Editor"]` holds EditMode tests, any other holds PlayMode tests. Test assemblies, their templates and setting up the first one: [ASSEMBLIES.md](ASSEMBLIES.md). `[UnityTest]`, yield instructions, async tests and scene tests: [UNITYTEST.md](UNITYTEST.md).

## The humble MonoBehaviour

The humble object pattern, Unity's form: logic lives in plain C# classes, tested directly in EditMode; a MonoBehaviour exists only where the engine needs one (a component in a scene, a lifecycle callback, a serialized reference) and forwards to them. A humble MonoBehaviour is too thin to need a test of its own. This is the default seam for Unity code, and the one to offer when agreeing seams.

**The engine as a dependency.** Engine services the logic reads (`Time`, `Input`, `Random`, physics queries) sit behind the repo's own port: an interface the logic takes, a Unity-backed adapter the MonoBehaviour passes in, and a fake the EditMode tests pass in. What only the real engine can show (a collision, a frame's ordering, a scene's wiring) goes to a PlayMode test against the real engine.

**Mocking** uses the library the Unity config names, else hand-written fakes. Whatever the library, put the repo's own interface at the seam and fake that, never a UnityEngine type.

C# versions of `tdd`'s good and bad tests, and of its mocking examples: [EXAMPLES.md](EXAMPLES.md).

## EditMode traps

- **No lifecycle.** A plain MonoBehaviour added in an EditMode test gets no `Awake`, `OnEnable`, `Start` or `Update`, not even across `yield return null`. Call its public (or `internal`, with `InternalsVisibleTo`) methods directly, which works, or test it in PlayMode. In PlayMode, `Awake` and `OnEnable` run inside `AddComponent`, and `Start` and `Update` after one `yield return null`.
- **`DestroyImmediate` in EditMode.** `Object.Destroy` there logs "Destroy may not be called from edit mode!", leaves the object alive, and fails the test. In PlayMode `Destroy` is deferred: the object is still non-null until the next frame.
- **Any unexpected error log fails the test**, `Debug.LogError`, an exception log and an assertion log alike. A test that expects one calls `LogAssert.Expect(LogType.Error, "<message or Regex>")` before the code that logs: the check runs at the end of each frame, so an expectation placed after a yield comes too late and the test fails.
- **Cleanup beyond Undo.** The EditMode runner opens a fresh scene and afterwards reverts Undo-recorded changes, which covers little: GameObjects a test creates are destroyed in its `[TearDown]`, and files, assets and settings it writes are deleted or restored by it too.

## Static state in tests

Write tests as if domain reload is off, whatever the project setting, unless the user or the Unity config says it does not matter: reset every static the test touches in `[SetUp]`, and never rely on a fresh domain between tests. Tests in one run share one domain, and a PlayMode run is one Play session, so a static set in one test is still set in the next whether domain reload is on or off. In an open editor, statics also outlive the run: nothing reloads the domain between two runs unless code recompiles. The reason, and the production side (giving each static a reset path), are `unity-code-lifecycle`'s: a suite that already resets its statics survives a switch to reload off, or to CoreCLR, with no migration.

## What tests cannot judge

Feel, visuals, audio and timing that a human perceives are out of a test's reach. Extract the testable logic from under them (the jump curve's numbers, the state that picks the sound), test that, and hand the rest to `unity-verification`'s report as concrete manual checks: what to open, what to do, what to look or listen for.

## Choosing tests

- **During the loop**: the test assemblies of the module being changed, only.
- **At final review** of a completed code change or a prototype's promotion into production code: the full EditMode suite, once. Not for each iteration or a prototype hand-off.
- **PlayMode**: only when a changed contract needs the engine running (the mode rule) and EditMode cannot establish it. Existing PlayMode tests in the module are not a reason on their own; logic kept behind a humble MonoBehaviour stays in EditMode.
- **No code behaviour change** (moving, restyling or rewording existing content): no tests; `unity-verification`'s focused inspection checks it.

Pass these to `unity-verification` as the assemblies or fixtures to run; the filter syntax is its concern.

## Run cadence

`tdd`'s "one slice at a time" holds: each slice is one seam, one test and one minimal implementation. What changes in Unity is how slices share a run, never a cycle.

- **With a connected editor** (`com.unity.pipeline`), runs are cheap: run plain one-slice red/green cycles, exactly as `tdd` writes them.
- **When each run is a cold headless launch**, editor startup dominates. Batch independent slices (neither touches the other's code or behaviour): one run shows the batch red, one shows it green, and a green run may carry the next batch's red tests.
- **The red run is never dropped**, batched or not: it is what exposes a tautological test.
- **Dependent slices stay sequential**: a slice whose test or code builds on another's waits for that one's green.

## Sketching test seams for a spec

For each behaviour, name the plain C# class that owns it and its EditMode `[Test]` seam; mark as PlayMode only what needs the engine running (per the mode rule); name each engine service that needs a port; and list what tests cannot judge as manual checks.

## Friction signals

When scanning Unity code for architectural friction, the signals this skill owns: logic stuck in MonoBehaviours, out of EditMode's reach; and scene lookups (`Find*`, `FindObjectOfType`) standing in for dependencies that could be passed in. Report where they are; changing the design is the user's call.

## Reviewing test changes

Check each changed test against every EditMode trap and the static and mocking rules above, and each changed test assembly for:

- a test asmdef beside its tests, with the mode its tests need (EditMode `includePlatforms: ["Editor"]` for anything using `UnityEditor`), in the layout of [ASSEMBLIES.md](ASSEMBLIES.md);
- production code in a test assembly (it never reaches the Player).

## Validation

Name the tests per **Choosing tests**, then call the Skill tool with "unity-verification" to run them and report. A new test assembly adds the checks in [ASSEMBLIES.md](ASSEMBLIES.md).
