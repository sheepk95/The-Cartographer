---
name: dots
description: Unity DOTS and ECS — systems and jobs, Burst, structural change and EntityCommandBuffer, ComponentLookup aliasing, baking and authoring, and when ECS is the wrong answer. Use when the project has com.unity.entities and the work touches systems, components or jobs.
---

# DOTS

Only relevant when `com.unity.entities` is in `Packages/manifest.json`. Check
before assuming: a project can have Burst and the Job System without ECS, and
those are different tools with different rules.

## The shape

- `IComponentData` — an unmanaged struct. Data only, no methods that matter, no
  references. A managed field turns it into a class component and gives up
  everything ECS is for.
- `ISystem` with `[BurstCompile]` — the default. `SystemBase` only when the
  system genuinely needs managed state or the main thread.
- `IJobEntity` — the query loop. `ScheduleParallel()` when the work per entity is
  independent, `Schedule()` when it is not, `Run()` only on the main thread and
  only when you have a reason.

`[BurstCompile]` goes on **both** the struct and the methods. On an `ISystem`,
the attribute on `OnUpdate` alone does nothing — the struct needs it too, and a
system that silently runs unburst-compiled is the most common reason DOTS code
performs like MonoBehaviour code.

## Structural change

Creating an entity, destroying one, or adding or removing a component is a
*structural change*. It invalidates chunk layout, so it cannot happen inside a
job, and on the main thread it forces a sync point that stalls every job in
flight.

Everything structural goes through an `EntityCommandBuffer`:

```csharp
var ecb = SystemAPI
    .GetSingleton<EndSimulationEntityCommandBufferSystem.Singleton>()
    .CreateCommandBuffer(state.WorldUnmanaged)
    .AsParallelWriter();
```

`BeginSimulation` plays back at the start of the *next* frame — spawn there and
nothing this frame sees the entity. `EndSimulation` plays back at the end of this
one. Getting this backwards produces a one-frame lag that is very hard to see and
very easy to explain once you know.

In a parallel job the sort key is `[ChunkIndexInQuery]`, not the entity index.

Prefer an `IEnableableComponent` over add and remove where the set of components
is stable and only the state changes: enabling and disabling is not a structural
change, so it costs nothing and needs no command buffer.

## Aliasing

The safety system rejects reading a component through `ComponentLookup<T>` while
the same job writes `T` through its query. It is right to: the two accesses can
touch the same chunk and the result depends on scheduling.

The fix is to change the data flow, not to silence the check. Reading positions
while writing transforms means building a read-only map of positions in an
earlier system and passing that, rather than reaching back into the transforms
being written. `[NativeDisableParallelForRestriction]` on a real conflict trades
a compile error for a race.

## Spatial queries

ECS has no physics broadphase unless Unity Physics is installed. For
"nearest enemy" or "anything within radius" across thousands of entities, a
spatial hash built once per frame is usually the right structure:

`NativeParallelMultiHashMap<int, Entry>` keyed by
`(int3)math.floor(position / cellSize)` hashed, filled by a parallel
`IJobEntity`, then queried by walking only the cells within the radius.

Two things to get right: the cell size should be close to the typical query
radius, and consumers must know whether they read on the main thread (complete
the dependency) or in a job (pass the handle).

## Baking

Authoring is a MonoBehaviour; a `Baker<T>` converts it to entity data at build or
subscene close time.

- `GetEntity(authoring.prefab, TransformUsageFlags.Dynamic)` — the flags decide
  which transform components exist. `None` on something you then move gives you
  an entity with no `LocalTransform`.
- Bakers re-run when the authoring data changes. They must be deterministic and
  must not reach outside their own GameObject except through `GetEntity` and
  `DependsOn`.
- Subscene contents are baked, not live. An entity that does not exist at runtime
  is usually a subscene that was not closed, or a baker that did not run.

## System order

`[UpdateInGroup]`, `[UpdateBefore]`, `[UpdateAfter]` — and prefer explicit groups
over long chains of pairwise ordering. A named group per phase (input, movement,
spatial, combat, resolution) is readable a year later; a graph of twenty
`UpdateAfter` attributes is not.

`state.RequireForUpdate<T>()` in `OnCreate` keeps a system from running before
its data exists, which is cheaper and clearer than an early return.

## When ECS is the wrong answer

ECS pays for itself at thousands of similar entities doing similar work. Below
that, it costs iteration speed, debuggability, and everyone else's ability to
read the project, and it buys nothing.

A hybrid project — ECS for the crowd, MonoBehaviours for the player, the UI and
the camera — is a normal and good architecture, not a compromise. Say which side
of the line a piece of work is on before choosing an approach for it.
