# MECar ANSYS

MECar의 ANSYS 해석 자동화 소스를 공개하기 위한 저장소다. 실행 가능한 코드,
스키마, 안전한 예제와 테스트만 버전 관리하며 실제 차량 데이터와 운영 비밀은
저장소 밖에서 관리한다.

| 구성 요소 | 용도 | 라이선스 |
|---|---|---|
| [`automation`](automation/) | 해석 작업 큐, 실행 게이트, 산출물 관리 | MIT |
| [`mcp-server`](mcp-server/) | MAPDL·Workbench와 MCP 클라이언트를 연결하는 브리지 | MIT |
| [`fluent-2d-runner`](fluent-2d-runner/) | Fluent 2021 R1 2D 케이스 준비·실행·검증 | GPL-2.0-or-later |

## 공개 범위

저장소에 포함하는 것은 소스 코드, JSON Schema, 비밀이 제거된 예제 설정,
테스트 fixture와 재현 절차다. 다음 항목은 공개 저장소에 넣지 않는다.

- ANSYS 설치 파일, 라이선스 파일·서버 주소와 학교 인증/릴레이 설정
- 비밀키, 인증서 개인키, 토큰, 비밀번호, 운영 `.env`와 실제 호스트 설정
- 차량 CAD, 원본 형상, 메시, Workbench 프로젝트와 Fluent/MAPDL 결과
- 실행 로그, case/data, 이미지·보고서 묶음과 팀 내부 운영 문서

해석 결과는 런타임 디렉터리에 먼저 불변 산출물로 확정한 뒤 별도 비공개
배포 작업이 NAS, 팀 서버 또는 승인된 문서 저장소로 전달한다. 저장소의 CI에는
외부 ANSYS 실행이나 운영 저장소 업로드 권한을 주지 않는다. 운영 연동이 필요하면
서버의 secret store 또는 CI secret을 통해 주입하고, 값 자체는 커밋하지 않는다.

`.gitignore`는 실수를 줄이는 보조 장치일 뿐 이미 추적된 비밀을 보호하지 않는다.
비밀이 커밋되었다면 파일 삭제만 하지 말고 해당 자격 증명을 즉시 폐기·교체한다.

## 개발 확인

각 하위 프로젝트의 README에 로컬 실행법이 있다. 기본 단위 테스트는 외부
ANSYS, 라이선스 서버, SMTP 또는 NAS에 접속하지 않으며 GitHub Actions에서도
같은 범위만 실행한다.

라이선스 적용 범위는 [`LICENSE.md`](LICENSE.md), 외부 구성 요소와 상표 고지는
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)를 확인한다.
