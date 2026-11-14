"""데이터 시트를 검증한 뒤 게임에서 사용하는 상수를 생성한다."""

import json
from pathlib import Path
from pprint import pformat

ROOT = Path(__file__).resolve().parents[1]


def validate(data):
    schemas = {
        'viewports': {'id', 'height_m', 'window_width_px', 'window_height_px', 'desktop_fit_ratio'},
        'arenas': {'id', 'viewport_id', 'diameter_height_ratio', 'grid_m'},
        'characters': {'id', 'viewport_id', 'height_ratio',
                       'width_height_ratio', 'boundary_height_ratio', 'speed_kmph'},
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
    for row in data['viewports']:
        if row['desktop_fit_ratio'] >= 1:
            raise ValueError('창은 바탕화면보다 작게 표시해야 합니다.')
        if any(not isinstance(row[field], int) for field in ('window_width_px', 'window_height_px')):
            raise ValueError('창의 가로와 세로는 정수 픽셀이어야 합니다.')
    for row in data['arenas'] + data['characters']:
        if row['viewport_id'] not in viewports:
            raise ValueError('존재하지 않는 화면 참조')
    for row in data['characters']:
        if row['boundary_height_ratio'] > 1:
            raise ValueError('경계 판정 높이는 전체 히트박스 높이를 넘을 수 없습니다.')
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
    combat = validate_combat(json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8')), data)
    source = '# 자동 생성 파일: data/combat.json을 수정한 뒤 tools/generate_data.py 실행\n'
    for name, rows in combat.items():
        source += f'{name.upper()} = {pformat({row["id"]: row for row in rows}, sort_dicts=False)}\n\n'
    (ROOT / 'combat_data.py').write_text(source, encoding='utf-8')


def validate_combat(data, scale):
    from math import isfinite
    schemas = {
        'systems': {'id', 'player_hp', 'guard_kmph', 'input_lock_s', 'success_invuln_s',
                    'hit_invuln_s', 'stun_s', 'guard_angle_deg', 'energy_max',
                    'damage_multiplier', 'beam_duration_s', 'beam_tick_s', 'step_s'},
        'stages': {'id', 'energy_min', 'parry_window_s', 'beam_width_m'},
        'enemies': {'id', 'character_id', 'hp', 'speed_kmph', 'damage', 'energy_gain',
                    'stop_m', 'windup_s', 'swing_s', 'recovery_s', 'sword_length_m',
                    'sword_width_m', 'sweep_deg'},
        'spawns': {'id', 'enemy_id', 'x_m', 'y_m'},
    }
    if set(data) != set(schemas):
        raise ValueError('전투 시트 종류가 올바르지 않습니다.')
    for name, columns in schemas.items():
        if not isinstance(data[name], list) or not data[name]:
            raise ValueError(f'{name}: 비어 있는 시트')
        ids = set()
        for row in data[name]:
            if set(row) != columns:
                raise ValueError(f'{name}: 누락되거나 알 수 없는 셀')
            for field, value in row.items():
                if field == 'id' or field.endswith('_id'):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f'{name}.{field}: 빈 ID')
                elif (isinstance(value, bool) or not isinstance(value, (int, float))
                      or not isfinite(value) or (field not in ('x_m', 'y_m', 'energy_min') and value <= 0)):
                    raise ValueError(f'{name}.{field}: 잘못된 수치')
            if row['id'] in ids:
                raise ValueError(f'{name}: 중복 ID')
            ids.add(row['id'])
    systems = {r['id']: r for r in data['systems']}
    if 'main' not in systems:
        raise ValueError('기본 전투 시스템 누락')
    system = systems['main']
    stages = data['stages']
    if len(stages) != 4 or [s['energy_min'] for s in stages] != sorted(set(s['energy_min'] for s in stages)):
        raise ValueError('축적 단계 경계가 중복되거나 순서가 잘못되었습니다.')
    if stages[0]['energy_min'] != 0 or stages[-1]['energy_min'] >= system['energy_max']:
        raise ValueError('단계 경계가 에너지 범위를 벗어납니다.')
    if any(s['parry_window_s'] > system['input_lock_s'] for s in stages):
        raise ValueError('패링 구간이 입력 잠금보다 깁니다.')
    if any(a['parry_window_s'] <= b['parry_window_s'] for a, b in zip(stages, stages[1:])):
        raise ValueError('축적 단계가 높을수록 패링 구간은 짧아야 합니다.')
    if not 0 < system['guard_angle_deg'] <= 360 or system['step_s'] > 1 / 60:
        raise ValueError('방어 각도 또는 전투 갱신 간격이 잘못되었습니다.')
    if system['beam_duration_s'] <= system['beam_tick_s'] * 2:
        raise ValueError('광선 지속 시간이 세 번째 타격 전에 끝납니다.')
    characters = {r['id']: r for r in scale['characters']}
    enemies = {r['id']: r for r in data['enemies']}
    for enemy in enemies.values():
        if enemy['character_id'] not in characters:
            raise ValueError('존재하지 않는 캐릭터 참조')
        if not system['guard_kmph'] < enemy['speed_kmph'] < characters[enemy['character_id']]['speed_kmph']:
            raise ValueError('기본 방어 < 적 < 일반 이동 속도 관계가 잘못되었습니다.')
    for spawn in data['spawns']:
        if spawn['enemy_id'] not in enemies:
            raise ValueError('존재하지 않는 적 참조')
    return data


if __name__ == '__main__':
    generate()
