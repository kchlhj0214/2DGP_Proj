"""도형 전투 상태, 체력, 에너지와 조작 안내."""

from math import ceil
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
        pico2d.draw_rectangle(12, top - 143, 360, top + 20, 13, 20, 29, filled=True)
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
        selections = {'all': '혼합', 'melee': '근접만', 'ranged': '원거리만'}
        single = {'none': '적 없음', 'melee': '근접 1마리', 'ranged': '원거리 1마리'}
        status = (f'Q 테스트  |  {single[mode.waves.single_mode]}' if mode.waves.single_mode is not None
                  else f'WAVE {mode.waves.number}  |  {selections[mode.waves.selection]}  |  대기 {mode.waves.pending}')
        self.font.draw(24, top - 123, status, (218, 228, 248))
        if mode.waves.remaining_s is not None:
            minutes, seconds = divmod(ceil(mode.waves.remaining_s), 60)
            color = (255, 164, 143) if minutes == 0 else (244, 220, 164)
            self.font.draw(281, top - 123, f'{minutes:02d}:{seconds:02d}', color)
        self.font.draw(22, 47, 'WASD 이동 | 우클릭 패링/방어 | 좌클릭 광선 | R 재시작 | ESC 일시정지', (205, 218, 228))
        self.font.draw(22, 23, '1~4 웨이브 | 8 근접만 | 9 원거리만 | 0 혼합 | Q 적 없음/근접 1/원거리 1', (237, 208, 146))
        x, y = camera.width_px / 2, camera.height_px / 2
        boss = mode.waves.boss
        if boss and boss.hp > 0:
            bar_left, bar_right = x - 155, x + 155
            pico2d.draw_rectangle(bar_left, 76, bar_right, 107, 27, 23, 30, filled=True)
            self.font.draw(x - 58, 97, '언데드 오크', (255, 205, 163))
            pico2d.draw_rectangle(bar_left + 5, 80, bar_right - 5, 88, 81, 32, 37, filled=True)
            pico2d.draw_rectangle(bar_left + 5, 80, bar_left + 5 + 300 * boss.hp / boss.data['hp'],
                                  88, 204, 68, 67, filled=True)
        if combat.time < combat.message_until:
            self.font.draw(x - 35, y + 58, combat.message, (248, 228, 142))
        if mode.paused:
            return
        if combat.hp <= 0:
            self.font.draw(x - 98, y + 96, '쓰러졌습니다 · R로 재시작', (255, 172, 163))
        elif mode.waves.won:
            self.font.draw(x - 103, y + 96, '보스 처치 · R로 재시작', (224, 246, 157))
        elif mode.waves.single_mode is not None and remaining == 0:
            self.font.draw(x - 118, y + 96, 'Q로 단일 적 테스트 모드 전환', (171, 247, 195))
        elif mode.waves.boss_pending:
            self.font.draw(x - 66, y + 96, '보스 등장', (255, 153, 144))
