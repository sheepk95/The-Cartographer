# Prompt recipes

Use only the recipe matching the requested asset. Replace bracketed fields and add the user's art direction.

## Seamless architectural surface

```text
A seamless tileable square material texture of [surface], intended as a Unity URP architectural albedo for standalone VR. Orthographic flat material capture, uniform neutral illumination, consistent real-world scale, edge-to-edge surface only. No perspective, no visible wall or floor boundary, no objects, no text, no frame, no vignette, no directional highlights, no cast shadows, no ambient-occlusion baked into corners. Opposite edges must continue naturally in both axes. [style and color details].
```

For a seam repair edit:

```text
Make this material perfectly tileable in both axes. Repair only edge continuity and obvious repeated motifs. Preserve the material identity, feature scale, color distribution, flat lighting, and center region. Do not introduce perspective, borders, text, objects, directional light, or large new features.
```

## Spot or directional Light Cookie

```text
A square grayscale Light Cookie texture for a Unity URP [spot/directional] light: [pattern]. Pure black background, soft controlled white-to-gray illumination pattern, centered, no color, no text, no scene, no lamp fixture, no perspective. Keep the outer border completely black so clamped projection fades cleanly. High contrast but smooth gradients, optimized for a 512×512 game texture.
```

Do not use this recipe for a point light. Unity point-light Cookies require a cubemap workflow, which this skill does not generate.

## Emission mask

```text
A square grayscale emission mask for [architectural element]. Black means no emission and white means full emission. Exact flat front-facing pattern, clean shapes, pure black background, no color, no lighting, no glow halo baked into the image, no perspective, no text unless explicitly requested. Designed to be tinted and intensified in a Unity URP material.
```

## Additive fog, smoke, or dust sprite

```text
A square monochrome additive particle sprite for standalone VR: [fog/smoke/dust description]. Pure black background and soft white-to-gray density, one centered organic cloud with irregular detail, feathering fully to black well before every edge. No scene, no horizon, no objects, no hard border, no color, no text. Avoid tiny noisy detail and preserve smooth gradients for a 512×512 Unity particle texture.
```

## Tiling procedural noise

```text
A seamless tileable square grayscale noise texture for [fog distortion/light modulation/surface breakup]. Balanced mid-frequency organic pattern, no recognizable objects, no directional lighting, no radial gradient, no border, no text. Opposite edges continue exactly in both axes. Black-to-white data texture suitable for linear sampling in Unity.
```

## Decal candidate

```text
A flat front-facing decal of [marking/sign/stain] for a Unity architectural environment. Isolated centered design, even neutral appearance, no wall mockup, no perspective, no cast shadow, no lighting demonstration, no extra objects, no frame. Provide a clean mask-friendly silhouette and generous empty border.
```

If transparent output is unavailable or unreliable, create a separate grayscale mask instead of pretending the background is transparent.
