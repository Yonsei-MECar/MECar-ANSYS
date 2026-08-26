# Wing Stiffness

기계 3팀의 윙 및 지지구조 강성·강도 해석 경계다. 독립 구조 하중 케이스와 Fluent
압력을 전달하는 `aero_to_structural_one_way` 단방향 연성 케이스를 분리한다.

## 독립 구조 케이스

- 규정·시험 또는 승인 공력 하중 envelope를 명시적 분포 하중으로 적용
- 고정부, insert, 접착부, laminate/material revision과 접촉 계약 고정
- tip deflection, 주요 단면 twist, 최대응력과 반력 평형 검증

## 단방향 연성 케이스

- 원본 Fluent run ID와 pressure field hash를 불변 입력으로 사용
- CFD surface와 structural target 사이 mapping 방법·좌표계·단위를 버전 고정
- 전달 전후 총 힘과 모멘트 보존 오차를 solve 전에 검사
- mapping coverage와 미매핑 면적이 profile 허용치를 넘으면 실행 거부
- 구조 변형을 Fluent로 되돌리지 않으므로 two-way FSI로 표시하지 않음

두 케이스 모두 변위, 비틀림, 응력, 반력, mesh/convergence와 provenance를 남긴다.
현재 pressure mapping과 Mechanical golden case는 미구현이므로 자동 실행 profile은
활성화하지 않는다.
