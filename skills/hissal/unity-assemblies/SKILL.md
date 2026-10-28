---
name: unity-assemblies
description: Unity assembly and compilation rules. Use when creating, moving or deleting a script folder or an `.asmdef`/`.asmref`; editing assembly references or scripting defines; using `UnityEditor` or `#if` in runtime code; or on a compile error about a type that exists, or a Player build failing where the Editor compiles.
---

# Unity assemblies

This repo's Unity config (`docs/agents/unity.md`), if present, overrides these defaults.

Which assembly each script compiles into, what it can see, and when it compiles. Neighbours: script renames and `.meta` identity are `unity-serialization`'s; test assembly templates are `unity-testing`'s; domain reload and statics are `unity-code-lifecycle`'s; how to compile, build and read the result is `unity-verification`'s.

## Stance

Assembly layout is the user's call. Add, split, merge or move an asmdef only when asked. When a change needs one (code has to leave `Assembly-CSharp` to be tested, or an Editor folder needs its own assembly), stop and propose it:

- the folder the asmdef goes in, and the assembly name (the Unity config's naming convention, else reverse-DNS matching the existing asmdefs);
- every `Assembly-CSharp` type the moved code uses, since each must move too;
- the assemblies that will reference the new one, and the ones it references.

The Unity config's layout policy, when set, answers these without asking. A script added to an existing folder needs no proposal: it joins its neighbours' assembly.

## The traps

- **No asmdef means `Assembly-CSharp`.** A script in no asmdef's folder compiles into a predefined assembly: `Assembly-CSharp`, or `Assembly-CSharp-Editor` inside an `Editor` folder (`-firstpass` variants under `Plugins`). An asmdef takes its folder and every subfolder, except one with its own asmdef or asmref. Inside a package, a script outside every asmdef is not compiled at all: the Editor log says so, and nothing fails.
- **Asmdef code never sees `Assembly-CSharp`.** A reference to it is dropped without a warning, `autoReferenced: false` included, and the code fails to compile. The other way round, per Unity's docs, predefined assemblies see only asmdefs with `autoReferenced: true`.
- **An asmdef swallows nested `Editor` folders.** Under an asmdef, an `Editor` folder is just a folder: its scripts join the runtime assembly, compile in the Editor, and break the Player build at their first `UnityEditor` call (the `using` line alone passes).
- **`UnityEditor` passes the Editor compile and fails the Player build**, whether it comes from an Editor API call in a runtime assembly or from a runtime asmdef referencing an Editor-only one.
- **Test assemblies never ship.** An assembly referencing the test runner, with `UNITY_INCLUDE_TESTS` in its `defineConstraints` as the test templates have, is left out of normal builds, so production code inside one vanishes from the Player. Test assemblies hold tests only.
- **Cycles are compile errors.** Two assemblies referencing each other cannot compile: move the shared types into one assembly, or split them out into a third both reference. The cycle is named only in the console ("cyclic dependencies detected between assemblies"), not among the compile errors.
- **A type that exists but "could not be found"** (CS0246, CS0234 "are you missing an assembly reference?", or CS0103) usually means a missing reference, not a missing type: find the type's assembly and whether this one lists it.
- **A reference that resolves to nothing is dropped silently**, with no error or warning: a typo'd name or a stale GUID fails only when code uses a type from it. The script below marks such references.

## Editor and runtime code

Match the module's existing pattern. With no precedent:

- A few Editor-only lines inside a runtime file: wrap them, and their `using UnityEditor`, in `#if UNITY_EDITOR`.
- Whole Editor files: an `Editor` folder. When a parent folder has an asmdef, that `Editor` folder gets its own asmdef with `"includePlatforms": ["Editor"]` (or an asmref to an existing Editor-only assembly).

References always point from Editor to runtime. A runtime assembly never references an Editor-only one.

## GUIDs

- Write references as `"GUID:<guid>"`. Use name references only when the asmdef being edited already uses names: match the file.
- A new `.asmdef` or `.asmref` gets a hand-written `.meta` with a freshly generated GUID (template in [ASMDEF.md](ASMDEF.md)), so it can be referenced at once, with no import round trip. Every other new asset keeps the `.meta` Unity generates.
- Unity deletes a `.meta` whose asset is missing when it refreshes. So write both files in one command, `.meta` first; re-read the `.meta`; if its GUID changed, adopt Unity's (nothing references it yet); only then write references to it.

Map names and GUIDs with [scripts/asmdefs.sh](scripts/asmdefs.sh) (bash and grep): run it from the Unity project or package root, or pass the root. It prints one tab-separated line per assembly, `name`, `guid`, `path`, `references`, with each reference resolved to a name; `?` marks one that resolves to nothing, and `no-meta` an asmdef without its `.meta`. Grep its output either way. Registry and git packages live only in `Library/PackageCache/`: without it (a checkout never opened in Unity) the script says so, and references into packages print unresolved. Without the script:

- name to GUID: `grep -rl --include='*.asmdef' '"name": *"<name>"' Assets Packages Library/PackageCache`, then the `guid:` line of that file's `.meta`;
- GUID to name: `grep -rl --include='*.asmdef.meta' 'guid: <guid>' Assets Packages Library/PackageCache`, then the `name` in the asmdef beside it.

## Defines

- **Optional-package integration**: put it in its own asmdef with a `versionDefines` entry that defines a symbol when the package is installed, and name that symbol in `defineConstraints`. The assembly compiles with the package and disappears without it; no project-wide symbol. Syntax in [ASMDEF.md](ASMDEF.md).
- **Project-wide symbols** only when the user asks, in the mechanism the repo already uses (the Unity config names it; else whichever of `csc.rsp`, Player Settings or build profiles already holds symbols). Set symbols and build in separate steps: per Unity's docs, a symbol set from script reaches the compile only after the Editor regains control and recompiles, and batch mode never recompiles for new symbols, so a headless run must get them from `csc.rsp` (or the saved settings) at startup. Syntax and scopes in [ASMDEF.md](ASMDEF.md).

## Recompiling

Per Unity's docs, it recompiles on an Asset Database refresh after a `.cs`, `.asmdef`, `.asmref`, `.rsp` or DLL change, after a define symbol change, and after switching the build target. A GUI editor refreshes when it regains focus (with the default Auto Refresh), so files written from outside can sit unimported and uncompiled while it idles. Get a finished compile before trusting any result after such a change; `unity-verification` owns how.

Only changed assemblies and their dependents recompile: that is what an asmdef buys.

## Naming and language

- One MonoBehaviour or ScriptableObject per file, the file named exactly like the class, one namespace per file. Renaming the class renames the file, keeping its `.meta`; that rename's rules are `unity-serialization`'s.
- C# 9 on Roslyn, per Unity's docs without init-only setters, covariant returns or module initializers; records need a hand-declared `IsExternalInit` and are never serialized.
- Analyzers and source generators: [ANALYZERS.md](ANALYZERS.md).

## Seams at assembly boundaries

An assembly boundary is a seam with its own rules: `internal` types stay inside the assembly; `[assembly: InternalsVisibleTo("<asmdef name>")]` (in an `AssemblyInfo.cs` beside the asmdef) opens them to one named assembly, usually its tests; references run one way, and never from runtime into Editor. Deepening a module across a boundary changes asmdef references: propose it, per the stance above.

**Friction signal, asmdef tangles**: assemblies that reference nearly everything, near-cycles worked around with interfaces or events, Editor-only references from runtime code, one feature's types spread over many assemblies, or a split that forces `public` on what should be `internal`.

## Validation

Name these checks, then call the Skill tool with "unity-verification" to run them.

- **Text checks**, from `scripts/asmdefs.sh` and grep: every reference resolves (no `?`); no cycle among the changed assemblies' references; no runtime asmdef references one with `"includePlatforms": ["Editor"]`; every `Editor` folder under an asmdef's folder has its own Editor-only asmdef or asmref; every `using UnityEditor` in a runtime assembly sits inside `#if UNITY_EDITOR`; no production code in a test assembly; no `no-meta` on a new asmdef.
- **Compile** is the minimum after any asmdef, reference or define change.
- **Player build** when the change touched the Editor/runtime split or defines. Without one, the Player side is reported unvalidated.
