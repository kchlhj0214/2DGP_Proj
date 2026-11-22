# 자동 생성 파일: data/waves.json을 수정한 뒤 tools/generate_data.py 실행
SETTINGS = {'main': {'id': 'main',
          'arrival_interval_s': 0.24,
          'gate_wait_s': 0.45,
          'gate_lift_s': 0.55,
          'portal_offset_m': 7.0,
          'bridge_inset_m': 5.0,
          'entrance_speed_mps': 6.0,
          'reveal_m': 2.3,
          'enemy_gap_m': 0.7}}

WAVES = {'wave1': {'id': 'wave1',
           'number': 1,
           'melee_id': 'melee',
           'ranged_id': 'ranged',
           'melee_per_gate': 1,
           'ranged_per_gate': 1},
 'wave2': {'id': 'wave2',
           'number': 2,
           'melee_id': 'melee',
           'ranged_id': 'ranged',
           'melee_per_gate': 2,
           'ranged_per_gate': 1},
 'wave3': {'id': 'wave3',
           'number': 3,
           'melee_id': 'melee',
           'ranged_id': 'ranged',
           'melee_per_gate': 3,
           'ranged_per_gate': 1},
 'wave4': {'id': 'wave4',
           'number': 4,
           'melee_id': 'melee',
           'ranged_id': 'ranged',
           'melee_per_gate': 0,
           'ranged_per_gate': 0}}

MODES = {'all': {'id': 'all', 'key': 0},
 'melee': {'id': 'melee', 'key': 8},
 'ranged': {'id': 'ranged', 'key': 9}}

SINGLE_MODES = {'none': {'id': 'none', 'enemy_id': 'melee', 'count': 0},
 'melee': {'id': 'melee', 'enemy_id': 'melee', 'count': 1},
 'ranged': {'id': 'ranged', 'enemy_id': 'ranged', 'count': 1}}

GATES = {'north': {'id': 'north', 'x_ratio': 0, 'y_ratio': 1},
 'east': {'id': 'east', 'x_ratio': 1, 'y_ratio': 0},
 'south': {'id': 'south', 'x_ratio': 0, 'y_ratio': -1},
 'west': {'id': 'west', 'x_ratio': -1, 'y_ratio': 0}}

RANGED = {'ranged': {'id': 'ranged',
            'character_id': 'player',
            'hp': 60,
            'speed_kmph': 10,
            'range_m': 15,
            'attack_interval_s': 3,
            'projectile_speed_mps': 8,
            'projectile_radius_m': 0.7,
            'damage': 10,
            'energy_gain': 10}}

