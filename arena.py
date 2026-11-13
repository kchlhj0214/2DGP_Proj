"""원형 경기장. 전달받은 경계 판정용 직사각형을 원 내부로 제한한다."""

from math import ceil, hypot, sqrt

import pico2d


class Arena:
    def __init__(self, data, viewport, camera):
        self.radius = viewport['height_m'] * data['diameter_height_ratio'] / 2
        self.grid_m = data['grid_m']
        self.camera = camera

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
        camera = self.camera
        cx, cy = camera.to_screen(0, 0)
        radius_px = round(self.radius * camera.pixels_per_meter)
        pico2d.draw_circle(cx, cy, radius_px, 28, 39, 48, filled=True)

        # 1m 격자를 원 내부에만 그린다. 이동과 크기 비교용 기준선.
        steps = int(ceil(self.radius / self.grid_m))
        for index in range(-steps, steps + 1):
            value = index * self.grid_m
            if abs(value) >= self.radius:
                continue
            reach = sqrt(self.radius ** 2 - value ** 2)
            color = (62, 82, 91) if index % 5 == 0 else (39, 54, 63)
            x1, y1 = camera.to_screen(value, -reach)
            x2, y2 = camera.to_screen(value, reach)
            pico2d.draw_line(x1, y1, x2, y2, *color)
            x1, y1 = camera.to_screen(-reach, value)
            x2, y2 = camera.to_screen(reach, value)
            pico2d.draw_line(x1, y1, x2, y2, *color)
        pico2d.draw_circle(cx, cy, radius_px, 122, 176, 184)
        # 상하좌우 입구 위치만 표시한다. 출현 기능은 아직 구현하지 않는다.
        for x, y in ((0, self.radius), (0, -self.radius),
                     (self.radius, 0), (-self.radius, 0)):
            px, py = camera.to_screen(x, y)
            pico2d.draw_rectangle(px - 5, py - 5, px + 5, py + 5,
                                  237, 179, 92, filled=True)
        pico2d.draw_line(cx - 8, cy, cx + 8, cy, 140, 166, 175)
        pico2d.draw_line(cx, cy - 8, cx, cy + 8, 140, 166, 175)
