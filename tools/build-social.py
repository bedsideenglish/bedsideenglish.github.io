#!/usr/bin/env python3
"""Build the shared social/store artwork from real app captures.

The three assets/social/ formats are the same composition at different crops,
so a copy change or a new screenshot only has to be made once:

  og-cover.png        1200x630   Open Graph / Twitter card (referenced by the pages)
  feature-graphic.png 1024x500   Google Play feature graphic (exact size Play requires)
  share-square.png    1200x1200  Square fallback for KakaoTalk, Instagram, etc.

A fourth, text-free asset lives in assets/backgrounds/ and decorates the final
CTA section in place, behind the actual heading/button markup:

  final-cta.webp       2400x680  Phone clusters pushed to both edges, empty and
                                  faded in the middle so live page copy sits on
                                  top of it without a collision. On a narrow
                                  mobile viewport, CSS `background-size:cover`
                                  crops to the empty middle by construction —
                                  see the .final rule's math in a comment there
                                  — so the page also drops the image outright
                                  under 900px to save the download.

Run from the repository root:  python3 tools/build-social.py
Requires Pillow.  Output is flattened RGB — Play rejects artwork with alpha.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "assets", "android")
OUT = os.path.join(ROOT, "assets", "social")
BG_OUT = os.path.join(ROOT, "assets", "backgrounds")
BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

VOID = (5, 7, 12)
CHALK = (237, 242, 251)
BLUE2 = (142, 180, 255)
FOG = (163, 174, 193)

# Each format: canvas, the two background glows, the phone stack, and the copy.
# Phone entries are (screenshot, screen width, (centre x, centre y), rotation).
FORMATS = {
    "og-cover.png": {
        "size": (1200, 630),
        "glows": [((690, -260, 1500, 550), (26, 58, 126)), ((-300, 260, 340, 900), (10, 26, 62))],
        "blur": 170,
        "phones": [("history", 196, (712, 344), -10), ("encounter-live", 196, (1052, 344), 10),
                   ("srs-transfer", 224, (876, 322), 0)],
        "text": [(72, 150, "ANDROID  ·  FREE  ·  NO ACCOUNT", BOLD, 21, BLUE2),
                 (70, 196, "Talk to an AI patient.", BOLD, 62, CHALK),
                 (70, 266, "In English. Out loud.", BOLD, 62, BLUE2),
                 (72, 356, "Unscripted voice practice, live scoring,", REG, 25, FOG),
                 (72, 392, "and your own mistakes as tomorrow's drill.", REG, 25, FOG),
                 (72, 470, "Bedside English", BOLD, 30, CHALK)],
    },
    # Play crops and overlays the edges of a feature graphic in some placements,
    # so nothing that must stay readable sits within ~50px of any edge.
    "feature-graphic.png": {
        "size": (1024, 500),
        "glows": [((600, -220, 1300, 460), (26, 58, 126)), ((-260, 200, 260, 720), (10, 26, 62))],
        "blur": 140,
        "phones": [("history", 148, (742, 250), -10), ("encounter-live", 148, (996, 250), 10),
                   ("srs-transfer", 170, (869, 232), 0)],
        "text": [(58, 128, "ANDROID  ·  FREE  ·  NO ACCOUNT", BOLD, 16, BLUE2),
                 (56, 158, "Talk to an AI patient.", BOLD, 44, CHALK),
                 (56, 208, "In English. Out loud.", BOLD, 44, BLUE2),
                 (58, 278, "Unscripted voice practice, live scoring,", REG, 18, FOG),
                 (58, 304, "and your mistakes as tomorrow's drill.", REG, 18, FOG),
                 (58, 356, "Bedside English", BOLD, 23, CHALK)],
    },
    "share-square.png": {
        "size": (1200, 1200),
        "glows": [((380, -300, 1500, 820), (26, 58, 126)), ((-320, 620, 420, 1360), (10, 26, 62))],
        "blur": 200,
        "phones": [("history", 232, (330, 860), -10), ("encounter-live", 232, (870, 860), 10),
                   ("srs-transfer", 266, (600, 832), 0)],
        "text": [(74, 150, "ANDROID  ·  FREE  ·  NO ACCOUNT", BOLD, 24, BLUE2),
                 (72, 192, "Talk to an AI patient.", BOLD, 70, CHALK),
                 (72, 272, "In English. Out loud.", BOLD, 70, BLUE2),
                 (74, 384, "Unscripted voice practice, live scoring,", REG, 27, FOG),
                 (74, 424, "and your own mistakes as tomorrow's drill.", REG, 27, FOG),
                 (74, 496, "Bedside English", BOLD, 32, CHALK)],
    },
}


def rounded(im, radius):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius, fill=255)
    im.putalpha(mask)
    return im


def phone(name, screen_w):
    """One screenshot inside a dark device frame, returned as RGBA."""
    shot = Image.open(os.path.join(SHOTS, name + ".webp")).convert("RGB")
    shot = shot.resize((screen_w, round(shot.height * screen_w / shot.width)), Image.LANCZOS)
    shot = rounded(shot, round(screen_w * .075))
    pad = max(6, round(screen_w * .035))
    frame = Image.new("RGBA", (screen_w + pad * 2, shot.height + pad * 2), (0, 0, 0, 0))
    frame.paste(rounded(Image.new("RGB", frame.size, (26, 33, 48)), round(screen_w * .11)), (0, 0))
    frame.paste(shot, (pad, pad), shot)
    return frame


def build(name, spec):
    w, h = spec["size"]
    bg = Image.new("RGB", (w, h), VOID)
    glow = Image.new("RGB", (w, h), VOID)
    gd = ImageDraw.Draw(glow)
    for box, colour in spec["glows"]:
        gd.ellipse(box, fill=colour)
    bg = Image.blend(bg, glow.filter(ImageFilter.GaussianBlur(spec["blur"])), .82)

    grid = ImageDraw.Draw(bg)
    for x in range(0, w, 72):
        grid.line([(x, 0), (x, h)], fill=(13, 17, 26))
    for y in range(0, h, 72):
        grid.line([(0, y), (w, y)], fill=(13, 17, 26))

    for shot, width, (cx, cy), angle in spec["phones"]:
        p = phone(shot, width).rotate(-angle, resample=Image.BICUBIC, expand=True)
        shadow = Image.new("RGBA", p.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 190), (0, 0), p.split()[3])
        shadow = shadow.filter(ImageFilter.GaussianBlur(26))
        pos = (cx - p.width // 2, cy - p.height // 2)
        bg.paste(shadow, (pos[0], pos[1] + 22), shadow)
        bg.paste(p, pos, p)

    d = ImageDraw.Draw(bg)
    for x, y, text, font, size, colour in spec["text"]:
        d.text((x, y), text, font=ImageFont.truetype(font, size), fill=colour)

    path = os.path.join(OUT, name)
    bg.save(path, optimize=True)
    print("%-22s %s  %d KB" % (name, bg.size, os.path.getsize(path) // 1024))


def build_final_cta_bg():
    """Two small phone clusters at the far edges of a wide canvas, nothing in
    the middle third. Meant to sit *behind* the final section's centred
    heading/button markup, not to be looked at directly — so each phone's
    alpha is cut to 60% before it's pasted, reading as texture rather than a
    third repeat of the hero screenshot."""
    w, h = 2400, 680
    bg = Image.new("RGB", (w, h), VOID)
    glow = Image.new("RGB", (w, h), VOID)
    gd = ImageDraw.Draw(glow)
    gd.ellipse((1550, -260, 2700, 520), fill=(26, 58, 126))
    gd.ellipse((-300, 260, 700, 900), fill=(10, 26, 62))
    bg = Image.blend(bg, glow.filter(ImageFilter.GaussianBlur(190)), .8)

    clusters = [
        [("feedback-scores", 150, (150, 300), -9), ("pronunciation-drill", 168, (330, 380), 7)],
        [("corrections", 168, (2070, 380), -7), ("srs-card", 150, (2250, 300), 9)],
    ]
    for cluster in clusters:
        for shot, width, (cx, cy), angle in cluster:
            p = phone(shot, width).rotate(-angle, resample=Image.BICUBIC, expand=True)
            r, g, b_, a = p.split()
            p = Image.merge("RGBA", (r, g, b_, a.point(lambda v: v * 6 // 10)))
            shadow = Image.new("RGBA", p.size, (0, 0, 0, 0))
            shadow.paste((0, 0, 0, 110), (0, 0), p.split()[3])
            shadow = shadow.filter(ImageFilter.GaussianBlur(22))
            pos = (cx - p.width // 2, cy - p.height // 2)
            bg.paste(shadow, (pos[0], pos[1] + 16), shadow)
            bg.paste(p, pos, p)

    os.makedirs(BG_OUT, exist_ok=True)
    path = os.path.join(BG_OUT, "final-cta.webp")
    bg.save(path, "WEBP", quality=84, method=6)
    print("%-22s %s  %d KB" % ("final-cta.webp", bg.size, os.path.getsize(path) // 1024))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, spec in FORMATS.items():
        build(name, spec)
    build_final_cta_bg()
