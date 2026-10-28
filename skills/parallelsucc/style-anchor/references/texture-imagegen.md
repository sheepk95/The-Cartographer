# Texture Imagegen Subtemplate

Use this file when the user wants a coherent family of textures, materials, or surfaces generated through `imagegen`.

## Goal

Keep texture sets visually related while still allowing controlled material-level variation.

## Required Decisions

Lock these before generating the batch:

- texture family: wall, fabric, bark, ceramic, paper, leather, metal, and so on
- repeat behavior: tileable, near-tileable, or single-frame
- scale feel: macro, mid-range, or close-up detail
- lighting model: flat studio, soft directional, diffuse overcast, stylized baked light
- surface age: pristine, lightly worn, aged, ruined
- rendering mode: painterly, stylized PBR-like, illustrated, pixel, print-like, and so on

## Master Prompt Shape

Use one stable master prompt and swap only the approved slots:

`[style family], [texture family], [core intent], [fixed invariants], [repeat behavior], [lighting model], [surface age], [item-specific variation axis], highly consistent set design`

## Recommended Invariants For Textures

- palette range
- material finish
- grain or crack logic
- detail density
- edge softness or sharpness
- amount of contrast
- camera distance
- orientation bias
- wear pattern behavior

## Variation Axes That Usually Work

- hue shift inside a narrow palette band
- amount of wear
- crack thickness
- grain direction
- stain distribution
- embossing intensity
- roughness impression
- motif insertions such as moss, dust, fibers, or flecks

## Negative Prompt Ideas

Block traits that commonly break set consistency:

- photoreal lighting changes
- inconsistent zoom level
- sudden specular highlights
- object silhouettes or scene composition
- unrelated background elements
- dramatic perspective
- mixed art styles
- noisy text or symbols

## Calibration Workflow

1. Generate `2-4` seed prompts with the same master prompt.
2. Compare them only on invariants, not on novelty.
3. Tighten whichever invariant drifted most.
4. Start the first production batch only after the seed set reads as one family.

## Tileability Reminder

If the user needs seamless textures, say so directly in every prompt and keep large directional features subdued unless directional flow is part of the contract.

## Output Template

```md
Texture style contract:
- ...

Master imagegen prompt:
- ...

Per-item slot template:
- Base prompt + [variation axis] + [material subtype]

Negative prompt:
- ...

Batch audit checklist:
- palette consistency
- detail density
- finish consistency
- repeat behavior
- wear logic
```
