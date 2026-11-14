"""도형 전투 상태, 체력, 에너지와 조작 안내."""

from pathlib import Path

import pico2d
from combat_data import STAGES


class CombatHUD:
    def __init__(self, mode):
        self.mode = mode
        font_path = Path(pico2d.__file__).parent / 'data' / 'ConsolaMalgun.ttf'
        self.font = pico2d.load_font(str(font_path), 17)

    def update(self):
        pass

    def draw(self):
        mode = self.mode
        combat, camera = mode.player.combat, mode.camera
        top = camera.height_px - 32
        pico2d.draw_rectangle(12, top - 112, 340, top + 20, 13, 20, 29, filled=True)
        self.font.draw(24, top, f'HP {combat.hp:g} / {combat.settings["player_hp"]:g}', (225, 243, 242))
        pico2d.draw_rectangle(24, top - 20, 310, top - 10, 66, 40, 49, filled=True)
        pico2d.draw_rectangle(24, top - 20, 24 + 286 * combat.hp / combat.settings['player_hp'],
                              top - 10, 93, 211, 158, filled=True)
        stage = list(STAGES).index(combat.stage()['id']) + 1
        self.font.draw(24, top - 42, f'ENERGY {combat.energy:g} / {combat.settings["energy_max"]:g}   {stage} / 4', (140, 221, 255))
        for index in range(4):
            x = 24 + index * 73
            pico2d.draw_rectangle(x, top - 66, x + 67, top - 55, 37, 62, 80, filled=True)
            segment = combat.settings['energy_max'] / 4
            ratio = max(0, min(1, (combat.energy - index * segment) / segment))
            if ratio:
                pico2d.draw_rectangle(x, top - 66, x + 67 * ratio, top - 55, 85, 190, 240, filled=True)
        states = {'free': '이동', 'raising': '방패 들기', 'guard': '기본 방어', 'beam': '광선', 'dead': '사망'}
        remaining = sum(enemy.hp > 0 for enemy in mode.enemies)
        self.font.draw(24, top - 94, f'{states[combat.state]}  |  남은 적 {remaining}', (225, 234, 244))
        self.font.draw(22, 24, 'WASD 이동  |  우클릭 패링 / 유지 방어  |  좌클릭 광선  |  R 재시작  |  ESC 일시정지', (205, 218, 228))
        x, y = camera.width_px / 2, camera.height_px / 2
        if combat.time < combat.message_until:
            self.font.draw(x - 35, y + 58, combat.message, (248, 228, 142))
        if mode.paused:
            self.font.draw(x - 100, y + 96, '일시정지 · ESC로 계속', (245, 236, 201))
        elif combat.hp <= 0:
            self.font.draw(x - 98, y + 96, '쓰러졌습니다 · R로 재시작', (255, 172, 163))
        elif remaining == 0:
            self.font.draw(x - 100, y + 96, '훈련 완료 · R로 다시 시작', (171, 247, 195))
