# 자동 생성 파일: data/boss.json을 수정한 뒤 tools/generate_data.py 실행
BOSSES = {'orc': {'id': 'orc',
         'character_id': 'player',
         'wave_id': 'wave4',
         'hp': 240,
         'scale': 1.8,
         'speed_kmph': 11,
         'arrival_s': 1.25,
         'between_attacks_s': 0.55,
         'push_s': 0.32}}

CHARGES = {'main': {'id': 'main',
          'damage': 28,
          'energy_ratio': 0.5,
          'guard_damage_ratio': 0.25,
          'guard_push_m': 6.0,
          'windup_s': 1.05,
          'recovery_s': 3.0,
          'recovery_motion_s': 1.0,
          'speed_mps': 18.0,
          'length_m': 19.0,
          'width_m': 5.2}}

SLAMS = {'main': {'id': 'main',
          'damage': 32,
          'windup_s': 1.15,
          'recovery_s': 1.25,
          'radius_m': 11.5,
          'eruption_s': 0.48,
          'spikes': 56}}

ROCKS = {'main': {'id': 'main',
          'damage': 12,
          'energy_ratio': 0.25,
          'radius_m': 2.25,
          'count': 9,
          'flight_s': 1.2,
          'interval_s': 0.08,
          'art': 'assets/sprites/boss-rock.png'}}

SWINGS = {'main': {'id': 'main',
          'damage': 24,
          'energy_ratio': 0.25,
          'guard_push_diameter_ratio': 0.25,
          'windup_s': 0.8,
          'swing_s': 0.32,
          'recovery_s': 1.15,
          'length_m': 8.0,
          'width_m': 1.9,
          'spread_deg': 140}}

