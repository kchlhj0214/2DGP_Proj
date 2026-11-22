"""원형 경기장. 전달받은 경계 판정용 직사각형을 원 내부로 제한한다."""

from math import hypot, sqrt
from pathlib import Path

import pico2d
from presentation_data import VISUALS
from wave_data import GATES


ART = VISUALS['arena']


class Arena:
    def __init__(self, data, viewport, camera):
        self.radius = viewport['height_m'] * data['diameter_height_ratio'] / 2
        self.camera = camera
        self.art = ()

    def load_art(self):
        root = Path(__file__).resolve().parent
        self.art = tuple(pico2d.load_image(str(root / ART[name]))
                         for name in ('crypt_art', 'gate_frame', 'gate_bars'))

    def update(self):
        pass

    def contains_box(self, x, y, width, height):
        # 원점에서 가장 먼 꼭짓점만 검사하면 네 꼭짓점이 모두 포함된다.
        return hypot(abs(x) + width / 2, abs(y) + height / 2) <= self.radius + 1e-9

    def constrain_box(self, x, y, width, height):
        """가장 먼 꼭짓점을 원에 투영. 축 방향 여백을 지켜 벽을 따라 이동."""
        half_w, half_h = width / 2, height / 2
        if hypot(half_w, half_h) > self.radius:
            raise ValueError('히트박스가 경기장보다 큽니다.')
        if self.contains_box(x, y, width, height):
            return x, y
        far_x, far_y = abs(x) + half_w, abs(y) + half_h
        scale = self.radius / hypot(far_x, far_y)
        far_x, far_y = far_x * scale, far_y * scale
        # 축에 가까운 곳은 투영 후 한 좌표가 반폭보다 작아질 수 있다.
        if far_x < half_w:
            far_x, far_y = half_w, sqrt(max(0.0, self.radius ** 2 - half_w ** 2))
        elif far_y < half_h:
            far_x, far_y = sqrt(max(0.0, self.radius ** 2 - half_h ** 2)), half_h
        return ((1 if x >= 0 else -1) * max(0.0, far_x - half_w),
                (1 if y >= 0 else -1) * max(0.0, far_y - half_h))

    def draw(self):
        if not self.art:
            return
        camera = self.camera
        center_x, center_y = camera.to_screen(0, 0)
        scale = self.radius * camera.pixels_per_meter / ART['crypt_radius_px']
        image = self.art[0]
        image.clip_draw(0, 0, image.w, image.h, center_x, center_y, image.w * scale, image.h * scale)

    def draw_gates(self, waves):
        if not self.art:
            return
        _, frame, bars = self.art
        scale = self.radius * self.camera.pixels_per_meter / ART['crypt_radius_px']
        for gate_id, gate in GATES.items():
            x, y = self.camera.to_screen(gate['x_ratio'] * waves.portal_distance,
                                         gate['y_ratio'] * waves.portal_distance)
            side = gate['x_ratio'] != 0
            width = scale * (0.78 if side else 1)
            # The top of the ironwork slides behind the lintel without scaling the bars.
            lift = round(bars.h * waves.gate_opening(gate_id))
            remaining = bars.h - lift
            if remaining:
                bars.clip_draw(0, 0, bars.w, remaining, x, y + (lift + remaining / 2) * scale,
                               bars.w * width, remaining * scale)
            frame.clip_draw(0, 0, frame.w, frame.h, x, y + frame.h * scale / 2,
                            frame.w * width, frame.h * scale)
