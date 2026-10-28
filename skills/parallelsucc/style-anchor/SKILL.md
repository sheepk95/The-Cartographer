---
name: style-anchor
description: Use when the user wants many outputs that must share a stable style with controlled variation, such as a texture set, icon family, illustration batch, poem sequence, slogan series, naming set, or other multi-item collection. This skill locks a style contract first, then generates in batches, audits drift, and repairs off-style items before continuing.
---

# Style Anchor

Use this skill when consistency matters more than novelty across a batch.

## Goal

Hold a stable style across many outputs while allowing only small, named variation.

Treat "guarantee" as an operational target:

- lock non-negotiable traits before generation
- vary only predeclared axes
- generate in small batches instead of one huge pass
- audit drift after each batch
- repair or regenerate off-style items before moving on

## When To Use

Use this skill when the user wants:

- a family of textures, sprites, icons, posters, or illustrations that feel like one set
- a sequence of poems, lyrics, slogans, taglines, or prose fragments in one voice
- a reusable prompt package that keeps later generations aligned
- style transfer from approved references into a larger batch

Do not use this skill for one-off outputs where style consistency across items is irrelevant.

## Core Workflow

1. Build a style contract before generating the full batch.
Read [references/style-contract.md](references/style-contract.md) when drafting or revising the contract.

2. Split traits into two groups:
- invariants: traits that must stay fixed
- variation axes: traits that may change intentionally

3. Calibrate with `2-4` seed examples, seed prompts, or reverse-engineered notes from user references.
If the seed outputs do not clearly share one style, tighten the contract before scaling up.

4. Generate in small batches.
Default to `3-5` items at a time unless the user requests otherwise.

5. After each batch, run a drift audit:
- what stayed on-style
- what drifted
- whether the contract needs clarification

6. Repair drift by restating the contract and regenerating only the off-style items.
Do not quietly average a drifting item into the set.

## Rules

- Keep one canonical style contract in the conversation.
- Reuse the same style lexicon across the entire batch.
- If a trait matters, write it as an invariant instead of leaving it implied.
- Avoid adjective creep. Do not keep appending new style words unless they become part of the contract.
- When the user says "more like this", change one named axis at a time.
- If the medium changes, translate the same contract instead of inventing a new one.
- If references conflict, say so early and propose splitting the work into two style families.

## Medium Notes

Read [references/media-recipes.md](references/media-recipes.md) for medium-specific prompt formulas and checks.
For tileable or set-based texture generation with `imagegen`, also read [references/texture-imagegen.md](references/texture-imagegen.md).

For image-heavy work:

- keep subject matter separate from rendering language
- lock palette, edge behavior, density, material cues, finish, and defect pattern
- if using image generation, feed the same contract into every render and change only subject slots or approved variation axes

For texture batches in `imagegen`:

- lock repeat logic first: tileable, near-tileable, or non-tileable
- state the surface category explicitly: stone, cloth, bark, plaster, metal, paper, and so on
- keep lighting, camera distance, and orientation fixed unless they are explicit variation axes
- treat wear, cracks, grain, stains, or embossing as controlled pattern families rather than random noise

For text-heavy work:

- lock speaker distance, diction band, imagery family, syntax density, cadence, and emotional temperature
- vary topics through approved motif banks, not by changing the voice

## Default Output Pattern

When starting a new batch, produce:

1. a style contract
2. a variation map
3. `2-4` seed examples or seed prompts
4. the first small batch
5. a short drift audit

## If The User Already Has References

Reverse-engineer the contract from the references and treat them as the gold standard for later audits.
Call out inferred invariants explicitly before scaling up.

## If The User Wants Only A Prompt Package

Deliver:

- a master style prompt
- a negative prompt or anti-drift list
- a per-item prompt template
- a batch audit checklist

## Texture Subtemplate

When the user specifically wants a series of textures or materials, produce:

1. a texture-focused style contract
2. a fixed `imagegen` master prompt
3. a slot template for per-texture variation
4. a negative prompt that blocks realism drift or pattern drift
5. `2-4` calibration prompts before the full batch
