"""발사 방향과 위력을 고정하고 시작점만 플레이어를 따라가는 광선."""

from geometry import box_points, circle_intersects_polygon, draw_polygon, intersects, oriented_box, ray_length


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

    def polygon(self):
        owner = self.owner
        length = ray_length(owner.x, owner.y, self.angle, owner.arena.radius)
        return oriented_box(owner.x, owner.y, self.angle, length, self.width)

    def apply_tick(self):
        polygon = self.polygon()
        hits = []
        for enemy in self.owner.targets:
            if enemy.hp > 0 and intersects(polygon, box_points(enemy.get_bb())):
                enemy.take_damage(self.damage)
                hits.append(enemy.identifier)
        self.hit_ids.append(hits)
        self.ticks += 1

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
        if self.active:
            draw_polygon(self.polygon(), self.owner.camera, (115, 213, 255))
