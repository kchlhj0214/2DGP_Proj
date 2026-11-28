"""Shared cell layout for the game and sprite authoring tools."""


def cell_size(clip, default):
    width = clip.get('cell_px', default)
    return width, clip.get('cell_height_px', width)


def cell_slot(clip, facing, index):
    return divmod(facing * clip['frames'] + index, clip.get('columns', clip['frames']))


def sheet_size(clip, default, directions):
    width, height = cell_size(clip, default)
    columns = clip.get('columns', clip['frames'])
    last_row, _ = cell_slot(clip, directions - 1, clip['frames'] - 1)
    return width * columns, height * (last_row + 1)
