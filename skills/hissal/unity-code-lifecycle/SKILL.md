---
name: unity-code-lifecycle
description: Unity code lifecycle rules. Use when adding or changing static state, a singleton or a static event; writing code that runs on load, on a code reload, or on entering or exiting Play mode; or when state leaks between Play sessions.
---

# Unity code lifecycle

This repo's Unity config (`docs/agents/unity.md`), if present, overrides these defaults, including its **Code lifecycle** fields (domain reload does not matter here; the lifecycle API the repo prefers).

This skill makes statics, singletons and static events safe across Play sessions. Whether to use them at all is the repo's design call, made in its Unity config or conventions docs. Asmdefs and what triggers a recompile belong to `unity-assemblies`; resetting statics inside a test belongs to `unity-testing`.

## Stance: build as if domain reload is off

With domain reload off, a static keeps its value and a static event keeps its subscribers from one Play session into the next, and nothing runs a static constructor again. Write every static as if reload is off, whatever the project's Enter Play Mode setting, unless the user or the Unity config says it does not matter. The reason: any Unity version since 2019.3 can have reload off, 6.6 ships with domain reload off by default, and a project that turns reload off later, or moves to the CoreCLR runtime (which has no domain reload), then needs no migration.

This skill covers domain reload. With scene reload also off, scene objects are not recreated either, so their non-serialized fields persist too; the project's Enter Play Mode Settings (Project Settings > Editor) show which reloads are on.

## Picking the API

1. **Version.** When the choice matters, read the version from `ProjectSettings/ProjectVersion.txt`; a UPM package uses the minimum in its `package.json` `unity` field.
   - 6.5 or later: the lifecycle attributes and `[AutoStaticsCleanup]`.
   - Earlier: `[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]` on a static method for runtime code, `[InitializeOnEnterPlayMode]` for Editor code, each assigning every static back by hand. Both still work on 6.6 and neither is obsolete, so a package with a minimum below 6.5 uses them throughout. A dual path under `#if UNITY_6000_5_OR_NEWER` only when the user asks.
2. **Existing pattern.** Match the pattern already in the file or module you are touching. The new attributes go only into new code with no local precedent, or where the Unity config names them. Leave existing code on its API; mention the newer one at most once.
3. **Old to new, by what fires each Play session.** A `SubsystemRegistration` reset maps to `[OnEnteringPlayMode]` or `[AutoStaticsCleanup]`, never `[OnCodeInitializing]`: Unity's docs map it there by load timing, but with reload off `[OnCodeInitializing]` never fires on entering Play mode. Code that needs a specific load point keeps its `RuntimeInitializeOnLoadMethod` load type.

[LIFECYCLE.md](LIFECYCLE.md) has the eight lifecycle attributes, which callbacks fire with reload on and off, the observed orders, and the mapping from the older APIs.

## Reset rules (6.5 and later)

- **Default: `[AutoStaticsCleanup]` on the member**, for a static field, property or event that should return to its initializer. A source generator resets it on both entering and exiting Play mode: the initializer runs again (`= new()` builds a fresh instance), a member with no initializer gets `default`, and a `static readonly` collection (or any type with a parameterless `Clear()`) keeps its instance and gets `Clear()`. It needs no per-assembly opt-in.
- **`[OnEnteringPlayMode]`** on a static method, for what the generator cannot do: a reset that needs a method call, setup that lives in a static constructor (the generator never re-runs one), and real work on the transition (it also runs once at Player startup). `[OnExitingPlayMode]` only for state nothing touches in Edit mode. Keep each static under one mechanism, the attribute or a callback, because their order on the same transition is not documented.
- **A `static readonly` field whose type has no `Clear()` resets in `[OnEnteringPlayMode]`, never under `[AutoStaticsCleanup]`.** Under the attribute the generator throws, the compile passes with only warning `CS8785`, and the generator emits nothing for that whole assembly: every other `[AutoStaticsCleanup]` in it silently stops resetting.
- **Field-level by default.** `[AutoStaticsCleanup]` on the type only when every static in it is session state.
- **Deliberate persistence**: a static meant to survive Play sessions (a reflection cache, a lookup table) gets `[NoAutoStaticsCleanup]` on purpose, even where nothing else resets it, so the next reader and the text check see the choice. On a type-level `[AutoStaticsCleanup]`, it keeps that one member.
- **The declaring type is `partial`, always.** A lifecycle callback in a non-`partial` type fails with `UAC0031`; `[AutoStaticsCleanup]` in one fails with `CS0260`.
- The UAL analyzer (`UAL0010` to `UAL0014`) is off by default and turned on per assembly with a `<asmdefName>.globalconfig`. Leave the analyzer and any `.globalconfig` as the repo has them; mention the analyzer at most once, as an option.

## Which callback for what (6.5 and later)

- **Per-session state**: `[AutoStaticsCleanup]` for a plain reset, `[OnEnteringPlayMode]` for a reset or setup that needs a method call.
- **Once per code load** (a registry built from types, a reflection cache): `[OnCodeInitializing]`. It runs at Editor startup, after each recompile, on each Play entry with reload on, and at Player startup, but never on a Play entry with reload off, so the setup must be safe to run again and hold across sessions. Use it rather than `[OnCodeLoaded]`, which runs before the engine is ready in a player.
- **The static that load code fills gets `[NoAutoStaticsCleanup]`.** The `[AutoStaticsCleanup]` reset runs after `[OnCodeInitializing]` on every Play entry, reload on or off, and at Player startup, so a cleaned static filled there is already empty when Play mode code reads it.

## Static events and singletons

- **Static event**: reset to `null` on entering Play mode (`[AutoStaticsCleanup]` on the event, or the fallback assigning `null`), so last session's subscribers never fire.
- **MonoBehaviour singleton**: clear the static instance field on entering Play mode. With reload off it still references last session's destroyed object: `== null` reports it destroyed, but `is null` and `??` see a live reference.

## Load-code hazards

- **Import workers run it too.** Asset import worker processes load the project's code and run `[OnCodeLoaded]`, `[OnCodeInitializing]`, `[InitializeOnLoad]` and `[InitializeOnLoadMethod]`, so a side effect there (a file write, a socket, a server) runs in several processes. Keep load code free of side effects, or skip them where `AssetDatabase.IsAssetImportWorkerProcess()` is true.
- **`[InitializeOnLoad]` runs before asset import completes**, so an asset load there can return null. Asset work after a reload goes in `AssetPostprocessor.OnPostprocessAllAssets`.
- **Load callbacks are not Play callbacks.** The `OnCode*` attributes, `[InitializeOnLoad]`, `[InitializeOnLoadMethod]` and `AssemblyReloadEvents` fire only when code actually reloads, so with reload off they never reset anything between Play sessions.

## Friction signals

When scanning Unity code for architectural friction, singletons and static events are the signals this skill owns: global state that a caller cannot see in a signature or swap in a test. Report where they are and how they reset; keeping or removing them is the user's call.

## Validation

This skill names the checks; call `unity-verification` through the Skill tool for how Unity runs them, and put the result in its report.

- **Text check**, on every new or changed static in the diff (fields, properties, events, singleton instance fields): each has a reset path (`[AutoStaticsCleanup]`, a callback, or the pre-6.5 fallback) or a deliberate `[NoAutoStaticsCleanup]`. Every type carrying a lifecycle attribute or `[AutoStaticsCleanup]` is `partial`. The same check applies in review.
- **Compile**: after adding `[AutoStaticsCleanup]`, grep the Editor log for `CS8785`; a clean `recompile` result does not show it.
- **Runtime**, when the change alters cleanup or state that persists between Play sessions: check that state across two Play sessions, through PlayMode tests that cover it, else `unity-debugging`'s Play loop (which runs twice when domain reload is off). Nothing unrelated to the changed state runs. When neither can run, the report lists the change as unvalidated: not checked across two Play sessions.
