"""적 몸체끼리의 연속 충돌과 입구의 빈 출현 위치 탐색. 단위는 m."""

from math import atan2, ceil, cos, hypot, pi, sin

EPSILON = 1e-7


def overlaps(enemy, x, y, other):
    return (other is not enemy and other.hp > 0
            and abs(x - other.x) < (enemy.width + other.width) / 2 - EPSILON
            and abs(y - other.y) < (enemy.height + other.height) / 2 - EPSILON)


def is_free(enemy, x, y):
    return not any(overlaps(enemy, x, y, other) for other in enemy.player.targets)


def sweep_fraction(enemy, dx, dy):
    """이동 선분을 확장된 적 몸체와 검사해 큰 시간 간격에도 관통을 막는다."""
    fraction = 1.0
    for other in enemy.player.targets:
        if other is enemy or other.hp <= 0:
            continue
        enter, leave = -float('inf'), float('inf')
        for position, delta, center, half in (
                (enemy.x, dx, other.x, (enemy.width + other.width) / 2),
                (enemy.y, dy, other.y, (enemy.height + other.height) / 2)):
            low, high = center - half, center + half
            if abs(delta) < EPSILON:
                if not low + EPSILON < position < high - EPSILON:
                    enter, leave = 1.0, -1.0
                    break
            else:
                first, last = sorted(((low - position) / delta, (high - position) / delta))
                enter, leave = max(enter, first), min(leave, last)
        if enter < leave and 0 <= enter < fraction and leave > EPSILON:
            fraction = max(0.0, enter - EPSILON / max(hypot(dx, dy), EPSILON))
    return fraction


def safe_step(enemy, dx, dy):
    x, y = enemy.player.constrain_position(enemy.x + dx, enemy.y + dy)
    dx, dy = x - enemy.x, y - enemy.y
    fraction = sweep_fraction(enemy, dx, dy)
    x, y = enemy.x + dx * fraction, enemy.y + dy * fraction
    if not is_free(enemy, x, y):
        return 0.0
    distance = hypot(x - enemy.x, y - enemy.y)
    enemy.x, enemy.y = x, y
    return distance


def move_enemy(enemy, dx, dy):
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
    for side in (sign, -sign):
        if safe_step(enemy, -dy / distance * remaining * side,
                     dx / distance * remaining * side) > EPSILON:
            return


def spawn_position(enemy, x, y):
    """입구가 막혀도 출현을 지연하지 않고 같은 입구 주변 원둘레의 빈 자리에 배치."""
    radius = enemy.player.arena.radius
    angle = atan2(y, x)
    angular_step = (max(enemy.width, enemy.height) + EPSILON * 4) / radius
    count = ceil(2 * pi / angular_step)
    for index in range(count * 2 + 1):
        offset = (index + 1) // 2 * (1 if index % 2 else -1)
        theta = angle + offset * angular_step
        px, py = enemy.player.constrain_position(radius * cos(theta), radius * sin(theta))
        if is_free(enemy, px, py):
            return px, py
    raise RuntimeError('경기장 가장자리에 적의 출현 공간이 없습니다.')
