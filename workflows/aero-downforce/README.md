# Aero Downforce

기계 3팀의 전체 차량 및 공력 부품 외부유동 해석 경계다. 기존 PRD의
`aero_fluent` 실행 유형을 사용하며, 공개 `fluent-2d-runner`는 파이프라인 검증용
참고 구현일 뿐 차량 설계 기준값을 만들지 않는다.

## 입력 계약

- 승인된 Fluent 3D prepared case 또는 별도로 검증된 geometry-to-case pipeline
- 차체 좌표계, inlet/yaw 정의, drag/lift 축과 downforce 부호
- 공기 물성, 속도, reference area/length, moving ground와 wheel 조건
- turbulence/wall treatment, mesh 품질과 y-plus 목표, force 대상 wall zone

## 필수 결과와 게이트

- drag/lift/downforce 원시 힘과 reconciled Cd/Cl, 선택적 Cm
- residual뿐 아니라 mass imbalance와 force-monitor 안정성 window
- 마지막 값과 window 평균·표준편차·slope의 분리 기록
- mesh 품질, 좌표 변환, profile/case hash와 ANSYS build provenance

현재 3D 차량 case, golden result와 운영 Fluent profile은 준비되지 않았다. 실제 형상과
case/data는 공개 저장소에 커밋하지 않고 restricted input 영역에서 승인한다.
