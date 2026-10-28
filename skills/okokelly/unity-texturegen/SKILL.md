---
name: unity-texturegen
description: Generate and refine GPT Image textures for Unity URP projects targeting standalone Meta Quest and mobile VR. Use for seamless textures, tileable architectural surfaces, PBR-friendly base-color textures, decals, spot or directional Light Cookies, emission masks, fog textures, particle sprites, noise masks, Unity import settings, tiling QA, and VR texture optimization. Trigger on AI texture generator, Unity texture generation, GPT Image game assets, OpenAI image texture generation, 贴图, 纹理, Unity贴图生成器, Unity纹理生成, 无缝贴图, 无缝纹理, 可平铺贴图, 循环纹理, 建筑贴图, 材质贴图, 光效贴图, 灯光Cookie, 光照Cookie, 发光遮罩, 自发光贴图, 雾贴图, 雾效贴图, 烟雾贴图, 粒子贴图, Meta Quest贴图, 移动VR贴图, or GPT图像生成. Requires a host raster image tool, Python 3, and local preview rendering. Do not use for character assets, mesh modeling, point-light cubemap Cookies, HDRP-only workflows, or unrelated illustrations.
---

# Unity Texture Generator

Create compact, production-oriented texture assets for Unity URP on standalone Quest. Use the built-in GPT Image path and keep the workflow free of Photoshop, Substance Designer, Blender, and third-party image API credentials.

## Required image capability

Resolve image generation in this order:

1. Load and follow the installed `$imagegen` skill when available.
2. Otherwise, use the host agent's native GPT Image or equivalent raster image generation and editing tool.
3. If the host has no image tool, stop and report the missing capability.

Prefer a host-native tool that does not require the user to expose an API key. Never configure an untrusted external image endpoint or install a third-party generator as a workaround.

## Workflow

1. Classify the request as one of: seamless surface, decal, spot/directional Light Cookie, emission mask, fog/particle sprite, procedural noise, or reference variant.
2. Infer reasonable defaults instead of blocking: standalone Quest, URP, PNG, square canvas, and the sizes in [Quest texture specs](references/quest-texture-specs.md).
3. Read [prompt recipes](references/prompt-recipes.md) for the selected asset class. Add the user's art direction without weakening the technical constraints.
4. Generate directly. Do not return only a prompt when the user asked for an asset.
5. Inspect the result at full size. For an input image, inspect it before editing. Reject text, unintended objects, perspective, baked directional light, hard edge discontinuities, or compression-like artifacts unless requested.
6. For a seamless surface, resolve this `SKILL.md` file's parent directory as `<skill-root>` and resolve a Python 3 launcher available on the host. Read the source PNG width, then run `<python3> "<skill-root>/scripts/make_tile_preview.py" "<image>" --output "<temporary-preview.html>" --tile-size <source-width>`. Open the self-contained HTML in an available browser or local preview renderer and inspect the 3x3 repeat at 1:1 resolution. Treat the preview as QA only and keep it outside final assets. If the preview cannot be inspected, label seamlessness as unverified.
7. Repair visible seams with an image edit using the generated image as the reference. Preserve scale, pattern, color, and surface identity. Recheck once; do not loop indefinitely.
8. Save with a Unity-oriented filename and show the final image. Report dimensions, intended shader slot, tiling status, and concise import settings.

## Generation rules

- Generate flat material capture, not a photographed wall or floor.
- Remove perspective, lens effects, vignetting, borders, objects, text, and cast shadows from reusable surfaces.
- Preserve a consistent real-world texel scale across requested variants.
- Prefer one albedo plus scalar material properties in Unity. Add masks only when they materially control an effect.
- Do not independently invent a full albedo/normal/roughness/AO set by default; independently generated maps may not align. If technical maps are explicitly requested, derive each through reference-image editing from one canonical base and disclose that pixel alignment needs visual verification.
- For Quest, avoid decorative alpha when additive blending or a separate grayscale mask works.
- Never claim a texture is seamless, tileable, pixel-aligned, or production-ready without the corresponding visual check.

## Naming

Use lowercase snake case:

`tx_<subject>_<variant>_<role>_<size>.png`

Examples:

- `tx_concrete_wall_a_albedo_1024.png`
- `tx_window_grid_a_emission_512.png`
- `tx_spotlight_b_cookie_512.png`
- `tx_ground_fog_a_additive_512.png`

## Delivery

Return:

- the rendered image and absolute file link;
- asset role and exact dimensions;
- `verified`, `failed`, or `unverified` tiling status when relevant;
- Unity settings limited to what differs from defaults;
- one brief warning if the asset uses transparency, large resolution, or another Quest-sensitive feature.

Do not recommend external art software unless the user explicitly asks for alternatives.
