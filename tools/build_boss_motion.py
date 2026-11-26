"""Bake the eight PixelLab boss rotations and optional PixelLab attack frames."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw
import numpy as np

from tools.build_pixellab_motion import pixel_regions
from tools.generate_data import ROOT

DATA = json.loads((ROOT / 'data/boss_motion.json').read_text(encoding='utf-8'))
SIZE = 256
ANCHOR = 220


def rotation_layer(image, row):
    mask = Image.new('L', image.size)
    ImageDraw.Draw(mask).polygon(row['arm'], fill=255)
    arm = image.copy()
    arm.putalpha(ImageChops.multiply(image.getchannel('A'), mask))
    return arm, mask


def normalize(image, foot_y):
    scale = 0.86
    out = Image.new('RGBA', (SIZE, SIZE))
    out.paste(image.resize((round(SIZE * scale), round(SIZE * scale)), Image.Resampling.NEAREST),
              (round(SIZE * (1 - scale) / 2), ANCHOR - round(foot_y * scale)))
    return out


def render_pose(image, arm, mask, row, pose, foot_y):
    lean, bend, rotation = pose
    turn = row['turn']
    body = image.copy()
    if rotation and (row['id'] not in ('NW', 'W') or abs(rotation) > 30):
        body.putalpha(ImageChops.subtract(image.getchannel('A'), mask))
        angle = turn * -rotation
        weapon = arm.rotate(angle, Image.Resampling.NEAREST, center=tuple(row['shoulder']))
        # Retain a small overlap at the shoulder so the separated arm stays attached.
        x, y = row['shoulder']
        joint = (x - 12, y - 10, x + 13, y + 13)
        body.alpha_composite(image.crop(joint), joint[:2])
        body.alpha_composite(weapon)
    slope = turn * lean / 160
    squash = (160 - bend) / 160
    moved = body.transform((SIZE, SIZE), Image.Transform.AFFINE,
                           (1, slope / squash, -slope * foot_y / squash,
                            0, 1 / squash, foot_y * (1 - 1 / squash)),
                           Image.Resampling.NEAREST)
    return normalize(moved, foot_y)


def clean_frame(frame):
    alpha = np.array(frame.getchannel('A'))
    regions = sorted(pixel_regions(alpha > 0), key=len, reverse=True)
    for region in regions[1:]:
        y, x = zip(*region)
        alpha[y, x] = 0
    frame.putalpha(Image.fromarray(alpha))
    return frame


def build(source, destination, animated):
    atlas_path = destination / 'atlas.json'
    atlas = json.loads(atlas_path.read_text(encoding='utf-8'))
    directions = atlas['directions']
    rows = DATA['rotations']
    if [row['id'] for row in rows] != directions or atlas['origin_px'] != [128, ANCHOR]:
        raise ValueError('Boss rotations and atlas do not share directions and anchor')
    clips = [clip for clip in atlas['clips'] if clip['actor'] != 'boss']
    rigs = {}
    for row in rows:
        image = Image.open(source / (row['file'] + '.png')).convert('RGBA')
        arm, mask = rotation_layer(image, row)
        rigs[row['id']] = (image, arm, mask, row, image.getbbox()[3] - 1)
    for hidden, visible in (('W', 'E'), ('NW', 'NE')):
        image, _, mask, row, foot_y = rigs[hidden]
        _, arm, _, donor, _ = rigs[visible]
        x, y = row['shoulder']
        dx, dy = donor['shoulder']
        # Reveal the matching club arm from behind the cape for the larger swings.
        arm = ImageChops.offset(arm.transpose(Image.Transpose.FLIP_LEFT_RIGHT), x - (SIZE - 1 - dx), y - dy)
        rigs[hidden] = (image, arm, mask, row, foot_y)
    for clip in DATA['poses']:
        action, frames = clip['id'], clip['frames']
        name = f'boss-{action}'
        sheet = Image.new('RGBA', (SIZE * len(frames), SIZE * len(rows)))
        for y, rig in enumerate(rigs.values()):
            for x, pose in enumerate(frames):
                custom = animated / action / rig[3]['id'] / f'{x}.png'
                if custom.is_file():
                    frame = normalize(Image.open(custom).convert('RGBA'), rig[4])
                else:
                    frame = render_pose(*rig[:4], pose, rig[4])
                frame = clean_frame(frame)
                box = frame.getbbox()
                if not box or min(box[:2]) == 0 or max(box[2:]) == SIZE:
                    raise ValueError(f'Empty or clipped boss sprite: {action}, {directions[y]}, frame {x}')
                sheet.paste(frame, (x * SIZE, y * SIZE))
        sheet.save(destination / f'{name}.png', optimize=True)
        flash = Image.new('RGBA', sheet.size, 'white')
        flash.putalpha(sheet.getchannel('A'))
        flash.save(destination / f'{name}-flash.png', optimize=True)
        clips.append({'actor': 'boss', 'action': action, 'frames': len(frames),
                      'loop': clip['loop'], 'file': f'{name}.png'})
    atlas['clips'] = clips
    atlas_path.write_text(json.dumps(atlas, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'art/boss/pixellab')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/pixellab-sprites')
    parser.add_argument('--animated', type=Path, default=ROOT / 'art/boss/animations')
    args = parser.parse_args()
    build(args.source, args.output, args.animated)
