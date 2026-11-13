"""LEC15의 모드 수명주기와 LEC16의 초 단위 frame_time."""

from time import perf_counter, sleep

running = False
stack = []
frame_time = 0.0


def quit():
    global running
    running = False


def change_mode(mode):
    if stack:
        stack.pop().finish()
    stack.append(mode)
    mode.init()


def push_mode(mode):
    if stack:
        stack[-1].pause()
    stack.append(mode)
    mode.init()


def pop_mode():
    if stack:
        stack.pop().finish()
    if stack:
        stack[-1].resume()
    else:
        quit()


def run(start_mode):
    global running, frame_time
    running = True
    stack.clear()
    try:
        change_mode(start_mode)
        previous = perf_counter()
        while running:
            now = perf_counter()
            frame_time = now - previous
            previous = now
            stack[-1].handle_events()
            if not running:
                break
            stack[-1].update()
            stack[-1].render()
            # CPU 사용을 줄일 뿐, 이동량은 이 값이 아닌 실제 frame_time으로 계산.
            sleep(0.001)
    finally:
        while stack:
            stack.pop().finish()
        running = False
