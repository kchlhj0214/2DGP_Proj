"""월드 좌표(m)와 화면 좌표(pixel)를 분리하는 추적 카메라."""


class Camera:
    def __init__(self, width_px, height_px, height_m, floor_y_ratio=1.0):
        self.width_px, self.height_px = width_px, height_px
        self.base_pixels_per_meter = height_px / height_m
        self.zoom = 1.0
        self.floor_y_ratio = floor_y_ratio
        self.width_m = width_px / self.pixels_per_meter
        self.height_m = height_m
        self.x = self.y = 0.0
        self.shake_x = self.shake_y = 0.0

    @property
    def pixels_per_meter(self):
        return self.base_pixels_per_meter * self.zoom

    def follow(self, target):
        # 이동 가능한 영역과 카메라 범위를 분리해 경계에서도 항상 중앙에 둔다.
        self.x, self.y = target.x, target.y

    def to_screen(self, x, y):
        return (self.width_px / 2 + (x - self.x) * self.pixels_per_meter + self.shake_x,
                self.height_px / 2 + (y - self.y) * self.pixels_per_meter * self.floor_y_ratio + self.shake_y)

    def to_world(self, x, y):
        return (self.x + (x - self.width_px / 2 - self.shake_x) / self.pixels_per_meter,
                self.y + (y - self.height_px / 2 - self.shake_y) / (self.pixels_per_meter * self.floor_y_ratio))
