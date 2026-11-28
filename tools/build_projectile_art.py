"""Recolor Kenney's CC0 fireball as a 64 px arcane projectile."""

from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "art/projectile/fireball.png"
OUTPUT = ROOT / "assets/sprites/arcane-orb.png"
PALETTE = [
    (49, 20, 73), (93, 41, 139), (139, 65, 188), (183, 93, 225),
    (208, 135, 242), (228, 182, 255), (248, 221, 255), (255, 249, 255),
]


def build():
    source = Image.open(SOURCE).convert("RGBA")
    shades = sorted({rgb for *rgb_list, alpha in source.getdata()
                     if alpha and (rgb := tuple(rgb_list))[0] > rgb[2] + 20},
                    key=lambda c: sum(c))
    ranks = {color: round((i + 1) * 220 / len(shades)) for i, color in enumerate(shades)}
    glow = Image.new("L", source.size)
    glow.putdata([ranks.get((r, g, b), 0) if a else 0 for r, g, b, a in source.getdata()])
    cropped = glow.crop(glow.getbbox()).resize((26, 26), Image.Resampling.BILINEAR)
    field = Image.new("L", (32, 32))
    field.paste(cropped, (3, 3))
    halo = field.filter(ImageFilter.MaxFilter(5))
    art = Image.new("RGBA", field.size)
    pixels = []
    for i, (light, edge) in enumerate(zip(field.getdata(), halo.getdata(), strict=True)):
        x, y = i % 32, i // 32
        if light >= 18:
            # A dithered band and crisp center preserve contrast at gameplay scale.
            rank = min(7, max(0, (light + 5 * ((x + y) % 2) - 11) // 29))
            pixels.append((*PALETTE[rank], 255))
        elif edge:
            pixels.append((*PALETTE[1], min(162, 74 + edge // 3)))
        else:
            pixels.append((0, 0, 0, 0))
    art.putdata(pixels)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    art.resize((64, 64), Image.Resampling.NEAREST).save(OUTPUT)


if __name__ == "__main__":
    build()
