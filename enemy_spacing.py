"""적 몸체끼리의 연속 충돌과 입구의 빈 출현 위치 탐색. 단위는 m."""

from math import atan2, ceil, cos, hypot, pi, sin

from wave_data import SETTINGS

EPSILON = 1e-7
GAP = SETTINGS['main']['enemy_gap_m']


def overlaps(enemy, x, y, other):
    return (other is not enemy and other.hp > 0
            and abs(x - other.x) < (enemy.width + other.width) / 2 + GAP - EPSILON
            and abs(y - other.y) < (enemy.height + other.height) / 2 + GAP - EPSILON)


def is_free(enemy, x, y):
    return not any(overlaps(enemy, x, y, other) for other in enemy.player.targets)


def sweep_contact(enemy, dx, dy):
    """이동 선분을 확장된 적 몸체와 검사해 큰 시간 간격에도 관통을 막는다."""
    fraction, blocker = 1.0, None
    for other in enemy.player.targets:
        if other is enemy or other.hp <= 0:
            continue
        enter, leave = -float('inf'), float('inf')
        for position, delta, center, half in (
                (enemy.x, dx, other.x, (enemy.width + other.width) / 2),
                (enemy.y, dy, other.y, (enemy.height + other.height) / 2)):
            low, high = center - half - GAP, center + half + GAP
            if abs(delta) < EPSILON:
                if not low + EPSILON < position < high - EPSILON:
                    enter, leave = 1.0, -1.0
                    break
            else:
                first, last = sorted(((low - position) / delta, (high - position) / delta))
                enter, leave = max(enter, first), min(leave, last)
        if enter < leave and 0 <= enter < fraction and leave > EPSILON:
            fraction, blocker = enter, other
    if blocker is not None:
        fraction = max(0.0, fraction - EPSILON / max(hypot(dx, dy), EPSILON))
    return fraction, blocker


def safe_step(enemy, dx, dy):
    x, y = enemy.constrain_position(enemy.x + dx, enemy.y + dy)
    dx, dy = x - enemy.x, y - enemy.y
    fraction, _ = sweep_contact(enemy, dx, dy)
    x, y = enemy.x + dx * fraction, enemy.y + dy * fraction
    if not is_free(enemy, x, y):
        return 0.0
    distance = hypot(x - enemy.x, y - enemy.y)
    enemy.x, enemy.y = x, y
    return distance


def move_enemy(enemy, dx, dy, *, priority=False):
    """길이 막히면 옆으로 돌아서며 공격 중인 다른 적도 통과하지 않는다."""
    distance = hypot(dx, dy)
    if distance <= EPSILON:
        return
    moved = safe_step(enemy, dx, dy)
    remaining = distance - moved
    if remaining <= EPSILON:
        return
    # ID에 고정된 방향을 사용해 군집에서 매 프레임 좌우로 흔들리지 않게 한다.
    sign = 1 if sum(map(ord, str(enemy.identifier))) % 2 else -1
    ux, uy = dx / distance, dy / distance
    if priority:
        _, blocker = sweep_contact(enemy, ux * remaining, uy * remaining)
        if blocker is not None and blocker.yields_space and blocker.recoil_age is None:
            side_offset = (blocker.x - enemy.x) * -uy + (blocker.y - enemy.y) * ux
            side = sign if abs(side_offset) < EPSILON else (1 if side_offset > 0 else -1)
            for direction in (side, -side):
                if safe_step(blocker, -uy * remaining * direction, ux * remaining * direction) > EPSILON:
                    remaining -= safe_step(enemy, ux * remaining, uy * remaining)
                    if remaining <= EPSILON:
                        return
                    sign = -direction
                    break
    for side in (sign, -sign):
        if safe_step(enemy, -uy * remaining * side, ux * remaining * side) > EPSILON:
            return


def spawn_position(enemy, x, y):
    """입구가 막혀도 출현을 지연하지 않고 같은 입구 주변 원둘레의 빈 자리에 배치."""
    radius = enemy.player.arena.radius
    angle = atan2(y, x)
    angular_step = (max(enemy.width, enemy.height) + GAP + EPSILON * 4) / radius
    count = ceil(2 * pi / angular_step)
    for index in range(count * 2 + 1):
        offset = (index + 1) // 2 * (1 if index % 2 else -1)
        theta = angle + offset * angular_step
        px, py = enemy.player.constrain_position(radius * cos(theta), radius * sin(theta))
        if is_free(enemy, px, py):
            return px, py
    raise RuntimeError('경기장 가장자리에 적의 출현 공간이 없습니다.')
