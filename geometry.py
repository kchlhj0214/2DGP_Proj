"""미터 단위 볼록 히트박스와 회전 직사각형의 SAT 충돌."""

from math import cos, sin, sqrt

import pico2d


def box_points(bb):
    left, bottom, right, top = bb
    return [(left, bottom), (right, bottom), (right, top), (left, top)]


def oriented_box(x, y, angle, length, width):
    ux, uy = cos(angle), sin(angle)
    vx, vy = -uy * width / 2, ux * width / 2
    return [(x + vx, y + vy), (x + ux * length + vx, y + uy * length + vy),
            (x + ux * length - vx, y + uy * length - vy), (x - vx, y - vy)]


def intersects(first, second):
    for polygon in (first, second):
        for start, end in zip(polygon, polygon[1:] + polygon[:1]):
            ax, ay = -(end[1] - start[1]), end[0] - start[0]
            a = [x * ax + y * ay for x, y in first]
            b = [x * ax + y * ay for x, y in second]
            if max(a) < min(b) - 1e-9 or max(b) < min(a) - 1e-9:
                return False
    return True


def circle_intersects_polygon(x, y, radius, points):
    """원과 볼록 다각형의 정확한 가장자리/내부 판정."""
    crosses = []
    for start, end in zip(points, points[1:] + points[:1]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length_sq = dx * dx + dy * dy
        fraction = max(0, min(1, ((x - start[0]) * dx + (y - start[1]) * dy) / length_sq)) if length_sq else 0
        px, py = start[0] + fraction * dx, start[1] + fraction * dy
        if (x - px) ** 2 + (y - py) ** 2 <= radius ** 2 + 1e-9:
            return True
        crosses.append(dx * (y - start[1]) - dy * (x - start[0]))
    return all(v >= 0 for v in crosses) or all(v <= 0 for v in crosses)


def ray_length(x, y, angle, radius):
    along = x * cos(angle) + y * sin(angle)
    discriminant = along * along + radius * radius - x * x - y * y
    return max(0.0, -along + sqrt(max(0.0, discriminant))) if discriminant >= 0 else 0.0


def draw_polygon(points, camera, color):
    for start, end in zip(points, points[1:] + points[:1]):
        pico2d.draw_line(*camera.to_screen(*start), *camera.to_screen(*end), *color)


def draw_sector(x, y, angle, radius, spread, camera, color):
    points = [(x, y)]
    for i in range(25):
        a = angle - spread / 2 + spread * i / 24
        points.append((x + cos(a) * radius, y + sin(a) * radius))
    draw_polygon(points, camera, color)
