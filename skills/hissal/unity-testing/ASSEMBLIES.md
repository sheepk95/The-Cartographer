# Test assemblies

A test assembly is any asmdef that references NUnit. Tests cannot reference `Assembly-CSharp`, so the code under test must sit in its own asmdef.

## Templates

Write test assemblies in the explicit form below. The Editor's own templates and the Manual still use the legacy shorthand `"optionalUnityReferences": ["TestAssemblies"]`; write the references out instead, so the file says what it depends on.

**EditMode**, `<Module>.Tests.EditMode.asmdef`:

```json
{
    "name": "<Module>.Tests.EditMode",
    "rootNamespace": "<Module>.Tests",
    "references": ["GUID:<module guid>", "UnityEngine.TestRunner", "UnityEditor.TestRunner"],
    "includePlatforms": ["Editor"],
    "overrideReferences": true,
    "precompiledReferences": ["nunit.framework.dll"],
    "autoReferenced": false,
    "defineConstraints": ["UNITY_INCLUDE_TESTS"]
}
```

**PlayMode**, `<Module>.Tests.PlayMode.asmdef`: the same without `includePlatforms` (empty means every platform, which is what lets its tests run in Play mode and in a player) and without `UnityEditor.TestRunner`, which only EditMode assemblies can reference. Editor API calls inside it go in `#if UNITY_EDITOR`.

**Test helpers** shared by several test assemblies (builders, fakes, custom constraints): their own asmdef, shaped like the test assembly of the mode they serve, with no tests in it; each test assembly references it.

- `precompiledReferences` takes effect only with `"overrideReferences": true`.
- `UNITY_INCLUDE_TESTS` in `defineConstraints` keeps the assembly out of normal player builds, which is also why production code in a test assembly vanishes from the Player.
- Reference the module under test by `GUID:`, per `unity-assemblies`; the test runner assemblies by name, as above.

Observed on 6000.6.2f1: both templates compile and run (checked with a name reference to the module).

## The test framework package

`com.unity.test-framework` is a core package with its version fixed to the Editor's, but a project can still lack it: the URP blank template lists it, while a project created with bare `-batchmode -createProject` has no entry, and test assemblies then fail to compile. Before the first test assembly, read `Packages/manifest.json`. When the entry is missing, propose adding it (the version the Editor bundles) and wait; adding a package is the user's call.

## Setting up the first test assembly

1. **Code in `Assembly-CSharp`**: stop. Tests cannot see it, so it needs its own asmdef first; call the Skill tool with "unity-assemblies", which proposes the move (folder, assembly name, the other types that must move with it) and waits for the user.
2. **Check the manifest**, as above.
3. **Place it** where the Unity config's test assembly layout says. Without one, match the repo's existing test assemblies; with none, `<Module folder>/Tests/EditMode/<Module>.Tests.EditMode.asmdef` (and `Tests/PlayMode/` when PlayMode tests are needed).
4. **Write the asmdef and a hand-written `.meta`**, following `unity-assemblies`' GUID rule (template in its `ASMDEF.md`).
5. **Add one test** and run it through `unity-verification`.

Checks for a new test assembly: every reference resolves (`unity-assemblies`' `asmdefs.sh`), its `.meta` exists, and a run reports a nonzero test count from it. A count of zero means the runner never saw the assembly, however green the run looks.
