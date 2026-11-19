"""pico2d sprite sheets with fixed foot anchors and eight facing directions."""

import json
from math import floor, pi
from pathlib import Path

import pico2d

from presentation_data import VISUALS

ROOT = Path(__file__).resolve().parent


class SpriteLibrary:
    def __init__(self):
        settings = VISUALS['sprites']
        atlas = ROOT / settings['atlas']
        data = json.loads(atlas.read_text(encoding='utf-8'))
        self.fps = data['fps']
        self.cell = data['cell_px']
        self.anchor = data['origin_px']
        self.body_pixels = settings['body_height_px']
        self.clips = {}
        for clip in data['clips']:
            actor, action = clip['actor'], clip['action']
            directory = ROOT / settings['asset_dir']
            source = (directory if action == 'deflected' else atlas.parent) / clip['file']
            white = directory / f'{actor}-{action}-flash.png'
            images = (pico2d.load_image(str(source)), pico2d.load_image(str(white)))
            if any((image.w, image.h) != (self.cell * clip['frames'], self.cell * 8)
                   for image in images):
                raise ValueError(f'스프라이트 시트 크기가 다릅니다: {actor}/{action}')
            self.clips[actor, action] = clip, images

    @staticmethod
    def direction(angle):
        return floor((angle + pi / 2) / (pi / 4) + .5) % 8

    def draw(self, actor, action, owner, camera, angle, elapsed=0.0, frame=None, flash=False):
        clip, images = self.clips[actor, action]
        index = int(elapsed * self.fps) if frame is None else int(frame)
        count = clip['frames']
        index = index % count if clip['loop'] else min(count - 1, max(0, index))
        x, y = camera.to_screen(owner.x, owner.y - owner.height / 2)
        scale = owner.height * camera.pixels_per_meter / self.body_pixels
        half = self.cell / 2
        x += (half - self.anchor[0]) * scale
        y += (self.anchor[1] - half) * scale
        size = self.cell * scale
        bottom = (7 - self.direction(angle)) * self.cell
        images[bool(flash)].clip_draw(index * self.cell, bottom, self.cell, self.cell, x, y, size, size)
