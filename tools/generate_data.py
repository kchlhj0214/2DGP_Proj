"""데이터 시트를 검증한 뒤 게임에서 사용하는 상수를 생성한다."""

import json
from math import isfinite
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
    combat = validate_combat(json.loads((ROOT / 'data/combat.json').read_text(encoding='utf-8')), data)
    waves = validate_waves(json.loads((ROOT / 'data/waves.json').read_text(encoding='utf-8')), data, combat)
    presentation = validate_presentation(json.loads((ROOT / 'data/presentation.json').read_text(encoding='utf-8')))
    # 모든 시트 검증이 성공한 뒤에만 코드를 생성한다.
    for sheet, output, content in (('scale', 'game_data.py', data),
                                   ('combat', 'combat_data.py', combat),
                                   ('waves', 'wave_data.py', waves),
                                   ('presentation', 'presentation_data.py', presentation)):
        source = f'# 자동 생성 파일: data/{sheet}.json을 수정한 뒤 tools/generate_data.py 실행\n'
        for name, rows in content.items():
            source += f'{name.upper()} = {pformat({row["id"]: row for row in rows}, sort_dicts=False)}\n\n'
        (ROOT / output).write_text(source, encoding='utf-8')


def validate_presentation(data):
    schemas = {
        'arena': {'art', 'water', 'ring_radius_px', 'wall_base_px', 'bank_drop_px', 'bridge_width_m'},
        'sprites': {'atlas', 'asset_dir', 'body_height_px'},
        'impact': {'sound', 'volume', 'hitstop_s', 'flash_s', 'number_s', 'rise_m',
                   'shake_s', 'shake_m', 'max_shake_m'},
        'parry': {'push_height_ratio', 'push_s', 'raise_s', 'success_lift_s'},
        'beam': {'taper_width_ratio'},
    }
    paths = {'art', 'water', 'atlas', 'asset_dir', 'sound'}
    rows = data.get('visuals', [])
    if len(rows) != len(schemas) or {row.get('id') for row in rows} != set(schemas):
        raise ValueError('화면 연출 시트 누락')
    for row in rows:
        if set(row) != schemas[row['id']] | {'id'}:
            raise ValueError(f'{row["id"]}: 누락되거나 알 수 없는 셀')
        for field, value in row.items():
            if field == 'wall_base_px':
                if (not isinstance(value, list) or len(value) != 64
                        or any(type(v) is not int or v <= row['ring_radius_px'] + row['bank_drop_px'] for v in value)):
                    raise ValueError('물길의 석벽 경계가 경기장 안쪽입니다.')
                continue
            if field in paths and (not isinstance(value, str) or not value or not (ROOT / value).exists()):
                raise ValueError(f'{field}: 없는 리소스')
            if field not in paths | {'id'} and (type(value) not in (int, float) or not isfinite(value) or value <= 0):
                raise ValueError(f'{field}: 양의 유한 수가 필요합니다')
    assets = next(row for row in rows if row['id'] == 'sprites')
    atlas = json.loads((ROOT / assets['atlas']).read_text(encoding='utf-8'))
    expected = {'hero': {'idle','guard_walk','guard','run','parry'},
                'melee': {'idle','walk','chop','deflected','collapse'},
                'ranged': {'idle','walk','cast','ash'}}
    if atlas['directions'] != ['S','SE','E','NE','N','NW','W','SW'] or atlas['fps'] <= 0:
        raise ValueError('스프라이트 방향 또는 속도 오류')
    for clip in atlas['clips']:
        actor, action = clip['actor'], clip['action']
        if action not in expected.get(actor,set()) or type(clip['frames']) is not int or clip['frames'] < 1:
            raise ValueError(f'잘못된 스프라이트 참조: {actor}/{action}')
        expected[actor].remove(action)
        if actor == 'hero' and action in ('guard','guard_walk'):
            anchors = clip.get('shield_px', [])
            if (len(anchors) != 8 or any(len(row) != clip['frames'] for row in anchors)
                    or any(len(point) != 2 or any(type(axis) is not int or not 0 <= axis < atlas['cell_px']
                                                  for axis in point)
                           for row in anchors for point in row)):
                raise ValueError(f'방패 발사점 누락: {action}')
        source = (ROOT / assets['atlas']).parent / clip['file']
        if not source.is_file() or not (ROOT / assets['asset_dir'] / f'{actor}-{action}-flash.png').is_file():
            raise ValueError(f'스프라이트 파일 누락: {actor}/{action}')
    if any(expected.values()):
        raise ValueError('필수 캐릭터 동작 누락')
    impact = next(row for row in rows if row['id'] == 'impact')
    if not impact['hitstop_s'] < impact['flash_s'] < impact['number_s'] or impact['volume'] > 128:
        raise ValueError('피격 연출 길이 또는 음량 오류')
    if impact['max_shake_m'] <= impact['shake_m']:
        raise ValueError('최대 광선의 흔들림이 기본보다 작습니다')
    beam = next(row for row in rows if row['id'] == 'beam')
    if beam['taper_width_ratio'] >= .5:
        raise ValueError('광선 시작부는 끝이 둔각이어야 합니다.')
    return data


def validate_waves(data, scale, combat):
    from math import isfinite
    schemas = {
        'settings': {'id', 'spawn_interval_s'},
        'waves': {'id', 'number', 'melee_id', 'ranged_id', 'melee_per_gate', 'ranged_per_gate'},
        'modes': {'id', 'key'},
        'single_modes': {'id', 'enemy_id', 'count'},
        'gates': {'id', 'x_ratio', 'y_ratio'},
        'ranged': {'id', 'character_id', 'hp', 'speed_kmph', 'range_m', 'attack_interval_s',
                   'projectile_speed_mps', 'projectile_radius_m', 'damage', 'energy_gain'},
    }
    if set(data) != set(schemas):
        raise ValueError('웨이브 시트 종류가 올바르지 않습니다.')
    for name, fields in schemas.items():
        rows = data[name]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f'{name}: 비어 있는 시트')
        ids = set()
        for row in rows:
            if set(row) != fields:
                raise ValueError(f'{name}: 누락되거나 알 수 없는 셀')
            for field, value in row.items():
                if field == 'id' or field.endswith('_id'):
                    if not isinstance(value, str) or not value:
                        raise ValueError(f'{name}.{field}: 빈 ID')
                elif isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                    raise ValueError(f'{name}.{field}: 유한 수가 필요합니다.')
                elif field not in ('key', 'count', 'melee_per_gate', 'ranged_per_gate', 'x_ratio', 'y_ratio') and value <= 0:
                    raise ValueError(f'{name}.{field}: 양수가 필요합니다.')
            if row['id'] in ids:
                raise ValueError(f'{name}: 중복 ID')
            ids.add(row['id'])
    if {row['id'] for row in data['settings']} != {'main'}:
        raise ValueError('출현 설정 누락')
    if {row['number'] for row in data['waves']} != {1, 2, 3, 4} or len(data['waves']) != 4:
        raise ValueError('1~4 웨이브가 필요합니다.')
    if {row['id']: row['key'] for row in data['modes']} != {'all': 0, 'melee': 8, 'ranged': 9}:
        raise ValueError('디버그 모드 키 설정이 잘못되었습니다.')
    if {row['id']: (row['x_ratio'], row['y_ratio']) for row in data['gates']} != {
            'north': (0, 1), 'south': (0, -1), 'west': (-1, 0), 'east': (1, 0)}:
        raise ValueError('상하좌우 입구가 필요합니다.')
    melee_ids = {row['id'] for row in combat['enemies']}
    ranged_ids = {row['id'] for row in data['ranged']}
    if [row['id'] for row in data['single_modes']] != ['none', 'melee', 'ranged']:
        raise ValueError('Q 디버그 모드 순서는 적 없음/근접/원거리여야 합니다.')
    for row in data['single_modes']:
        if row['enemy_id'] not in melee_ids | ranged_ids:
            raise ValueError('존재하지 않는 단일 디버그 적 참조')
        if type(row['count']) is not int or row['count'] != (0 if row['id'] == 'none' else 1):
            raise ValueError('단일 디버그 적 수는 적 없음 0, 나머지 1이어야 합니다.')
    for row in data['waves']:
        if row['melee_id'] not in melee_ids or row['ranged_id'] not in ranged_ids:
            raise ValueError('존재하지 않는 웨이브 적 참조')
        for field in ('number', 'melee_per_gate', 'ranged_per_gate'):
            if type(row[field]) is not int or row[field] < 0:
                raise ValueError('웨이브 번호와 마릿수는 음수가 아닌 정수여야 합니다.')
        if row['number'] == 4 and row['melee_per_gate'] + row['ranged_per_gate'] != 0:
            raise ValueError('보스 미구현 4웨이브는 비어 있어야 합니다.')
    characters = {row['id']: row for row in scale['characters']}
    for row in data['ranged']:
        if row['character_id'] not in characters:
            raise ValueError('존재하지 않는 원거리 캐릭터 참조')
        if not combat['systems'][0]['guard_kmph'] < row['speed_kmph'] < characters[row['character_id']]['speed_kmph']:
            raise ValueError('원거리 적 이동 속도 관계가 잘못되었습니다.')
    return data


def validate_combat(data, scale):
    from math import isfinite
    schemas = {
        'systems': {'id', 'player_hp', 'guard_kmph', 'input_lock_s', 'success_invuln_s',
                    'hit_invuln_s', 'stun_s', 'guard_angle_deg', 'energy_max',
                    'damage_multiplier', 'beam_duration_s', 'beam_tick_s', 'step_s'},
        'stages': {'id', 'energy_min', 'parry_window_s', 'beam_width_m'},
        'enemies': {'id', 'character_id', 'hp', 'speed_kmph', 'damage', 'energy_gain',
                    'attack_gap_m', 'windup_s', 'swing_s', 'recovery_s', 'sword_length_m',
                    'sword_width_m', 'sweep_deg'},
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
    return data


if __name__ == '__main__':
    generate()
