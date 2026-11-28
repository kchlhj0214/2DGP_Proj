"""Import reviewed PixelLab Workbench sheets into the game's boss atlas."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from math import cos, radians, sin
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageChops, ImageOps

from tools.build_pixellab_motion import close_joint_seam, pixel_regions
from tools.pixellab_boss_scene import DIRECTIONS, OFFSET, RIG, ROOT, pose, view_joints

SOURCE = ROOT / 'art/boss/pixellab'
SLAM_PLATES = ROOT / 'art/boss/animations/slam'
LINING = ROOT / 'art/boss/lining.png'
ASSETS = ROOT / 'assets/pixellab-sprites'
MANIFEST = ROOT / 'art/boss/workbench.json'
CELL, ORIGIN = 320, (160, 244)
SCALE, COLUMNS = .86, 4


def fetch_sheet(export, direction, path):
    if path.is_file():
        return
    drawing = drawing_for(export, direction)
    url = f'https://api.pixellab.ai/mcp/pixel-tools/{drawing}/assets/{direction}/full.png'
    request = Request(url, headers={'User-Agent': 'Shield Attack art builder'})
    with urlopen(request, timeout=40) as response:
        png = response.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def drawing_for(export, direction):
    return export.get('directions', {}).get(direction, export['drawing'])


def export_path(exports, export, direction):
    return exports / drawing_for(export, direction) / f'{direction}.png'


def repair_joints(frame, view, row, reflected):
    joints = view_joints(view)
    motion = dict(zip(RIG['columns'], row, strict=True))
    moves = pose(view, motion, joints)
    hinges = [('weapon_arm', joints[1], 12, 2), ('grip', joints[2], 12, 2)]
    hinges.extend((f'thigh_{index}', complex(*hip), 18, 4)
                  for index, (hip, _, _, _) in enumerate(view['legs']))
    for node, rest, radius, gap in hinges:
        center = rest + complex(*moves[node]['at'])
        if reflected:
            center = complex(frame.width - 1 - center.real, center.imag)
        close_joint_seam(frame, center, radius=radius, gap=gap)


def normalize(frame, offset, source_foot, cell, origin):
    alpha = np.array(frame.getchannel('A'))
    regions = sorted(pixel_regions(alpha > 0), key=len, reverse=True)
    for region in regions[1:]:
        if len(region) <= 45:
            y, x = zip(*region)
            alpha[y, x] = 0
    frame.putalpha(Image.fromarray(alpha))
    bounds = frame.getbbox()
    if bounds is None or min(bounds[:2]) <= 0 or max(bounds[2:]) >= frame.width:
        raise ValueError('PixelLab export contains an empty or clipped frame')
    ox, oy = offset
    anchor_x, anchor_y = ox + 128, oy + source_foot
    target = (origin[0] + round((bounds[0] - anchor_x) * SCALE),
              origin[1] + round((bounds[1] - anchor_y) * SCALE))
    frame = frame.crop(bounds)
    frame = frame.resize(tuple(round(length * SCALE) for length in frame.size), Image.Resampling.NEAREST)
    if min(target) <= 0 or max(a + b for a, b in zip(target, frame.size)) >= cell:
        raise ValueError('Boss frame needs more room in the in-game atlas')
    out = Image.new('RGBA', (cell, cell))
    out.paste(frame, target)
    return out


def load_lining():
    # PixelLab sheet panels cover source x=64..191 for each original direction.
    layers = {}
    with Image.open(LINING) as sheet:
        for column, direction in enumerate(('south', 'south-east', 'east')):
            layer = Image.new('RGBA', (256, 256))
            layer.paste(sheet.crop((128 * column, 0, 128 * (column + 1), 256)), (64, 0))
            layers[direction] = layer
    return layers


def add_lining(frame, layer, view, direction, row, foot, origin):
    """Move the hand-painted concealed surfaces with the cape or torso."""
    joints = view_joints(view)
    node, pivot = ('torso', joints[0]) if view['id'] == 'east' else ('cape', joints[-1])
    motion = dict(zip(RIG['columns'], row, strict=True))
    placement = pose(view, motion, joints)[node]
    shift = complex(*placement['at']) - complex(*OFFSET)
    angle = radians(placement['angle'])
    c, s = cos(angle), sin(angle)
    mirror = 1 if direction == view['id'] else -1
    center_x = 128 if mirror == 1 else 127
    anchor = complex(center_x - mirror * origin[0] / SCALE, foot - origin[1] / SCALE)
    start = (anchor - pivot - shift) * complex(c, -s) + pivot
    layer = layer.transform(frame.size, Image.Transform.AFFINE,
                            (mirror * c / SCALE, s / SCALE, start.real,
                             -mirror * s / SCALE, c / SCALE, start.imag),
                            Image.Resampling.NEAREST)
    bounds = frame.getbbox()
    backing = Image.new('RGBA', frame.size)
    backing.paste(layer.crop(bounds), bounds[:2])
    transparent = frame.getchannel('A').point(lambda opacity: 0 if opacity else 255)
    frame.paste(backing, mask=ImageChops.multiply(backing.getchannel('A'), transparent))
    return frame


def slam_plate(direction, index):
    # Preserve the original two-handed PixelLab strike plates where available.
    view = {'south': 'S', 'east': 'E', 'west': 'E'}.get(direction)
    if view is None or index >= 8:
        return None
    if direction == 'south' and index >= 4:
        index = 7
    with Image.open(SLAM_PLATES / view / f'{index}.png') as sprite:
        frame = sprite.convert('RGBA')
    if direction == 'west':
        frame = ImageOps.mirror(frame)
    return frame


def build(exports, destination, fetch):
    metadata = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if set(metadata) != set(RIG['clips']):
        raise ValueError('A boss clip is missing a PixelLab export')
    atlas_path = destination / 'atlas.json'
    atlas = json.loads(atlas_path.read_text(encoding='utf-8'))
    atlas['clips'] = [clip for clip in atlas['clips']
                      if clip['actor'] != 'boss' or clip['action'] == 'idle']
    feet = {}
    views = {view['id']: view for view in RIG['views']}
    lining = load_lining()
    for direction in DIRECTIONS:
        reference = RIG['mirrors'].get(direction, direction)
        with Image.open(SOURCE / f'{reference}.png') as sprite:
            feet[direction] = sprite.convert('RGBA').getbbox()[3] - 1
    if fetch:
        with ThreadPoolExecutor(max_workers=8) as pool:
            downloads = [pool.submit(fetch_sheet, info, direction, export_path(exports, info, direction))
                         for info in metadata.values() for direction in DIRECTIONS]
            for download in downloads:
                download.result()
    for action, rows in RIG['clips'].items():
        export = metadata[action]
        source_cell, offset = export['cell_px'], export['offset']
        count = len(rows)
        cell, origin = (352, (176, 244)) if action == 'collapse' else (CELL, ORIGIN)
        sheet = Image.new('RGBA', (cell * count, cell * len(DIRECTIONS)))
        for row, direction in enumerate(DIRECTIONS):
            reference = RIG['mirrors'].get(direction, direction)
            with Image.open(export_path(exports, export, direction)) as source:
                image = source.convert('RGBA')
            if image.size != (COLUMNS * source_cell, (count + COLUMNS - 1) // COLUMNS * source_cell):
                raise ValueError(f'PixelLab sheet does not match {action}/{direction}')
            for index in range(count):
                x, y = index % COLUMNS * source_cell, index // COLUMNS * source_cell
                source_frame = slam_plate(direction, index) if action == 'slam' else None
                from_workbench = source_frame is None
                source_offset = offset if from_workbench else (0, 0)
                if from_workbench:
                    source_frame = image.crop((x, y, x + source_cell, y + source_cell))
                    repair_joints(source_frame, views[reference], rows[index], direction != reference)
                try:
                    frame = normalize(source_frame, source_offset, feet[direction], cell, origin)
                except ValueError as error:
                    raise ValueError(f'{action}/{direction}/{index + 1}: {error}') from error
                if from_workbench and reference in lining:
                    frame = add_lining(frame, lining[reference], views[reference], direction,
                                       rows[index], feet[direction], origin)
                sheet.paste(frame, (index * cell, row * cell))
        name = f'boss-{action}'
        sheet.save(destination / f'{name}.png', optimize=True)
        flash = Image.new('RGBA', sheet.size, 'white')
        flash.putalpha(sheet.getchannel('A'))
        flash.save(destination / f'{name}-flash.png', optimize=True)
        atlas['clips'].append({'actor': 'boss', 'action': action, 'frames': count, 'loop': action == 'walk',
                               'file': f'{name}.png', 'cell_px': cell, 'origin_px': list(origin)})
    atlas_path.write_text(json.dumps(atlas, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exports', type=Path, default=ROOT / '.scratch/pixellab-boss')
    parser.add_argument('--output', type=Path, default=ASSETS)
    parser.add_argument('--fetch', action='store_true', help='Download the reviewed sheets from PixelLab')
    args = parser.parse_args()
    build(args.exports, args.output, args.fetch)
