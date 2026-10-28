# Quest texture specs

Use these as project defaults, then adapt when scene scale or close viewing justifies it.

## Size and format

| Asset | Default | Escalate only when |
|---|---:|---|
| Repeating architectural albedo | 1024×1024 PNG | A hero surface is viewed very close; test 2048 |
| Decal or signage | 512×512 PNG | Text or fine symbols fail at target distance |
| Light Cookie | 512×512 grayscale PNG | A large projected pattern visibly breaks up |
| Emission or utility mask | 512×512 grayscale PNG | The mask spans a large screen area |
| Fog, smoke, dust, particle sprite | 256–512 square PNG | Soft gradients band or show pixels in-headset |
| Generic noise | 256–512 square PNG | The effect demonstrably repeats too visibly |

Prefer powers of two. Avoid 2048 and 4096 by default. A large source file is not free detail once Android GPU compression, mipmaps, sampling distance, and headset resolution are considered.

## Unity import defaults

### Albedo and colored emission

- Texture Type: Default
- sRGB: On
- Alpha Source: None unless genuinely used
- Wrap Mode: Repeat for seamless surfaces; Clamp for one-shot decals
- Filter Mode: Bilinear; use Trilinear only when mip transitions are visibly objectionable
- Generate Mip Maps: On for world-space surfaces; usually Off for screen-fixed or one-shot utility textures
- Android override: ASTC 6×6 as a balanced starting point; test ASTC 8×8 for low-frequency, soft, or distant textures

### Grayscale masks, cookies, and data textures

- Texture Type: Default
- sRGB: Off
- Wrap Mode: Clamp for cookies and isolated masks; Repeat for tiling noise
- Alpha Source: None when the mask is stored in RGB
- Generate Mip Maps: decide from projection scale; keep them for distant/repeating world effects
- Android override: ASTC 6×6; try ASTC 8×8 when artifacts remain invisible in-headset

### Normal maps

- Do not generate by default.
- When explicitly required, import as Normal Map and test whether the extra sample improves the headset view enough to justify it.

## Quest material budget rules

- Prefer shared tiling textures over many unique materials.
- Reuse one grayscale mask with material tint and intensity parameters.
- Favor opaque materials. Transparent fog layers and particles can cause expensive overdraw.
- Use a black-background additive fog or light sprite when it provides the intended result without alpha blending.
- Evaluate final quality in-headset; the Editor Game view is not the acceptance test.

## Sources

- Unity 6 platform-specific texture overrides: https://docs.unity3d.com/6000.0/Documentation/Manual/class-TextureImporter-type-specific.html
- Unity 6 Android texture formats: https://docs.unity3d.com/6000.0/Documentation/Manual/texture-choose-format-by-platform.html

