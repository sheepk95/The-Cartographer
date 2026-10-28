# Style Contract Template

Use this template before generating a large batch.
Keep it compact. The goal is to freeze the style, not to write a mood board essay.

## Contract

Fill in these fields:

- Style label: a short internal name for the style family
- Medium: texture, illustration, icon, poem, slogan, prose, mixed, or other
- Core intent: what the style should make the audience feel
- Invariants: `5-9` traits that must stay fixed
- Variation axes: `2-5` traits that may change intentionally
- Motif bank: recurring imagery, materials, symbols, or rhetorical devices
- Negative constraints: traits that would break the style
- Fidelity reference: approved sample, reference image, or anchor text if available

## Recommended Invariant Categories

Pick the categories that fit the medium:

- palette or tonal range
- edge quality
- texture density
- composition or framing
- material finish
- scale discipline
- voice distance
- diction band
- sentence or line length behavior
- rhythm or cadence
- emotional temperature
- metaphor family

## Compact Output Format

```md
Style label: ...
Medium: ...
Core intent: ...

Invariants:
- ...
- ...
- ...

Variation axes:
- ...
- ...

Motif bank:
- ...
- ...

Negative constraints:
- ...
- ...

Fidelity reference:
- ...
```

## Heuristics

- Prefer observable traits over vague adjectives.
- If two traits pull in opposite directions, resolve the conflict before batch generation.
- If the user asks for "consistent but not repetitive", widen variation axes instead of weakening invariants.
- If style and subject are getting mixed together, rewrite the contract so the style can survive subject changes.
