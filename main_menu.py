"""Title screen and the lobby's help, achievement and sound pages."""

from pathlib import Path

import pico2d

import game_framework
from menu_ui import Choice, GOLD, HEIGHT, INK, LINE, MUTED, WIDTH, MenuInput, MenuUI


TITLE_ART = Path(__file__).resolve().parent / 'assets/menu/title-art.png'
HOME = tuple(Choice(action, label, (72, 366 - i * 57, 353, 413 - i * 57))
             for i, (action, label) in enumerate((('start', '게임 시작'), ('controls', '조작법'),
                                                 ('achievements', '업적'), ('sound', '사운드 설정'),
                                                 ('quit', '종료'))))
BACK = Choice('back', '돌아가기', (374, 112, 554, 160))
SOUND = (Choice('volume', '전체 음량', (374, 330, 906, 410)), BACK)
ACHIEVEMENTS = (
    ('빈틈없는 방패', '패링 행동을 7회 연속 성공합니다.'),
    ('절제된 반격', '4단계 광선을 한 번도 발사하지 않고 클리어합니다.'),
    ('한 번에 받아내기', '한 번의 패링으로 서로 다른 공격 3개 이상을 받아냅니다.'),
    ('완벽한 생존', '체력이 한 번도 감소하지 않고 클리어합니다.'),
)
CONTROLS = (
    ('WASD', '이동'),
    ('마우스 이동', '바라보는 방향과 방패 조준'),
    ('우클릭 · 유지', '패링 시도 · 이후 방패로 방어'),
    ('좌클릭', '모아 둔 에너지로 광선 발사'),
    ('ESC', '전투 일시정지'),
)
HEADINGS = {'achievements': '업적', 'controls': '조작법', 'sound': '사운드 설정'}


class MainMenu:
    def init(self):
        self.ui = MenuUI()
        self.art = pico2d.load_image(str(TITLE_ART))
        self.active_page = 'home'
        self.input = MenuInput()
        self.home_selection = 0

    def items(self):
        if self.active_page == 'home':
            return HOME
        return SOUND if self.active_page == 'sound' else (BACK,)

    def handle_events(self):
        events = pico2d.get_events()
        if any(event.type == pico2d.SDL_QUIT for event in events):
            game_framework.quit()
            return
        for event in events:
            action = self.input.handle(event, self.ui, self.items())
            if action == 'start':
                import play_mode
                game_framework.change_mode(play_mode)
                return
            if action == 'quit':
                game_framework.quit()
                return
            if action == 'back' and self.active_page != 'home':
                self.active_page = 'home'
                self.input.reset(self.home_selection)
                return
            if action in HEADINGS:
                self.home_selection = self.input.selected
                self.active_page = action
                self.input.reset()
                return

    def update(self):
        pass

    def render(self):
        ui = self.ui
        pico2d.clear_canvas()
        pico2d.draw_rectangle(0, 0, ui.width, ui.height, 12, 13, 20, filled=True)
        self.art.draw(ui.width / 2, ui.height / 2, WIDTH * ui.scale, HEIGHT * ui.scale)
        if self.active_page == 'home':
            ui.rectangle((72, 641, 157, 644), GOLD)
            ui.text(69, 577, '참는 데도', 64)
            ui.text(70, 511, '용량이 있습니다', 50)
            ui.text(72, 62, '방향키 이동   Enter 선택', 17, MUTED)
        else:
            self.draw_page()
        ui.choices(self.items(), self.input.selected)
        pico2d.update_canvas()

    def draw_page(self):
        ui = self.ui
        ui.dim(145)
        ui.panel((338, 87, 942, 632))
        ui.text(374, 572, HEADINGS[self.active_page], 39)
        if self.active_page == 'achievements':
            ui.text(374, 531, '달성 기록 기능은 준비 중입니다.', 17, MUTED)
            for index, (name, requirement) in enumerate(ACHIEVEMENTS):
                y = 483 - index * 76
                ui.rectangle((374, y + 23, 906, y + 23), LINE)
                ui.text(374, y, name, 22, GOLD)
                ui.text(906, y, '미달성', 16, MUTED, 'right')
                ui.text(374, y - 28, requirement, 17, INK)
        elif self.active_page == 'controls':
            for index, (key, meaning) in enumerate(CONTROLS):
                y = 498 - index * 65
                ui.rectangle((374, y + 25, 906, y + 25), LINE)
                ui.text(374, y, key, 20, GOLD)
                ui.text(570, y, meaning, 18)
        else:
            ui.text(374, 297, '슬라이더 또는 좌우 방향키로 조절합니다.', 17, MUTED)

    def finish(self):
        self.art = None
        self.ui.close()


MAIN_MENU = MainMenu()
