"""A ground-slam burst that raises broken masonry from the arena floor."""

from ctypes import byref, c_int
from math import cos, pi, sin, sqrt
from random import Random

import pico2d
import pico2d.pico2d as canvas

from geometry import circle_points


class StoneEruption:
    def __init__(self, x, y, radius, count, duration, seed):
        self.duration = duration
        self.center = (x, y)
        self.rim = circle_points(x, y, radius)
        rng = Random(seed)
        self.fissures = []
        for index in range(13):
            angle = index * 2 * pi / 13 + rng.uniform(-.12, .12)
            points = []
            for fraction in (.07, .20, .40, .57, .78, .96):
                turn = angle + rng.uniform(-.14, .14)
                points.append((x + radius * fraction * cos(turn), y + radius * fraction * sin(turn)))
            self.fissures.append(points)
        golden_angle = pi * (3 - sqrt(5))
        spikes = []
        for index in range(count):
            angle = index * golden_angle + rng.uniform(-.11, .11)
            distance = (radius - .65) * sqrt((index + .5) / count)
            spikes.append((x + distance * cos(angle), y + distance * sin(angle),
                           rng.uniform(.34, .70), rng.uniform(.85, 2.55), rng.uniform(-.55, .55),
                           rng.randint(-8, 8)))
        self.spikes = sorted(spikes, key=lambda spike: spike[1], reverse=True)

    def draw(self, camera, age):
        if not 0 <= age < self.duration:
            return
        progress = age / self.duration
        growth = min(1.0, .62 + 5.5 * progress) * (1 - .82 * max(0.0, (progress - .40) / .60))
        opacity = 1 - progress ** 2
        vertices = []

        def triangle(*points):
            for x, y, color in points:
                vertices.append(pico2d.SDL_Vertex(
                    pico2d.SDL_FPoint(x, camera.height_px - 1 - y),
                    pico2d.SDL_Color(*color[:3], round(color[3] * opacity)), pico2d.SDL_FPoint(0, 0)))

        cx, cy = camera.to_screen(*self.center)
        edge = [camera.to_screen(*p) for p in self.rim]
        # The burst shades the whole disc while leaving the original pavers visible.
        for left, right in zip(edge, edge[1:] + edge[:1]):
            color = (37, 43, 50, 42)
            triangle((cx, cy, (82, 92, 104, 122)), (*left, color), (*right, color))

        scale = camera.pixels_per_meter
        for crack in self.fissures:
            points = [camera.to_screen(*point) for point in crack]
            for index, ((x1, y1), (x2, y2)) in enumerate(zip(points, points[1:])):
                thickness = scale * (.19 - index * .025)
                shade, lip = (23, 29, 36, 208), (110, 118, 128, 125)
                triangle((x1, y1, lip), (x1 + thickness, y1 - thickness, shade), (x2, y2, shade))
                triangle((x1 + thickness, y1 - thickness, shade), (x2, y2, lip),
                         (x2 + thickness * .6, y2 - thickness * .6, shade))
        def face(color, *points):
            for a, b in zip(points[1:], points[2:]):
                triangle((*points[0], color), (*a, color), (*b, color))

        def gray(tone, variation):
            value = tone + variation
            return (value, value + 5, value + 12, 255)

        for x, y, width, height, lean, variation in self.spikes:
            sx, sy = camera.to_screen(x, y)
            w, h = width * scale, height * scale * growth
            point = (sx + lean * w, sy + h)
            left, right = (sx - w, sy), (sx + .93 * w, sy + .12 * w)
            foot = (sx + .15 * w, sy - .34 * w)
            left_corner = (sx + (.32 * lean - .85) * w, sy + .48 * h)
            right_corner = (sx + (.32 * lean + .68) * w, sy + .49 * h)
            ridge = (sx + (.34 * lean + .16) * w, sy + .56 * h)
            notch = (sx + (.57 * lean - .42) * w, sy + .66 * h)
            bevel = (sx + (.66 * lean + .10) * w, sy + .76 * h)

            face((20, 25, 32, 128), left, (sx, sy - .57 * w), right, (sx + .25 * w, sy + .30 * w))
            face(gray(70, variation), left, foot, ridge, left_corner)
            face(gray(48, variation), foot, right, right_corner, ridge)
            face(gray(108, variation), left_corner, notch, point, bevel, ridge)
            face(gray(79, variation), ridge, bevel, point, right_corner)
            face(gray(132, variation), notch, point, bevel)
            face(gray(42, variation), left, foot,
                 (foot[0] - .06 * w, foot[1] + .17 * w), (left[0] + .08 * w, sy + .11 * w))

        renderer = canvas.renderer
        blend = c_int()
        pico2d.SDL_GetRenderDrawBlendMode(renderer, byref(blend))
        pico2d.SDL_SetRenderDrawBlendMode(renderer, pico2d.SDL_BLENDMODE_BLEND)
        try:
            pico2d.SDL_RenderGeometry(renderer, None, (pico2d.SDL_Vertex * len(vertices))(*vertices),
                                      len(vertices), None, 0)
        finally:
            pico2d.SDL_SetRenderDrawBlendMode(renderer, blend.value)
