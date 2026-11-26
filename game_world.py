"""LEC14 방식의 레이어별 객체 관리: 배경, 캐릭터, 표시 객체."""

world = [[], [], []]


def add_object(obj, depth=1):
    world[depth].append(obj)


def remove_object(obj):
    for layer in world:
        if obj in layer:
            layer.remove(obj)
            return
    raise ValueError('월드에 없는 객체입니다.')


def update(stop=None):
    for layer in world:
        for obj in layer[:]:
            if stop is not None and stop():
                return
            obj.update()


def render(before_actors=None):
    for obj in world[0][:]:
        obj.draw()
    if before_actors is not None:
        before_actors()
    # World y grows north. Draw the actors behind others first, using the foot anchor.
    for obj in sorted(world[1], key=lambda item: getattr(item, 'y', 0.0)
                      - getattr(item, 'height', 0.0) / 2, reverse=True):
        obj.draw()
    for obj in world[2][:]:
        obj.draw()


def clear():
    for layer in world:
        layer.clear()
