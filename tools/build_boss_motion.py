"""Import reviewed PixelLab Workbench sheets into the game's boss atlas."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from math import ceil, cos, radians, sin, sqrt
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image, ImageChops, ImageOps

from tools.build_pixellab_motion import close_joint_seam, pixel_regions
from sprite_layout import cell_slot, sheet_size
from tools.pixellab_boss_scene import (ATTACK_PHASES, DIRECTIONS, OFFSET, RIG, ROOT,
                                       SUBFRAMES, expanded_rows, pose, view_joints)

SOURCE = ROOT / 'art/boss/pixellab'
SLAM_PLATES = ROOT / 'art/boss/animations/slam'
LINING = ROOT / 'art/boss/lining.png'
STAGGER_LINING = ROOT / 'art/boss/stagger-lining.png'
ASSETS = ROOT / 'assets/pixellab-sprites'
MANIFEST = ROOT / 'art/boss/workbench.json'
CELL, ORIGIN = 320, (160, 244)
SCALE, COLUMNS = .86, 4
MAX_SHEET_SIDE = 4096


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


def load_lining(path, directions, panel_width):
    # PixelLab sheet panels start at source x=64 for each original direction.
    layers = {}
    with Image.open(path) as sheet:
        if sheet.width != panel_width * len(directions) or sheet.height > 256:
            raise ValueError(f'보스 안감 시트 크기가 잘못되었습니다: {path}')
        for column, direction in enumerate(directions):
            layer = Image.new('RGBA', (256, 256))
            layer.paste(sheet.crop((panel_width * column, 0, panel_width * (column + 1), sheet.height)), (64, 0))
            layers[direction] = layer
    return layers


def add_lining(frame, layer, view, direction, row, foot, origin, node):
    """Move the hand-painted concealed surfaces with the cape or torso."""
    joints = view_joints(view)
    pivot = joints[0] if node == 'torso' else joints[-1]
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
    with Image.open(SLAM_PLATES / view / f'{index}.png') as sprite:
        frame = sprite.convert('RGBA')
    if direction == 'west':
        frame = ImageOps.mirror(frame)
    return frame


def idle_steps(action, count):
    steps = [0] if action in ATTACK_PHASES else []
    if action in ('stagger', 'recover', 'swing', 'slam'):
        steps.extend(range(count - SUBFRAMES, count))
    return steps


def pack_frames(action, frames, origin, atlas_fps):
    bounds = [frame.getbbox() for frame in frames]
    x0 = min(origin[0], *(box[0] for box in bounds)) - 1
    y0 = min(origin[1], *(box[1] for box in bounds)) - 1
    x1 = max(origin[0] + 1, *(box[2] for box in bounds)) + 1
    y1 = max(origin[1] + 1, *(box[3] for box in bounds)) + 1
    width, height = x1 - x0, y1 - y0
    count = len(frames) // len(DIRECTIONS)
    columns = min(ceil(sqrt(len(frames) * height / width)), MAX_SHEET_SIDE // width)
    clip = {'actor': 'boss', 'action': action, 'frames': count, 'loop': action in ('idle', 'walk'),
            'file': f'boss-{action}.png', 'cell_px': width, 'cell_height_px': height,
            'columns': columns, 'origin_px': [origin[0] - x0, origin[1] - y0]}
    if action in ATTACK_PHASES:
        clip['phases'] = [count * SUBFRAMES for count in ATTACK_PHASES[action]]
    if rest := idle_steps(action, count):
        clip['idle_frames'] = rest
    fps = {'walk': 10, 'charge': 18, 'slam': 16, 'collapse': atlas_fps}.get(action)
    if fps:
        clip['fps'] = fps * SUBFRAMES
    dimensions = sheet_size(clip, width, len(DIRECTIONS))
    if max(dimensions) > MAX_SHEET_SIDE:
        raise ValueError(f'보스 스프라이트 시트가 너무 큽니다: {action}')
    sheet = Image.new('RGBA', dimensions)
    for index, frame in enumerate(frames):
        facing, step = divmod(index, count)
        row, column = cell_slot(clip, facing, step)
        sheet.paste(frame.crop((x0, y0, x1, y1)), (column * width, row * height))
    return clip, sheet


def save_clip(destination, action, frames, origin, fps):
    clip, sheet = pack_frames(action, frames, origin, fps)
    sheet.save(destination / clip['file'], optimize=True)
    flash = Image.new('RGBA', sheet.size, 'white')
    flash.putalpha(sheet.getchannel('A'))
    flash.save(destination / f'boss-{action}-flash.png', optimize=True)
    return clip


def build(exports, destination, fetch):
    metadata = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if set(metadata) != set(RIG['clips']):
        raise ValueError('A boss clip is missing a PixelLab export')
    atlas_path = destination / 'atlas.json'
    atlas = json.loads(atlas_path.read_text(encoding='utf-8'))
    atlas['clips'] = [clip for clip in atlas['clips'] if clip['actor'] != 'boss']
    feet = {}
    views = {view['id']: view for view in RIG['views']}
    lining = load_lining(LINING, ('south', 'south-east', 'east'), 128)
    stagger_lining = load_lining(STAGGER_LINING, ('south-east', 'east', 'north-east', 'north'), 112)
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
    clips = {}
    rest = {}
    # The repaired final stagger pose supplies one neutral stance for every transition.
    for action in ('stagger', *(name for name in RIG['clips'] if name != 'stagger')):
        rows = expanded_rows(action)
        export = metadata[action]
        source_cell, offset = export['cell_px'], export['offset']
        count = len(rows)
        neutral = idle_steps(action, count)
        cell, origin = (352, (176, 244)) if action == 'collapse' else (CELL, ORIGIN)
        frames = []
        for direction in DIRECTIONS:
            reference = RIG['mirrors'].get(direction, direction)
            with Image.open(export_path(exports, export, direction)) as source:
                image = source.convert('RGBA')
            if image.size != (COLUMNS * source_cell, (count + COLUMNS - 1) // COLUMNS * source_cell):
                raise ValueError(f'PixelLab sheet does not match {action}/{direction}')
            for index in range(count):
                x, y = index % COLUMNS * source_cell, index // COLUMNS * source_cell
                source_frame = slam_plate(direction, index // SUBFRAMES) if action == 'slam' else None
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
                    node = 'torso' if reference == 'east' else 'cape'
                    add_lining(frame, lining[reference], views[reference], direction,
                               rows[index], feet[direction], origin, node)
                if action == 'stagger' and reference in stagger_lining:
                    add_lining(frame, stagger_lining[reference], views[reference], direction,
                               rows[index], feet[direction], origin, 'cape')
                if action == 'stagger' and index == count - 1:
                    rest[direction] = frame
                elif action != 'stagger' and index in neutral:
                    frame = rest[direction]
                frames.append(frame)
        clips[action] = save_clip(destination, action, frames, origin, atlas['fps'])
    atlas['clips'].append(save_clip(destination, 'idle', list(rest.values()), ORIGIN, atlas['fps']))
    atlas['clips'].extend(clips[action] for action in RIG['clips'])
    atlas_path.write_text(json.dumps(atlas, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exports', type=Path, default=ROOT / '.scratch/pixellab-boss')
    parser.add_argument('--output', type=Path, default=ASSETS)
    parser.add_argument('--fetch', action='store_true', help='Download the reviewed sheets from PixelLab')
    args = parser.parse_args()
    build(args.exports, args.output, args.fetch)
