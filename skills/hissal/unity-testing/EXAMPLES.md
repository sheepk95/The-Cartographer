# Unity test examples

C# counterparts to `tdd`'s `tests.md` and `mocking.md`. The principles are `tdd`'s; these show only the Unity shapes.

## Good: behaviour through the plain C# class

```csharp
// GOOD: EditMode [Test] against the logic, no GameObject needed
[Test]
public void Taking_damage_below_zero_kills_the_player()
{
    var health = new Health(max: 10);
    health.TakeDamage(12);
    Assert.That(health.IsDead, Is.True);
}
```

The component stays humble and has no test of its own:

```csharp
public class PlayerHealth : MonoBehaviour
{
    [SerializeField] int max = 10;
    Health health;

    void Awake() => health = new Health(max);
    public void OnHit(int damage) => health.TakeDamage(damage);
    public bool IsDead => health.IsDead;
}
```

## Bad: the lifecycle in EditMode

```csharp
// BAD: EditMode never runs Awake, so health is null and the test throws
[Test]
public void Player_dies_from_damage()
{
    var player = new GameObject().AddComponent<PlayerHealth>();
    player.OnHit(12);
}
```

Test `Health` directly, as above. If the component itself is under test, use PlayMode, where `Awake` runs inside `AddComponent`:

```csharp
[UnityTest]
public IEnumerator Player_dies_from_damage()
{
    var go = new GameObject();
    var player = go.AddComponent<PlayerHealth>();
    player.OnHit(12);
    yield return null;
    Assert.That(player.IsDead, Is.True);
    Object.Destroy(go);
}
```

## Bad: tautological

```csharp
// BAD: expected value recomputed the way the code computes it
Assert.AreEqual(Vector3.forward * speed * dt, mover.Step(dt));

// GOOD: an independent literal
Assert.That(new Mover(speed: 2f).Step(0.5f), Is.EqualTo(new Vector3(0, 0, 1)).Using(Vector3EqualityComparer.Instance));
```

`Vector3EqualityComparer` (in `UnityEngine.TestTools.Utils`) compares with a tolerance, so float error in the step does not fail the test.

## Cleanup and statics

```csharp
public class SpawnerTests
{
    GameObject root;

    [SetUp]
    public void SetUp()
    {
        EnemyRegistry.Clear();      // statics reset as if domain reload is off
        root = new GameObject("test-root");
    }

    [TearDown]
    public void TearDown() => Object.DestroyImmediate(root);   // EditMode: never Destroy

    [Test]
    public void Spawning_registers_the_enemy()
    {
        new Spawner(root.transform).Spawn();
        Assert.That(EnemyRegistry.Count, Is.EqualTo(1));
    }
}
```

## Expected error logs

```csharp
[Test]
public void Loading_a_missing_level_logs_an_error()
{
    LogAssert.Expect(LogType.Error, "Level 'nope' not found");   // before the code that logs
    Assert.That(levels.Load("nope"), Is.Null);
}
```

## Mocking: your own port, not the engine

Mock at the engine boundary the same way `tdd` mocks at a system boundary: inject a port the repo owns.

```csharp
// The port the logic takes
public interface IClock { float DeltaTime { get; } }

// Unity-backed adapter, passed in by the MonoBehaviour
public sealed class UnityClock : IClock { public float DeltaTime => Time.deltaTime; }

// Fake, passed in by the EditMode test
public sealed class FakeClock : IClock { public float DeltaTime { get; set; } }

[Test]
public void Cooldown_ends_after_its_duration()
{
    var clock = new FakeClock { DeltaTime = 0.5f };
    var cooldown = new Cooldown(duration: 1f, clock);
    cooldown.Tick();
    cooldown.Tick();
    Assert.That(cooldown.Ready, Is.True);
}
```

```csharp
// BAD: the logic reads the engine directly, so only PlayMode can drive it
public void Tick() => remaining -= Time.deltaTime;
```

With a mocking library the Unity config names, the fake becomes that library's mock of `IClock`; the port stays the same. What the port must not be is a UnityEngine type (`Transform`, `Rigidbody`, `Time`): those are the engine, tested in PlayMode or not at all.
