"""A shield-centered beam with an obtuse flare and a fixed full width."""

from ctypes import byref, c_int
from math import cos, sin

import pico2d
import pico2d.pico2d as canvas

from geometry import box_points, circle_intersects_polygon, intersects, ray_length
from presentation_data import VISUALS
from sprites import shield_emitter


EDGE_STOPS = (
    (0.0, (237, 255, 220, 246)),
    (.20, (186, 249, 208, 236)),
    (.48, (101, 223, 189, 211)),
    (.76, (45, 159, 146, 168)),
    (1.0, (21, 102, 102, 22)),
)


class Beam:
    def __init__(self, owner, energy, stage, settings):
        self.owner = owner
        self.angle = owner.combat.aim
        self.width = stage['beam_width_m']
        self.damage = energy * settings['damage_multiplier']
        self.duration = settings['beam_duration_s']
        self.tick_interval = settings['beam_tick_s']
        self.age = 0.0
        self.ticks = 0
        self.hit_ids = []
        self.apply_tick()
        self.erase_projectiles()

    @property
    def active(self):
        return self.age < self.duration - 1e-9

    def origin(self):
        owner = self.owner
        pose, elapsed = owner.beam_pose()
        return shield_emitter(owner, pose, self.angle, elapsed)

    def profile(self):
        x, y = self.origin()
        length = ray_length(x, y, self.angle, self.owner.arena.radius)
        taper = self.width * VISUALS['beam']['taper_width_ratio']
        return x, y, length, taper

    def polygon(self):
        x, y, length, taper = self.profile()
        if length <= 1e-8:
            return []
        ux, uy = cos(self.angle), sin(self.angle)
        reach = min(taper, length)
        half = self.width / 2 * reach / taper
        def off(distance, lateral):
            return x + ux * distance - uy * lateral, y + uy * distance + ux * lateral
        tip = (x, y)
        if length <= taper:
            return [tip, off(length, half), off(length, -half)]
        return [tip, off(reach, half), off(length, half),
                off(length, -half), off(reach, -half)]

    def apply_tick(self):
        polygon = self.polygon()
        hits = []
        for enemy in self.owner.targets:
            if polygon and enemy.hp > 0 and intersects(polygon, box_points(enemy.get_bb())):
                enemy.take_damage(self.damage)
                hits.append(enemy.identifier)
        self.hit_ids.append(hits)
        self.ticks += 1
        if self.owner.effects:
            self.owner.effects.beam_pulse()

    def update(self, dt):
        self.age += dt
        while self.ticks < 3 and self.age + 1e-9 >= self.ticks * self.tick_interval:
            self.apply_tick()
        if self.active:
            self.erase_projectiles()

    def erase_projectiles(self):
        polygon = self.polygon()
        for projectile in self.owner.projectiles:
            if projectile.active and circle_intersects_polygon(projectile.x, projectile.y, projectile.radius, polygon):
                projectile.active, projectile.result = False, 'beam'

    def draw(self):
        if not self.active:
            return
        camera = self.owner.camera
        x, y, length, taper = self.profile()
        if length <= 1e-8:
            return
        ux, uy = cos(self.angle), sin(self.angle)
        pulse = 1 - min(1, (self.age % self.tick_interval) / .16)
        half = self.width / 2

        def point(distance, fraction):
            offset = half * min(1, distance / taper) * fraction
            return camera.to_screen(x + ux*distance - uy*offset, y + uy*distance + ux*offset)

        lanes = [(-position, color) for position, color in reversed(EDGE_STOPS[1:])] + list(EDGE_STOPS)
        sections = (0, taper, length) if length > taper else (0, length)
        vertices = []
        for distance in sections:
            for offset, color in lanes:
                sx, sy = point(distance, offset)
                r, g, b, a = color
                vertices.append(pico2d.SDL_Vertex(
                    pico2d.SDL_FPoint(sx, camera.height_px - 1 - sy),
                    pico2d.SDL_Color(min(255, round(r + 13*pulse)),
                                     min(255, round(g + 4*pulse)), b, a),
                    pico2d.SDL_FPoint(0, 0)))
        indices = []
        row = len(lanes)
        for i in range(len(sections) - 1):
            for j in range(row - 1):
                a = i*row + j
                b = a + row
                indices.extend((a, b, b+1, a, b+1, a+1))
        renderer = canvas.renderer
        previous = c_int()
        pico2d.SDL_GetRenderDrawBlendMode(renderer, byref(previous))
        pico2d.SDL_SetRenderDrawBlendMode(renderer, pico2d.SDL_BLENDMODE_BLEND)
        try:
            pico2d.SDL_RenderGeometry(renderer, None,
                                      (pico2d.SDL_Vertex * len(vertices))(*vertices), len(vertices),
                                      (c_int * len(indices))(*indices), len(indices))
            for i in range(22):
                fraction = .74 * sin(i*2.34)
                travel = 2.9 + (i % 5) * .52
                a = (i * 1.419 + self.age * travel) % max(1.0, length)
                b = min(length, a + .35 + (i % 4) * .32)
                if a < b:
                    alpha = round(24 + 74*pulse + (1 - abs(fraction))*38)
                    pico2d.draw_line(*point(a, fraction), *point(b, fraction), 221, 255, 223, alpha)
        finally:
            pico2d.SDL_SetRenderDrawBlendMode(renderer, previous.value)

    def draw_emitter(self):
        if not self.active:
            return
        camera = self.owner.camera
        x, y = camera.to_screen(*self.origin())
        pulse = 1 - min(1, (self.age % self.tick_interval) / .13)
        scale = self.owner.height * camera.pixels_per_meter
        radius = max(2, round(scale * (.031 + .027*pulse)))
        previous = c_int()
        renderer = canvas.renderer
        pico2d.SDL_GetRenderDrawBlendMode(renderer, byref(previous))
        pico2d.SDL_SetRenderDrawBlendMode(renderer, pico2d.SDL_BLENDMODE_ADD)
        try:
            pico2d.draw_circle(x, y, radius * 2, 39, 138, 114, 94, filled=True)
            pico2d.draw_circle(x, y, radius, 105, 221, 167, 170, filled=True)
            pico2d.draw_circle(x, y, max(1, radius // 2), 233, 255, 211, 225, filled=True)
        finally:
            pico2d.SDL_SetRenderDrawBlendMode(renderer, previous.value)
