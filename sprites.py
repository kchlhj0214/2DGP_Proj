"""pico2d sprite sheets with fixed foot anchors and eight facing directions."""

import json
from math import ceil, floor, pi
from pathlib import Path

import pico2d

from presentation_data import VISUALS

ROOT = Path(__file__).resolve().parent
SETTINGS = VISUALS['sprites']
ATLAS_PATH = ROOT / SETTINGS['atlas']
ATLAS = json.loads(ATLAS_PATH.read_text(encoding='utf-8'))
CLIPS = {(clip['actor'], clip['action']): clip for clip in ATLAS['clips']}


def direction(angle):
    return floor((angle + pi / 2) / (pi / 4) + .5) % 8


def frame_index(clip, elapsed, frame=None):
    index = int(elapsed * ATLAS['fps']) if frame is None else int(frame)
    count = clip['frames']
    return index % count if clip['loop'] else min(count - 1, max(0, index))


def clip_duration(actor, action):
    return CLIPS[actor, action]['frames'] / ATLAS['fps']


def shield_emitter(owner, action, angle, elapsed):
    clip = CLIPS['hero', action]
    sx, sy = clip['shield_px'][direction(angle)][frame_index(clip, elapsed)]
    ox, oy = ATLAS['origin_px']
    scale = owner.height / SETTINGS['body_height_px']
    return (owner.x + (sx - ox) * scale,
            owner.y - owner.height / 2 + (oy - sy) * scale / owner.camera.floor_y_ratio)


class SpriteLibrary:
    def __init__(self):
        self.fps = ATLAS['fps']
        self.cell = ATLAS['cell_px']
        self.anchor = ATLAS['origin_px']
        self.body_pixels = SETTINGS['body_height_px']
        self.projectile = pico2d.load_image(str(ROOT / SETTINGS['projectile_art']))
        self.clips = {}
        for clip in ATLAS['clips']:
            actor, action = clip['actor'], clip['action']
            directory = ROOT / SETTINGS['asset_dir']
            source = ATLAS_PATH.parent / clip['file']
            flash_source = directory / f'{actor}-{action}-flash.png'
            images = (pico2d.load_image(str(source)), pico2d.load_image(str(flash_source)))
            if any((image.w, image.h) != (self.cell * clip['frames'], self.cell * 8)
                   for image in images):
                raise ValueError(f'스프라이트 시트 크기가 다릅니다: {actor}/{action}')
            self.clips[actor, action] = clip, images

    def draw(self, actor, action, owner, camera, angle, elapsed=0.0, frame=None, flash=False,
             reveal=1.0, clip_at_x=None):
        clip, images = self.clips[actor, action]
        index = frame_index(clip, elapsed, frame)
        x, y = camera.to_screen(owner.x, owner.y - owner.height / 2)
        meters_per_pixel = owner.height / self.body_pixels
        scale = meters_per_pixel * camera.pixels_per_meter
        half = self.cell / 2
        x += (half - self.anchor[0]) * scale
        y += (self.anchor[1] - half) * scale
        bottom = (7 - direction(angle)) * self.cell
        image = images[bool(flash)]
        if actor == 'hero' and flash:
            color = (250, 55, 52) if flash == 'red' else (255, 255, 255)
            pico2d.SDL_SetTextureColorMod(image.texture, *color)
        left, width, height = 0, self.cell, self.cell
        if clip_at_x is not None:
            edge, inward = clip_at_x
            column = self.anchor[0] + (edge - owner.x) / meters_per_pixel
            if inward > 0:
                left = max(0, ceil(column))
                width -= left
            else:
                width = min(self.cell, floor(column))
            if width <= 0:
                return
            x += (left + width / 2 - half) * scale
        elif reveal < 1.0:
            # Skip the transparent padding beneath the feet; expose rows upwards from the foot anchor.
            rows = round(self.anchor[1] * reveal)
            if rows <= 0:
                return
            foot_padding = self.cell - self.anchor[1]
            height = rows + foot_padding
            y -= (self.cell - height) * scale / 2
        image.clip_draw(index * self.cell + left, bottom, width, height, x, y, width * scale, height * scale)

    def draw_projectile(self, projectile, camera):
        x, y = camera.to_screen(projectile.x, projectile.y)
        diameter = projectile.radius * 2 * camera.pixels_per_meter
        self.projectile.draw(x, y, diameter, diameter)
