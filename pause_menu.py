"""Menu overlay shown on top of the frozen battle."""

import pico2d

from menu_ui import Choice, GOLD, MUTED, MenuInput, MenuUI


PAUSE_ITEMS = (
    Choice('continue', '이어 하기', (430, 456, 850, 509)),
    Choice('restart', '다시 시작', (430, 389, 850, 442)),
    Choice('volume', '전체 음량', (430, 299, 850, 375)),
    Choice('menu', '메인 메뉴로 이동', (430, 232, 850, 285)),
)
CONFIRM_ITEMS = (
    Choice('confirm', '확인', (440, 270, 628, 321)),
    Choice('cancel', '취소', (652, 270, 840, 321)),
)


class PauseMenu:
    def __init__(self):
        self.ui = MenuUI()
        self.input = MenuInput()
        self.confirm = None

    def open(self):
        self.input.reset()
        self.confirm = None

    def handle(self, event):
        if self.confirm and event.type == pico2d.SDL_KEYDOWN:
            if event.key in (pico2d.SDLK_LEFT, pico2d.SDLK_RIGHT):
                self.input.selected = int(event.key == pico2d.SDLK_RIGHT)
                return None
        action = self.input.handle(event, self.ui, self.items())
        if self.confirm:
            if action == 'confirm':
                return self.confirm
            if action in ('cancel', 'back'):
                selected = next(i for i, item in enumerate(PAUSE_ITEMS) if item.action == self.confirm)
                self.confirm = None
                self.input.reset(selected)
        elif action in ('menu', 'restart'):
            self.confirm = action
            self.input.reset(1)
        elif action in ('back', 'continue'):
            return 'continue'
        return None

    def items(self):
        return CONFIRM_ITEMS if self.confirm else PAUSE_ITEMS

    def draw(self):
        ui = self.ui
        ui.dim(157)
        if self.confirm:
            ui.panel((400, 223, 880, 496))
            question = '메인 메뉴로 돌아갈까요?' if self.confirm == 'menu' else '다시 시작할까요?'
            ui.text(640, 425, question, 30, align='center')
            ui.text(640, 370, '이번 전투 진행 상황이 사라집니다.', 19, MUTED, 'center')
        else:
            ui.panel((390, 158, 890, 615))
            ui.text(640, 557, '일시정지', 44, align='center')
            ui.text(640, 192, 'ESC 이어 하기', 17, GOLD, 'center')
        ui.choices(self.items(), self.input.selected)
