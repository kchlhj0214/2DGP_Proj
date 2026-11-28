# 기사검과 과장된 액션 검토

게임 적용 전 확인용이다. 기존 v1/v2 모델과 게임 판정·쿨타임·이동 코드는 바꾸지 않는다.

- 사용자 선택: Polyfork Arming Sword. 원본과 저작자 표시는 `../source/`에 보존한다.
- 패링: 왼쪽 대기 방패, 낮춘 준비 자세, 왼팔 전방 이동과 빠른 올려치기, 짧은 정지와 큰 후속 동작.
- 피격: 주인공과 근접 적 모두 순간 젖힘, 짧은 자세 유지, 반대 방향 반동, 회복.
- 근접 공격: 몸과 검을 옆으로 당긴 뒤 전방을 가로질러 쓸어 베기.
- 모든 시간은 검토 영상의 시간이다. 게임의 패링 판정 시간이나 공격 속도 변경이 아니다.

`motion-comparison.gif`는 네 동작과 축소 가독성을 동시에 보여준다. 오른쪽 작은 모형은
약 36픽셀 높이로 줄인 뒤 3배 확대했다. 최종 도트 스프라이트가 아니라 실루엣 확인용이다.
복잡한 장식과 세부 근육을 추가하지 않고 자세·박자에 집중한다.

원본: `shield-attack-dynamic-review.blend`. 프레임 1~29는 패링/베기, 33~57은 피격.
`data/art_dynamic.json`이 동작 수치의 원본이며 `manifest.json`은 제작 당시 사본이다.
재생성: Blender 배경 실행으로 `tools/build_dynamic_review.py`, 이후 Pillow 환경에서
`tools/make_dynamic_review_board.py`. 둘 다 제작 도구이며 게임 의존성이 아니다.

참고: Thomas Vasseur, Motion Twin, “Art Design Deep Dive: Using a 3D pipeline for 2D animation in Dead Cells”
https://www.gamedeveloper.com/production/art-design-deep-dive-using-a-3d-pipeline-for-2d-animation-in-i-dead-cells-i-

핵심 자세 중심의 공격과 짧은 전환이라는 제작 원리를 참고했다. 다른 게임의 모델·애니메이션 파일은 사용하지 않았다.
