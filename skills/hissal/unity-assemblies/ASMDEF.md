# Assembly definition format

The `.asmdef`, `.asmref` and `.meta` file shapes, and the define syntax, from Unity's docs and source; the lines marked observed were checked on 6000.6.2f1. Unity reads missing fields as their defaults, so a hand-written file needs only the fields that differ; match the fields and formatting the repo's other asmdefs already use.

## `.asmdef`

A runtime assembly with every field at its default except the ones commented:

```jsonc
{
  "name": "Company.Product.Feature",     // the assembly name; unique in the project
  "rootNamespace": "Company.Product.Feature",
  "references": [
    "GUID:0123456789abcdef0123456789abcdef"
  ],
  "includePlatforms": [],
  "excludePlatforms": [],
  "allowUnsafeCode": false,
  "overrideReferences": false,
  "precompiledReferences": [],
  "autoReferenced": true,
  "defineConstraints": [],
  "versionDefines": [],
  "noEngineReferences": false
}
```

(Real files are plain JSON: no comments.)

| Field | Default | Effect | Gotcha |
|---|---|---|---|
| `name` | required | The compiled assembly's name. | Renaming the `.asmdef` file leaves `name` unchanged. Name references and `InternalsVisibleTo` strings use `name`. |
| `rootNamespace` | empty | The namespace IDEs put in new scripts. | Changes nothing at compile time. |
| `references` | `[]` | Assemblies this one may use, as `"GUID:<guid>"` or a name. | A reference that matches no assembly is dropped without an error or warning (observed on 6000.6.2f1); it fails only when code uses a type from it. |
| `includePlatforms` / `excludePlatforms` | `[]` | Where the assembly compiles. `["Editor"]` makes it Editor-only. | Only one of the two may be non-empty. Only platforms with installed build support are valid. |
| `allowUnsafeCode` | `false` | Allows `unsafe` code. | |
| `autoReferenced` | `true` | Whether the predefined assemblies (`Assembly-CSharp` and its siblings) see this one. | Has no effect on whether the assembly ships in a build, and never lets this assembly see `Assembly-CSharp`. |
| `overrideReferences` | `false` | When true, only `precompiledReferences` DLLs are referenced, instead of every precompiled DLL. | Test assemblies set it to list `nunit.framework.dll`. |
| `precompiledReferences` | `[]` | DLL file names, with extension. | Read only when `overrideReferences` is true. |
| `defineConstraints` | `[]` | Symbols that must all be defined for the assembly to compile, or to be referenced. | Evaluated against the active build target. When they fail, the assembly does not exist at all, and its source is never compiled (observed). |
| `versionDefines` | `[]` | Symbols defined inside this assembly when a package, module or Unity version matches. | The symbol exists only in this assembly's scripts. |
| `noEngineReferences` | `false` | Leaves out `UnityEngine` and `UnityEditor`: a plain C# assembly. | |

Legacy: `"optionalUnityReferences": ["TestAssemblies"]` still loads as a test assembly; write test assemblies explicitly (templates in `unity-testing`).

## `.asmref`

Adds its folder (and subfolders without their own asmdef or asmref) to an existing assembly:

```json
{
  "reference": "GUID:0123456789abcdef0123456789abcdef"
}
```

## `.meta` for a new `.asmdef` or `.asmref`

```yaml
fileFormatVersion: 2
guid: 0123456789abcdef0123456789abcdef
AssemblyDefinitionImporter:
  externalObjects: {}
  userData: 
  assetBundleName: 
  assetBundleVariant: 
```

`guid` is 32 lowercase hex characters, freshly generated (for example a UUID with its dashes removed); never reuse one. An `.asmref` uses `AssemblyDefinitionReferenceImporter:` in place of `AssemblyDefinitionImporter:`. Unity keeps a hand-written GUID in either (observed), when written per the GUID rule in `SKILL.md`.

## `versionDefines`

```json
"versionDefines": [
  {
    "name": "com.unity.inputsystem",
    "expression": "1.0.0",
    "define": "HAS_INPUT_SYSTEM"
  }
]
```

- `name`: a package name, a module name, or `Unity` for the editor version.
- `expression`: a version or interval, with no spaces and no wildcards:

| Expression | Means |
|---|---|
| `1.0.0` | 1.0.0 or later |
| `[1.3,3.4.1]` | 1.3 to 3.4.1, both included |
| `(1.3.0,3.4)` | between them, both excluded |
| `[1.1,3.4)` | 1.1 included, up to 3.4 excluded |
| `[2.4.5]` | exactly 2.4.5 |

For `Unity`, write editor versions such as `[6000.0,6000.2)`; release types order `a < b < f = c < p < x`.

## `defineConstraints`

```json
"defineConstraints": ["HAS_INPUT_SYSTEM", "!UNITY_WEBGL", "UNITY_EDITOR || DEVELOPMENT_BUILD"]
```

Entries are ANDed. `!` negates a symbol; `||` inside one entry means either. Built-in symbols (`UNITY_EDITOR`, `UNITY_INCLUDE_TESTS`, platform symbols), project symbols and this assembly's own `versionDefines` all count. An invalid entry fails with "Invalid Define Constraint".

## Project-wide symbols

Per Unity's documentation, three scopes add up:

- `Assets/csc.rsp` with `-define:A;B`: every assembly, Editor and Player, regardless of build profile. A change takes effect only after a recompile (reimport or touch one script).
- Player Settings, Scripting Define Symbols: per platform. Applying recompiles.
- A build profile's own define list: per profile.

From script, `PlayerSettings.SetScriptingDefineSymbols` sets the Player Settings scope and `BuildPlayerOptions.extraScriptingDefines` adds symbols to one Player build only.
