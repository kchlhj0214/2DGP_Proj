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


def update():
    for layer in world:
        for obj in layer[:]:
            obj.update()


def render():
    for layer in world:
        for obj in layer[:]:
            obj.draw()


def clear():
    for layer in world:
        layer.clear()
