# Roslyn analyzers and source generators

How Unity picks up analyzer and source generator DLLs, and which assemblies they reach. Everything here is from Unity's documentation (Unity 6.0 and 6.6 manuals), not reproduced in a sandbox: when a setup behaves differently, trust the compile output and say the docs did not match.

## Setting one up

Both ship as a managed plugin DLL inside the project:

- Built against .NET Standard 2.0, using `Microsoft.CodeAnalysis.CSharp` 4.3 (the version the Unity 6.0 and 6.6 manuals name).
- In the DLL's Plugin Inspector: every platform unchecked, Any Platform and Editor included. It is a compiler input, never a library any assembly loads.
- The asset label `RoslynAnalyzer`, exactly that, case-sensitive. Without the label Unity treats the DLL as an ordinary plugin.

The manuals only show `ISourceGenerator`; whether `IIncrementalGenerator` works is undocumented. Try it and read the compile output before relying on it.

## Scope

| Where the DLL sits | Which assemblies it runs on |
|---|---|
| A folder with no asmdef above it (under `Assets/`) | Every predefined assembly (`Assembly-CSharp` and its siblings) |
| Inside an asmdef's folder | That assembly, and every assembly that references it |

So an analyzer next to a widely referenced asmdef reaches every referencer, often more than intended.

A generator injected into several assemblies that emits the same public type causes CS0436 (type conflicts with an imported type) in any assembly that sees two copies. Generated types should be `internal` or uniquely named per assembly.

## Rule sets

- `Assets/Default.ruleset`: every assembly.
- `Assets/<PredefinedAssemblyName>.ruleset` (such as `Assets/Assembly-CSharp.ruleset`): that predefined assembly only.
- A `.ruleset` beside an `.asmdef` (any file name): that assembly only.

Analyzer diagnostics show in the Editor console and in IDEs Unity supports; other IDEs may not show them.

## Unity's own

Unity 6.5 and later ship analyzers and a generator for the code lifecycle attributes (`UAC0031`, `UAL0010` to `UAL0014`), switched per assembly with a `<asmdefName>.globalconfig` file. Those, and any `.globalconfig`, are `unity-code-lifecycle`'s.
