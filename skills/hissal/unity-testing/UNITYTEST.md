# Beyond `[Test]`

Reach for these only when a plain `[Test]` cannot express the behaviour.

## `[UnityTest]`

- Returns `IEnumerator`; `yield return null` skips one frame (one `EditorApplication.update` in EditMode). Use it only to wait frames (PlayMode) or to yield Editor instructions (EditMode).
- **EditMode yields**: `null`, an `AsyncOperation`, or an Editor instruction: `EnterPlayMode`, `ExitPlayMode`, `RecompileScripts`, `WaitForDomainReload`. Runtime waits do not wait there: `yield return new WaitForSeconds(1.5f)` returned after 0 ms (observed on 6000.6.2f1). Wait in PlayMode, or count frames.
- **PlayMode yields**: `WaitForSeconds`, `WaitForFixedUpdate`, `WaitUntil` and the rest work. Yielding an Editor instruction from a PlayMode test throws. Unity calls long waits bad practice; mark a slow test `[Explicit, Category("<name>")]` so the default run skips it.
- `[UnitySetUp]` and `[UnityTearDown]` are the `IEnumerator` forms of `[SetUp]` and `[TearDown]` (plus `[UnityOneTimeSetUp]`/`[UnityOneTimeTearDown]` from Test Framework 1.5).
- `MonoBehaviourTest<T>`: yield one to create a MonoBehaviour implementing `IMonoBehaviourTest` and wait until its `IsTestFinished` is true.
- The default timeout for a Unity test is 180 s, per the Test Framework source; `[Timeout(ms)]` overrides it.

## Domain reload inside a test

An unexpected domain reload during a test fails it. A test that recompiles or enters Play mode on purpose yields `RecompileScripts` or `EnterPlayMode` from EditMode. After such a reload, only `[SerializeField]` fields of the fixture keep their values, and the plain `[SetUp]`/`[OneTimeSetUp]` run again while the Unity ones do not.

## Async tests

- `[Test] public async Task Name()` works (Test Framework 1.3 and later), in both modes; so do `async Task` `[SetUp]` and `[TearDown]`. The task runs on the main thread, polled each frame.
- **Await an `Awaitable` inside an `async Task` test.** An `async Awaitable` test method is not supported: its body ran to the end, then the runner failed the test with a `NullReferenceException` from NUnit's async handling, hiding the body's own result (observed on 6000.6.2f1).
- Never `Assert.ThrowsAsync`: it blocks the main thread and freezes the Editor. `try`/`await`/`catch`, then assert on what was caught.
- Error logs are checked only after an async test completes.

## Scene tests

- **EditMode**, scene content (every level has a spawn point): `EditorSceneManager.OpenScene(path)` in the test, and `EditorSceneManager.NewScene(NewSceneSetup.EmptyScene)` in `[TearDown]` to leave the scene behind. Never save the opened scene.
- **PlayMode**, scene behaviour: `SceneManager.LoadScene(name)`, then yield at least one frame before asserting, since the load is not immediate. Unity's `LoadScene` docs require the scene to be in the build profile (not yet checked in the sandbox).
