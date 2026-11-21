"""Compose actual Blender renders into review boards; no model or game edits."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'art/model-review-v1'
DATA = json.loads((ROOT / 'data/art_models.json').read_text(encoding='utf-8'))
FONT = 'C:/Windows/Fonts/malgun.ttf'
BG = (24, 28, 33)
PANEL = (33, 38, 44)
INK = (236, 228, 213)
MUTED = (170, 180, 185)
NAMES = {'hero': '주인공 · 유물 방패', 'melee': '근접형 · 해골 검사', 'ranged': '원거리형 · 해골 마법사'}
DIRECTIONS = ['정면', '정면 대각', '측면', '후면 대각', '후면', '반대 후면 대각', '반대 측면', '반대 정면 대각']


def font(size):
    return ImageFont.truetype(FONT, size)


def put_image(board, path, box):
    source = Image.open(path).convert('RGBA')
    source.thumbnail((box[2]-box[0], box[3]-box[1]), Image.Resampling.LANCZOS)
    x = box[0] + (box[2]-box[0]-source.width)//2
    y = box[1] + (box[3]-box[1]-source.height)//2
    board.paste(source, (x, y), source)


def lineup():
    board = Image.new('RGB', (1500, 820), BG)
    d = ImageDraw.Draw(board)
    d.text((40, 24), 'SHIELD ATTACK · 3D 모델 검토', font=font(34), fill=INK)
    d.text((40, 79), '기존 컨셉 기반 · 동일한 세계 단위 · 게임 적용 전 외형 확인', font=font(19), fill=MUTED)
    for i, name in enumerate(NAMES):
        x = 20 + i*495
        d.rounded_rectangle((x, 125, x+480, 785), radius=14, fill=PANEL)
        put_image(board, FOLDER/(name+'-three-quarter.png'), (x, 120, x+480, 735))
        d.text((x+34, 742), NAMES[name], font=font(25), fill=INK)
    board.save(FOLDER/'model-lineup.png')


def turnaround(name):
    cell, top = 400, 125
    board = Image.new('RGB', (1600, 1045), BG)
    d = ImageDraw.Draw(board)
    d.text((32, 22), NAMES[name]+' · 8방향', font=font(32), fill=INK)
    d.text((32, 75), '한 개의 실제 3D 모델을 회전 촬영 · 좌우 반전 사용 안 함 · 발 위치와 카메라 고정', font=font(19), fill=MUTED)
    for i, row in enumerate(DATA['views']):
        x, y = (i%4)*cell, top+(i//4)*450
        d.rounded_rectangle((x+8,y,x+cell-8,y+438),radius=10,fill=PANEL)
        put_image(board,FOLDER/(name+'-'+row['id']+'.png'),(x,y,x+cell,y+400))
        d.text((x+24,y+397), DIRECTIONS[i], font=font(22), fill=INK)
    board.save(FOLDER/(name+'-turnaround.png'))


def validate_images():
    report = []
    for name in NAMES:
        for view in DATA['views']:
            for prefix in ('', 'game-'):
                path = FOLDER/(name+'-'+prefix+view['id']+'.png')
                im = Image.open(path).convert('RGBA')
                bbox = im.getchannel('A').getbbox()
                assert bbox, str(path)
                assert bbox[0]>1 and bbox[1]>1 and bbox[2]<im.width-1 and bbox[3]<im.height-1, str(path)
                report.append({'file':path.name,'size':im.size,'visible_bounds':bbox})
    (FOLDER/'image-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f'Validated {len(report)} rendered views: visible, transparent, not clipped.')


if __name__ == '__main__':
    validate_images()
    lineup()
    for name in NAMES: turnaround(name)
