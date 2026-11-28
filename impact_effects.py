"""Hit feedback advances on presentation time, even while gameplay is stopped."""

from dataclasses import dataclass
from math import cos, sin, tau
from pathlib import Path

import pico2d

from presentation_data import VISUALS


@dataclass
class DamageNumber:
    x: float
    y: float
    amount: float
    born: float
    player_hit: bool


class ImpactEffects:
    def __init__(self, camera, load_media=False):
        self.camera = camera
        self.config = VISUALS['impact']
        self.time = self.stop_until = self.shake_start = self.shake_m = 0.0
        self.flashes = {}
        self.player_flash_at = None
        self.numbers = []
        self.font = self.sound = None
        if load_media:
            font = Path(pico2d.__file__).parent / 'data' / 'ConsolaMalgun.ttf'
            self.font = pico2d.load_font(str(font), max(15, round(camera.height_px * .027)))
            try:
                self.sound = pico2d.load_wav(str(Path(__file__).resolve().parent / self.config['sound']))
            except IOError:
                pass  # The visual cues also work with no audio device.
            if self.sound:
                self.sound.set_volume(self.config['volume'])

    @property
    def stopped_for(self):
        return max(0.0, self.stop_until - self.time)

    def damage(self, owner, amount, player_hit=False):
        if amount <= 0:
            return
        self.stop_until = max(self.stop_until, self.time + self.config['hitstop_s'])
        if player_hit:
            self.player_flash_at = self.time
        else:
            self.flashes[owner] = self.time + self.config['flash_s']
        self.numbers.append(DamageNumber(owner.x, owner.y + owner.height * .65,
                                         amount, self.time, player_hit))

    def flashing(self, owner):
        return self.time < self.flashes.get(owner, 0.0)

    def player_flash_color(self):
        if self.player_flash_at is None:
            return None
        age = self.time - self.player_flash_at
        phase = int(age / self.config['player_flash_phase_s'])
        colors = ('red', 'white', 'red')
        return colors[phase] if phase < len(colors) else None

    def beam(self, strongest):
        self.shake_start = self.time
        self.shake_m = self.config['max_shake_m' if strongest else 'shake_m']

    def beam_pulse(self):
        if self.sound:
            self.sound.play()

    def update(self, seconds):
        self.time += seconds
        self.flashes = {owner: until for owner, until in self.flashes.items() if until > self.time}
        self.numbers = [number for number in self.numbers
                        if self.time - number.born < self.config['number_s']]
        age = self.time - self.shake_start
        fade = max(0.0, 1 - age / self.config['shake_s'])
        strength = self.shake_m * self.camera.pixels_per_meter * fade * fade
        self.camera.shake_x = strength * sin(tau * 20 * age)
        self.camera.shake_y = strength * .65 * cos(tau * 25 * age)

    def draw(self):
        if not self.font:
            return
        for number in self.numbers:
            progress = (self.time - number.born) / self.config['number_s']
            rise = (1 - (1 - progress)**2) * self.config['rise_m']
            x, y = self.camera.to_screen(number.x, number.y + rise)
            text = format(number.amount, 'g')
            x -= 5 * len(text)
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                self.font.draw(x + dx, y + dy, text, (40, 22, 22))
            color = (255, 155, 120) if number.player_hit else (255, 237, 171)
            self.font.draw(x, y, text, color)
