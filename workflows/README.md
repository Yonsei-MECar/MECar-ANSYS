# 팀별 해석 워크플로

이 디렉터리는 팀 조직이 아니라 공학 도메인을 기준으로 안정적인 workflow 경계를
정의한다. 담당 팀이 바뀌어도 workflow ID와 결과 계약은 유지한다.

| 영역 | 현재 담당 | ANSYS 경로 | 대표 결과 | 상태 |
|---|---|---|---|---|
| [`structural-solids`](structural-solids/) | 기계 3팀 | Mechanical/Workbench 또는 승인 MAPDL | 응력, 변위, 반력, 안전율 | 계약 초안 |
| [`aero-downforce`](aero-downforce/) | 기계 3팀 | Fluent 3D 외부유동 | drag, downforce, Cd/Cl, 수렴 근거 | 계약 초안 |
| [`wing-stiffness`](wing-stiffness/) | 기계 3팀 | Mechanical + 선택적 Fluent 압력 전달 | 처짐, 비틀림, 응력, 강성 | 계약 초안 |

공통 실행 큐와 산출물 처리는 `automation`, MCP 연결은 `mcp-server`가 담당한다.
각 workflow는 다음 승격 단계를 독립적으로 거친다.

1. `draft`: schema, 좌표계, 단위, 허용 입력과 KPI를 합의한다.
2. `golden-case`: 팀이 수동으로 검토한 기준 케이스와 허용 오차를 고정한다.
3. `validated`: 지정 ANSYS build에서 자동 결과가 기준 결과와 일치한다.
4. `enabled`: profile과 실행 머신의 외부 실행 스위치를 마지막에 활성화한다.

## 팀 간 입력 인계

기계 2팀은 VD와 hardpoint 설계를 담당하고, 승인된 hardpoint revision, load
envelope·load case, 좌표계와 단위를 구조해석 입력으로 인계한다. 기계 3팀은 이
handoff를 변경 불가능한 입력 기준으로 받아 프레임·고체 구조해석과 CFD를 수행한다.
입력이 바뀌면 새 revision으로 다시 인계하고 기존 golden case를 자동 재사용하지
않는다.

공개 저장소에는 schema, 비밀이 제거된 예제, 자동화 코드와 검증 절차만 둔다.
실제 CAD, mesh, case/data, Workbench project, 라이선스·릴레이 설정과 solver 결과는
저장소 밖 restricted input/artifact 영역에서 관리한다. 결과 배포는 로컬에서
불변 artifact와 checksum을 확정한 뒤 승인된 비공개 문서 저장소가 맡는다.

`CODEOWNERS`는 GitHub 팀이 생성된 뒤 도메인별 팀 slug로 추가한다. 현재 조직에는
GitHub Team이 없으므로 개인 계정을 임시 owner로 고정하지 않는다.
