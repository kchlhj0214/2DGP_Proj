"""데이터 시트를 검증한 뒤 게임에서 사용하는 상수를 생성한다."""

import json
from pathlib import Path
from pprint import pformat

ROOT = Path(__file__).resolve().parents[1]


def validate(data):
    schemas = {
        'viewports': {'id', 'height_m'},
        'arenas': {'id', 'viewport_id', 'diameter_height_ratio', 'grid_m'},
        'characters': {'id', 'viewport_id', 'height_ratio',
                       'width_height_ratio', 'speed_kmph'},
    }
    if set(data) != set(schemas):
        raise ValueError('시트 종류가 올바르지 않습니다.')
    for name, columns in schemas.items():
        rows = data[name]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'{name}: 비어 있는 시트')
        ids = set()
        for row in rows:
            if set(row) != columns or any(v is None or v == '' for v in row.values()):
                raise ValueError(f'{name}: 누락되거나 알 수 없는 셀')
            if not isinstance(row['id'], str) or row['id'] in ids:
                raise ValueError(f'{name}: 중복되거나 잘못된 ID')
            ids.add(row['id'])
            for key, value in row.items():
                if key.endswith('_id') or key == 'id':
                    continue
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < float('inf'):
                    raise ValueError(f'{name}.{key}: 양의 유한 수가 필요합니다.')
    viewports = {row['id'] for row in data['viewports']}
    for row in data['arenas'] + data['characters']:
        if row['viewport_id'] not in viewports:
            raise ValueError('존재하지 않는 화면 참조')
    required = {'viewports': 'main', 'arenas': 'arena', 'characters': 'player'}
    for name, identifier in required.items():
        if identifier not in {row['id'] for row in data[name]}:
            raise ValueError(f'{name}: 시작 객체 {identifier} 누락')
    return data


def generate():
    data = validate(json.loads((ROOT / 'data/scale.json').read_text(encoding='utf-8')))
    source = '# 자동 생성 파일: data/scale.json을 수정한 뒤 tools/generate_data.py 실행\n'
    for name, rows in data.items():
        source += f'{name.upper()} = {pformat({row["id"]: row for row in rows}, sort_dicts=False)}\n\n'
    (ROOT / 'game_data.py').write_text(source, encoding='utf-8')


if __name__ == '__main__':
    generate()
