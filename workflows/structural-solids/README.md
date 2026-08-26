# Structural Solids

기계 2팀의 프레임, 업라이트, 마운트와 기타 고체 부품 구조해석 경계다. 기존 PRD의
`structural_mechanical`과 `structural_mapdl` 실행 유형을 사용한다.

## 입력 계약

- 승인된 Workbench golden project 또는 parameterized MAPDL master deck
- material revision, 하중과 구속 조건, 접촉 정의, Named Selection 계약
- mesh control과 node/element/body 수 및 품질 허용 범위
- load case, 단위계, solver와 ANSYS exact build

임의 APDL, topology가 바뀐 CAD 교체, 사용자 지정 executable은 허용하지 않는다.
Topology가 바뀌면 Named Selection, contact, support와 result scope를 다시 검증한다.

## 필수 결과와 게이트

- 최대 등가응력과 위치, 총변위와 위치, 반력 평형
- 재료 항복 기준이 명시된 경우에만 최소 안전율
- load step/substep 및 nonlinear convergence 근거
- mesh 통계, profile/template/input hash와 ANSYS build provenance

현재 Mechanical/Workbench 전용 adapter와 팀 golden case는 아직 구현·승인되지 않았다.
따라서 profile은 검증 완료 전까지 `enabled=false`를 유지한다.
