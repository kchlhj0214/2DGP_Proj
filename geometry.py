"""미터 단위 볼록 히트박스와 회전 직사각형의 SAT 충돌."""

from ctypes import byref, c_int
from math import atan2, cos, hypot, pi, sin, sqrt

import pico2d
import pico2d.pico2d as canvas


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
    if len(points) < 3:
        return False
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


def warning_strength(age, windup):
    if not 0 <= age < windup:
        return 0
    phase = (2 * age / windup) % 1
    return max(0.0, min(1.0, phase / .14, (.79 - phase) / .25))


def draw_sweep_warning(x, y, angle, length, width, spread, camera, opacity):
    # The far corners sweep a wider arc than the blade's centerline.
    half_width = width / 2
    end_angle = spread / 2 + atan2(half_width, length)
    reach = hypot(length, half_width)
    side_angle = spread / 2 + pi / 2
    outline = [(-side_angle, half_width)]
    outline.extend((end_angle * (i / 12 - 1), reach) for i in range(25))
    outline.append((side_angle, half_width))
    vertices = []
    for fraction, (r, g, b, alpha) in ((0, (135, 10, 17, 40)),
                                        (.57, (224, 20, 31, 114)),
                                        (1, (255, 68, 49, 207))):
        for relative, radius in outline:
            a, distance = angle + relative, radius * fraction
            sx, sy = camera.to_screen(x + cos(a) * distance, y + sin(a) * distance)
            vertices.append(pico2d.SDL_Vertex(
                pico2d.SDL_FPoint(sx, camera.height_px - 1 - sy),
                pico2d.SDL_Color(r, g, b, round(alpha * opacity)), pico2d.SDL_FPoint(0, 0)))
    columns = len(outline)
    indices = []
    for i in range(2):
        for j in range(columns - 1):
            a = i * columns + j
            b = a + columns
            indices.extend((a, b, b + 1, a, b + 1, a + 1))
    renderer = canvas.renderer
    blend = c_int()
    pico2d.SDL_GetRenderDrawBlendMode(renderer, byref(blend))
    pico2d.SDL_SetRenderDrawBlendMode(renderer, pico2d.SDL_BLENDMODE_BLEND)
    try:
        pico2d.SDL_RenderGeometry(renderer, None,
                                  (pico2d.SDL_Vertex * len(vertices))(*vertices), len(vertices),
                                  (c_int * len(indices))(*indices), len(indices))
    finally:
        pico2d.SDL_SetRenderDrawBlendMode(renderer, blend.value)
