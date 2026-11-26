"""A single ground-slam burst, with stone tips rising from the whole impact disk."""

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
                           rng.uniform(.26, .61), rng.uniform(.65, 2.65), rng.uniform(-.55, .55)))
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
        # The fractured surface fills the entire hit disc on the first impact frame.
        for left, right in zip(edge, edge[1:] + edge[:1]):
            color = (54, 42, 40, 213)
            triangle((cx, cy, (97, 71, 56, 221)), (*left, color), (*right, color))

        scale = camera.pixels_per_meter
        for crack in self.fissures:
            points = [camera.to_screen(*point) for point in crack]
            for index, ((x1, y1), (x2, y2)) in enumerate(zip(points, points[1:])):
                thickness = scale * (.19 - index * .025)
                shade, lip = (37, 29, 31, 212), (147, 104, 76, 152)
                triangle((x1, y1, lip), (x1 + thickness, y1 - thickness, shade), (x2, y2, shade))
                triangle((x1 + thickness, y1 - thickness, shade), (x2, y2, lip),
                         (x2 + thickness * .6, y2 - thickness * .6, shade))
        for x, y, width, height, lean in self.spikes:
            sx, sy = camera.to_screen(x, y)
            w, h = width * scale, height * scale * growth
            point = (sx + lean * w, sy + h)
            left, right = (sx - w, sy), (sx + w, sy + .15 * w)
            front = (sx + .16 * w, sy - .40 * w)
            ridge = (sx - .18 * w, sy + .35 * h)
            triangle((*left, (71, 52, 48, 255)), (*front, (44, 33, 36, 255)), (*ridge, (168, 132, 99, 255)))
            triangle((*left, (91, 68, 60, 255)), (*ridge, (168, 132, 99, 255)), (*point, (225, 192, 144, 255)))
            triangle((*point, (200, 166, 125, 255)), (*ridge, (114, 82, 65, 255)), (*right, (76, 53, 46, 255)))
            triangle((*ridge, (117, 84, 67, 255)), (*front, (48, 34, 37, 255)), (*right, (73, 49, 43, 255)))

        renderer = canvas.renderer
        blend = c_int()
        pico2d.SDL_GetRenderDrawBlendMode(renderer, byref(blend))
        pico2d.SDL_SetRenderDrawBlendMode(renderer, pico2d.SDL_BLENDMODE_BLEND)
        try:
            pico2d.SDL_RenderGeometry(renderer, None, (pico2d.SDL_Vertex * len(vertices))(*vertices),
                                      len(vertices), None, 0)
        finally:
            pico2d.SDL_SetRenderDrawBlendMode(renderer, blend.value)
