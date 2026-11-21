"""Lay out all eight facings and preview each motion at its native frame rate."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = "#1b1a23"
PANEL = "#272532"
INK = "#dfd0bf"
LABELS = {
    "hero": "Shield fighter", "melee": "Skeleton knight", "ranged": "Ash warlock",
    "idle": "Idle", "guard_walk": "Guard walk", "run": "Run", "guard": "Guard",
    "parry": "Parry", "walk": "Walk", "chop": "Overhead chop", "deflected": "Parried",
    "collapse": "Bone collapse", "cast": "Cast", "stagger": "Stagger", "ash": "Ash",
}


def label(drawing, xy, text, size=16):
    drawing.text(xy, text, font=ImageFont.load_default(size=size), fill=INK)


def sample(image, cell, column, row, size):
    left, top = column * cell, row * cell
    return image.crop((left, top, left + cell, top + cell)).resize(
        (size, size), Image.Resampling.NEAREST
    )


def preview(folder, output):
    output.mkdir(parents=True, exist_ok=True)
    atlas = json.loads((folder / "atlas.json").read_text(encoding="utf-8"))
    cell, directions = atlas["cell_px"], atlas["directions"]
    size = 144
    by_actor = {}
    for clip in atlas["clips"]:
        image = Image.open(folder / clip["file"]).convert("RGBA")
        by_actor.setdefault(clip["actor"], []).append((clip, image))
    board = Image.new("RGB", (size * len(directions), (size + 33) * len(by_actor) + 36), BACKGROUND)
    draw = ImageDraw.Draw(board)
    label(draw, (12, 10), "Shield Attack   /   Character rotations", 20)
    for i, (actor, clips) in enumerate(by_actor.items()):
        idle, sheet = next((clip, sheet) for clip, sheet in clips if clip["action"] == "idle")
        y = 36 + (size + 33) * i
        label(draw, (10, y + 5), LABELS[actor], 17)
        for row, heading in enumerate(directions):
            x = row * size
            draw.rectangle((x + 1, y + 30, x + size - 2, y + size + 27), fill=PANEL)
            frame = sample(sheet, cell, 0, row, size)
            board.paste(frame, (x, y + 28), frame)
            label(draw, (x + size - 32, y + 37), heading, 13)
        # Show every facing and action together. Signal the end of one-shots with a brief pause.
        size_gif, caption = 90, 24
        columns = len(clips)
        count = max(clip["frames"] for clip, _ in clips) + 6
        frames = []
        cache = {(clip["action"], col, row): sample(sheet, cell, col, row, size_gif)
                 for clip, sheet in clips for row in range(len(directions))
                 for col in range(clip["frames"])}
        for t in range(count):
            frame = Image.new("RGB", (columns * size_gif + 34, caption + len(directions) * size_gif), BACKGROUND)
            titles = ImageDraw.Draw(frame)
            for col, (clip, _) in enumerate(clips):
                x = 34 + col * size_gif
                label(titles, (x + 5, 5), LABELS[clip["action"]], 10)
                index = t % clip["frames"] if clip["loop"] else min(t, clip["frames"] - 1)
                for row, heading in enumerate(directions):
                    y = caption + row * size_gif
                    titles.rectangle((x + 1, y + 1, x + size_gif - 2, y + size_gif - 2), fill=PANEL)
                    tile = cache[clip["action"], index, row]
                    frame.paste(tile, (x, y), tile)
                    if col == 0:
                        label(titles, (6, y + size_gif // 2 - 4), heading, 11)
            frames.append(frame)
        frames[0].save(output / f"pixellab-256-{actor}-motion.gif", save_all=True,
                       append_images=frames[1:], duration=round(1000 / atlas["fps"]), loop=0)
    board.save(output / "pixellab-256-rotations.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas-dir", type=Path, default=ROOT / "assets/pixellab-sprites")
    parser.add_argument("--output", type=Path, default=ROOT / "shots")
    args = parser.parse_args()
    preview(args.atlas_dir, args.output)
