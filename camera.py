"""월드 좌표(m)와 화면 좌표(pixel)를 분리하는 추적 카메라."""


class Camera:
    def __init__(self, width_px, height_px, height_m):
        self.width_px, self.height_px = width_px, height_px
        self.pixels_per_meter = height_px / height_m
        self.width_m = width_px / self.pixels_per_meter
        self.height_m = height_m
        self.x = self.y = 0.0

    def follow(self, target, arena):
        limit_x = max(0.0, arena.radius - self.width_m / 2)
        limit_y = max(0.0, arena.radius - self.height_m / 2)
        self.x = max(-limit_x, min(limit_x, target.x))
        self.y = max(-limit_y, min(limit_y, target.y))

    def to_screen(self, x, y):
        return (self.width_px / 2 + (x - self.x) * self.pixels_per_meter,
                self.height_px / 2 + (y - self.y) * self.pixels_per_meter)

    def to_world(self, x, y):
        return (self.x + (x - self.width_px / 2) / self.pixels_per_meter,
                self.y + (y - self.height_px / 2) / self.pixels_per_meter)
