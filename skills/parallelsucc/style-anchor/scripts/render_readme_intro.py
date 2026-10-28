from pathlib import Path
from math import sin, cos, pi
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont


WIDTH = 960
HEIGHT = 620
FRAMES = 78
FRAME_MS = 90

ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT / "media"
MEDIA_DIR.mkdir(exist_ok=True)

OUT_GIF = MEDIA_DIR / "style-anchor-intro.gif"
OUT_PNG = MEDIA_DIR / "style-anchor-intro-poster.png"

BG = (11, 12, 14)
BG_WARM = (22, 18, 16)
INK = (244, 239, 231)
SOFT = (184, 174, 164)
DIM = (114, 104, 96)
HAIR = (62, 56, 52)
RUST = (203, 108, 70)
RUST_DEEP = (150, 79, 49)
BLUE = (111, 132, 162)
STONE = (214, 202, 188)
PANEL = (24, 25, 28)
PANEL_2 = (29, 26, 24)


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(v):
    v = clamp(v)
    return 1 - (1 - v) ** 3


def ease_in_out(v):
    v = clamp(v)
    return 3 * v * v - 2 * v * v * v


def expo_out(v):
    v = clamp(v)
    if v >= 1:
        return 1
    return 1 - pow(2, -10 * v)


def span_progress(t, start, end):
    if end <= start:
        return 1.0
    return clamp((t - start) / (end - start))


def lerp(a, b, v):
    return a + (b - a) * v


def mix(c1, c2, v):
    return tuple(int(lerp(a, b, v)) for a, b in zip(c1, c2))


def alpha(c, a):
    return (c[0], c[1], c[2], int(a))


def load_font(path, size):
    return ImageFont.truetype(str(path), size=size)


FONT_DISPLAY = load_font("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 76)
FONT_DISPLAY_MED = load_font("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 44)
FONT_DISPLAY_SMALL = load_font("/System/Library/Fonts/Supplemental/Georgia.ttf", 27)
FONT_SERIF = load_font("/System/Library/Fonts/Supplemental/Georgia.ttf", 28)
FONT_SERIF_ITALIC = load_font("/System/Library/Fonts/Supplemental/Georgia Italic.ttf", 28)
FONT_LABEL = load_font("/System/Library/Fonts/Menlo.ttc", 14)
FONT_LABEL_SMALL = load_font("/System/Library/Fonts/Menlo.ttc", 12)
FONT_CARD = load_font("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 22)
FONT_CARD_BODY = load_font("/System/Library/Fonts/Supplemental/Georgia.ttf", 16)


def text_size(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_centered_text(draw, x, y, text, font, fill):
    w, h = text_size(draw, text, font)
    draw.text((x - w / 2, y - h / 2), text, font=font, fill=fill)


def make_background():
    base = Image.new("RGBA", (WIDTH, HEIGHT), BG + (255,))
    px = base.load()
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        row = mix(BG, BG_WARM, ratio * 0.72)
        for x in range(WIDTH):
            px[x, y] = row + (255,)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((150, -120, 810, 420), fill=alpha((126, 84, 52), 90))
    gd.ellipse((220, 10, 740, 310), fill=alpha((240, 222, 204), 22))
    gd.ellipse((-160, 280, 380, 820), fill=alpha((92, 70, 52), 30))
    gd.ellipse((640, 260, 1160, 820), fill=alpha((72, 76, 92), 26))

    stage = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stage)
    sd.polygon(
        [(120, 490), (840, 490), (920, 610), (40, 610)],
        fill=alpha((19, 20, 23), 255),
    )
    sd.line((110, 490, 850, 490), fill=alpha((91, 74, 60), 80), width=1)
    for x in range(140, 840, 70):
        sd.line((x, 492, x - 72, 610), fill=alpha((42, 40, 40), 60), width=1)

    noise = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    nd = ImageDraw.Draw(noise)
    rng = random.Random(7)
    for _ in range(800):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        a = rng.randint(8, 18)
        nd.point((x, y), fill=(180, 162, 144, a))

    out = Image.alpha_composite(base, glow.filter(ImageFilter.GaussianBlur(48)))
    out = Image.alpha_composite(out, stage)
    out = Image.alpha_composite(out, noise)
    return out


BACKGROUND = make_background()


def make_texture_card(base_color, accent, label, lines, seed):
    w, h = 176, 222
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=24, fill=(245, 241, 236, 255), outline=(82, 72, 67, 120), width=1)
    d.rounded_rectangle((14, 14, w - 14, 130), radius=18, fill=base_color + (255,), outline=alpha(mix(base_color, (20, 20, 20), 0.25), 90), width=1)

    rng = random.Random(seed)
    for _ in range(lines):
        x0 = rng.randint(24, w - 40)
        y0 = rng.randint(22, 116)
        x1 = x0 + rng.randint(-36, 36)
        y1 = y0 + rng.randint(8, 28)
        d.line((x0, y0, x1, y1), fill=alpha(mix(accent, (24, 24, 24), 0.38), rng.randint(34, 72)), width=rng.randint(1, 2))
    for _ in range(11):
        cx = rng.randint(26, w - 26)
        cy = rng.randint(26, 118)
        r = rng.randint(4, 9)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha(mix(base_color, accent, 0.25), rng.randint(16, 40)))

    d.text((16, 154), label, font=FONT_CARD, fill=(30, 28, 26, 255))
    d.text((16, 185), "Locked palette / detail / finish", font=FONT_LABEL_SMALL, fill=(107, 98, 90, 255))
    return card


TEXTURE_CARDS = [
    make_texture_card((209, 196, 180), RUST, "Stone", 22, 14),
    make_texture_card((198, 187, 177), BLUE, "Linen", 20, 18),
    make_texture_card((217, 204, 191), (122, 140, 116), "Plaster", 19, 26),
    make_texture_card((191, 177, 164), RUST_DEEP, "Bark", 23, 31),
]


def make_text_panel():
    w, h = 332, 230
    panel = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=26, fill=(246, 241, 235, 252), outline=(86, 76, 70, 112), width=1)
    d.line((22, 34, 132, 34), fill=(111, 132, 162, 255), width=2)
    d.text((22, 50), "One recognisable voice", font=FONT_CARD, fill=(28, 27, 25, 255))
    d.text((22, 98), "A winter line, restrained and spare,", font=FONT_SERIF_ITALIC, fill=(40, 37, 34, 255))
    d.text((22, 136), "still carrying the same dry air.", font=FONT_SERIF_ITALIC, fill=(40, 37, 34, 238))
    d.text((22, 184), "Topic changes. The voice does not.", font=FONT_CARD_BODY, fill=(104, 96, 89, 255))
    return panel


TEXT_PANEL = make_text_panel()


def paste_center(base, layer, x, y, scale=1.0, angle=0.0, alpha_mul=1.0, blur=0):
    if scale <= 0:
        return
    w, h = layer.size
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    obj = layer.resize((new_w, new_h), Image.Resampling.LANCZOS)
    if angle:
        obj = obj.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    if blur:
        obj = obj.filter(ImageFilter.GaussianBlur(blur))
    if alpha_mul < 1:
        a = obj.getchannel("A").point(lambda p: int(p * alpha_mul))
        obj.putalpha(a)
    base.alpha_composite(obj, (int(x - obj.size[0] / 2), int(y - obj.size[1] / 2)))


def build_slab(progress, scale_bias=1.0):
    progress = clamp(progress)
    slab = Image.new("RGBA", (550, 286), (0, 0, 0, 0))
    d = ImageDraw.Draw(slab)
    d.rounded_rectangle((0, 0, 549, 285), radius=34, fill=alpha(PANEL, 246), outline=alpha((93, 83, 77), 110), width=1)
    d.rounded_rectangle((1, 1, 548, 72), radius=34, fill=alpha((27, 26, 28), 255))
    d.line((44, 56, 164, 56), fill=alpha(RUST, 220), width=2)
    d.text((44, 28), "STYLE CONSISTENCY ENGINE", font=FONT_LABEL, fill=alpha(SOFT, 200))

    reveal = int(530 * progress)
    mask = Image.new("L", (550, 286), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle((0, 0, reveal, 286), fill=255)

    text = Image.new("RGBA", (550, 286), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    td.text((44, 104), "Style Anchor", font=FONT_DISPLAY_MED, fill=alpha(INK, 255))
    td.text((44, 160), "Lock the style. Vary the output.", font=FONT_DISPLAY_SMALL, fill=alpha(SOFT, 228))
    td.text((44, 208), "Textures / poems / icon families / naming systems", font=FONT_LABEL, fill=alpha(mix(SOFT, BLUE, 0.25), 204))
    text.putalpha(mask)
    slab.alpha_composite(text)

    pulse = 0.5 + 0.5 * sin(progress * pi)
    d.rounded_rectangle((394, 104, 486, 188), radius=18, outline=alpha((92, 82, 77), 120), width=1)
    d.line((414, 150, 466, 150), fill=alpha(RUST, int(160 + 60 * pulse)), width=3)
    d.line((438, 126, 438, 174), fill=alpha(BLUE, int(80 + 40 * pulse)), width=1)
    d.text((400, 198), "contract", font=FONT_LABEL_SMALL, fill=alpha(DIM, 220))

    badge_y = 238
    labels = [("freeze", RUST), ("vary", BLUE), ("audit", (124, 145, 118))]
    x = 44
    for label, tone in labels:
        d.rounded_rectangle((x, badge_y, x + 82, badge_y + 24), radius=12, fill=alpha((33, 32, 35), 255), outline=alpha(tone, 120), width=1)
        tw, th = text_size(d, label, FONT_LABEL_SMALL)
        d.text((x + (82 - tw) / 2, badge_y + (24 - th) / 2 - 1), label, font=FONT_LABEL_SMALL, fill=alpha(tone, 220))
        x += 94

    if scale_bias != 1:
        out = slab.resize((int(550 * scale_bias), int(286 * scale_bias)), Image.Resampling.LANCZOS)
        return out
    return slab


def build_frame(frame_index):
    t = frame_index / (FRAMES - 1)
    img = BACKGROUND.copy()

    intro = span_progress(t, 0.00, 0.18)
    slab_phase = span_progress(t, 0.12, 0.34)
    gallery_phase = span_progress(t, 0.34, 0.74)
    final_phase = span_progress(t, 0.74, 1.00)

    draw = ImageDraw.Draw(img)

    # opening title
    intro_a = ease_out(intro) * (1 - ease_in_out(span_progress(t, 0.22, 0.34)))
    line_len = int(lerp(0, 152, intro_a))
    draw.line((96, 84, 96 + line_len, 84), fill=alpha(RUST, 220 * intro_a), width=2)
    draw.line((WIDTH - 96 - line_len, 84, WIDTH - 96, 84), fill=alpha(BLUE, 180 * intro_a), width=2)
    draw.text((96, 102), "CODEX SKILL FOR STYLE CONSISTENCY", font=FONT_LABEL, fill=alpha(SOFT, int(190 * max(intro_a, 0.15))))
    title_y = lerp(238, 208, intro_a)
    draw_centered_text(draw, WIDTH / 2, title_y, "Style Anchor", FONT_DISPLAY, alpha(INK, int(255 * intro_a)))
    draw_centered_text(draw, WIDTH / 2, title_y + 74, "A launch workflow for coherent batches.", FONT_DISPLAY_SMALL, alpha(SOFT, int(220 * intro_a)))

    # hero slab reveal
    slab_p = expo_out(slab_phase)
    slab_hold_fade = 1 - ease_in_out(span_progress(t, 0.42, 0.58))
    slab_glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sg = ImageDraw.Draw(slab_glow)
    glow_alpha = int(120 * slab_p * slab_hold_fade)
    sg.ellipse((242, 120, 718, 458), fill=alpha((160, 96, 58), glow_alpha))
    img = Image.alpha_composite(img, slab_glow.filter(ImageFilter.GaussianBlur(38)))
    slab = build_slab(slab_p)
    paste_center(img, slab, WIDTH / 2, 300 - 18 * (1 - slab_p), scale=1.0, angle=0, alpha_mul=slab_hold_fade)

    # gallery reveal
    gallery_a = ease_in_out(gallery_phase)
    if gallery_a > 0:
        stage_dim = Image.new("RGBA", (WIDTH, HEIGHT), alpha((8, 8, 10), int(112 * gallery_a)))
        img = Image.alpha_composite(img, stage_dim)

        # left texture gallery with parallax
        base_x = 242
        base_y = 338
        offsets = [(-138, 24), (-42, -8), (58, -20), (152, 8)]
        angles = [-12, -5, 5, 12]
        scales = [0.88, 0.98, 1.02, 0.94]
        for i, card in enumerate(TEXTURE_CARDS):
            p = span_progress(gallery_a, i * 0.08, 0.46 + i * 0.08)
            local = expo_out(p)
            x = lerp(WIDTH / 2, base_x + offsets[i][0], local)
            y = lerp(296, base_y + offsets[i][1], local)
            scale = lerp(0.72, scales[i], local)
            angle = lerp(-2, angles[i], local)
            alpha_mul = local
            shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            sx = x + 10
            sy = y + 18
            sd.ellipse((sx - 80, sy + 66, sx + 80, sy + 98), fill=alpha((0, 0, 0), int(42 * local)))
            img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(12)))
            paste_center(img, card, x, y, scale=scale, angle=angle, alpha_mul=alpha_mul)

        # right editorial panel
        panel_p = expo_out(span_progress(gallery_a, 0.18, 0.72))
        panel_x = lerp(676, 678, panel_p)
        panel_y = lerp(388, 346, panel_p)
        paste_center(img, TEXT_PANEL, panel_x, panel_y, scale=lerp(0.88, 1.0, panel_p), angle=lerp(4, 0, panel_p), alpha_mul=panel_p)

        draw = ImageDraw.Draw(img)
        caption_a = int(208 * gallery_a)
        draw.text((106, 520), "TEXTURE WORKFLOW · TILE / MATERIAL / FINISH", font=FONT_LABEL_SMALL, fill=alpha(DIM, caption_a))
        draw.text((548, 520), "TEXT WORKFLOW · VOICE / CADENCE / IMAGERY", font=FONT_LABEL_SMALL, fill=alpha(DIM, caption_a))
        cursor = span_progress(gallery_a, 0.42, 0.82)
        cx = int(546 + 142 * ease_in_out(cursor))
        draw.line((cx, 480, cx, 505), fill=alpha(BLUE, int(160 * gallery_a)), width=2)

    # final plaque
    final_a = ease_in_out(final_phase)
    if final_a > 0:
        veil = Image.new("RGBA", (WIDTH, HEIGHT), alpha((6, 6, 8), int(150 * final_a)))
        img = Image.alpha_composite(img, veil)
        plaque = Image.new("RGBA", (640, 258), (0, 0, 0, 0))
        pd = ImageDraw.Draw(plaque)
        pd.rounded_rectangle((0, 0, 639, 257), radius=36, fill=alpha((22, 22, 25), 246), outline=alpha((98, 88, 82), 118), width=1)
        pd.line((52, 52, 194, 52), fill=alpha(RUST, 220), width=2)
        pd.line((446, 52, 588, 52), fill=alpha(BLUE, 182), width=2)
        pd.text((52, 70), "FOR LAUNCH-SCALE GENERATION", font=FONT_LABEL, fill=alpha(SOFT, 190))
        pd.text((52, 116), "One style contract", font=FONT_DISPLAY_MED, fill=alpha(INK, 255))
        pd.text((52, 164), "across images and text.", font=FONT_DISPLAY_MED, fill=alpha(INK, 255))
        pd.text((52, 214), "Includes an imagegen-ready texture workflow.", font=FONT_DISPLAY_SMALL, fill=alpha(SOFT, 224))
        glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((182, 124, 778, 474), fill=alpha((126, 84, 52), int(64 * final_a)))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(28)))
        paste_center(img, plaque, WIDTH / 2, 312, scale=lerp(0.92, 1.0, final_a), alpha_mul=final_a)

    draw = ImageDraw.Draw(img)
    shimmer_x = 120 + int(720 * (0.5 + 0.5 * sin(t * pi * 2.8)))
    draw.line((120, 570, 840, 570), fill=alpha(HAIR, 105), width=1)
    draw.line((max(120, shimmer_x - 70), 570, min(840, shimmer_x + 70), 570), fill=alpha(RUST, 120), width=1)
    draw.text((690, 586), "Created by Huashu-Design", font=FONT_LABEL_SMALL, fill=alpha(DIM, 140))

    rgba = img.convert("RGBA")
    return rgba.convert("P", palette=Image.Palette.ADAPTIVE, colors=255)


def main():
    frames = [build_frame(i) for i in range(FRAMES)]
    frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=FRAME_MS,
        disposal=2,
        optimize=True,
    )
    build_frame(FRAMES - 1).convert("RGBA").save(OUT_PNG)
    print(f"wrote {OUT_GIF}")
    print(f"wrote {OUT_PNG}")


if __name__ == "__main__":
    main()
