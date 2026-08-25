# MECar ANSYS 자동해석·지식관리 플랫폼 PRD

## 문서 정보

| 항목 | 내용 |
|---|---|
| 문서 상태 | Review Ready |
| 문서 버전 | 0.2 |
| 작성일 | 2026-08-23 |
| 제품 가칭 | MECar Analysis Automation Hub |
| 기준 실행 환경 | 개인 Windows 11 노트북/데스크탑 |
| 기준 해석 환경 | ANSYS 2021 R1, Release 211 |
| 주 대상 해석 | 고체 강도해석, 외부 공기역학 해석 |
| 기본 결과 전달 | 범용 SMTP 이메일 |
| 기본 원본 저장소 | 로컬 SSD 및 NAS |
| 기본 지식 저장소 | Notion |
| 구현 일정 | 본 문서 범위에서 의도적으로 제외 |

이 문서는 제품이 제공해야 할 기능, 품질, 데이터 경계, 외부 연동, 보안 및 인수 조건을 정의한다. 구현 세부 기술은 본 요구사항을 만족하는 범위에서 변경할 수 있으나, 제품 경계와 데이터 무결성 원칙은 유지해야 한다.

### 문서 구성

- 1~8장: 제품 정의, 목표, 사용자와 범위
- 9~12장: 구조, 사용자 흐름, 기능 요구사항과 공급자 중립 통합
- 13~15장: 데이터, 폴더·배포와 Notion 모델
- 16~22장: 보안, 신뢰성, 성능, 호환성, 관측성, 오류와 보존
- 23~24장: 인수 기준과 필수 장애 시험
- 25~29장: 설정, 운영 준비물, 결정 정책, 기술 근거와 최종 경계

---

## 1. 제품 요약

MECar Analysis Automation Hub는 개인 Windows PC에서 실행되는 로컬 자동화 프로그램이다. 사용자가 ANSYS를 직접 실행하거나 GUI를 조작하지 않아도 승인된 해석 프로필에 따라 입력을 검증하고, 작업을 큐에 적재하고, ANSYS Workbench/Mechanical, MAPDL 또는 Fluent를 배치 실행하고, 결과를 검증·후처리·보관·정리·전달한다.

핵심 제품 정의는 다음과 같다.

> 인증된 ANSYS 2021 R1 프로필을 선택해 작업을 제출하면, ANSYS UI 조작 없이 검증, 큐잉, 해석, 수렴 판정, 후처리, NAS 보관, Notion 발행 및 이메일 전달이 완료되고, 실패·취소·재부팅 상황에서도 명확한 상태와 증거가 남아야 한다.

정상적인 반복 작업은 완전 무인으로 처리한다. 단, 새로운 해석 종류의 최초 템플릿 제작, Named Selection과 경계조건 설정, 메시 전략 수립, 기준 결과 검증은 해석 전문가가 ANSYS GUI에서 수행하는 별도의 프로필 저작 작업으로 인정한다.

---

## 2. 배경과 해결할 문제

현재 해석 업무는 다음 문제를 가진다.

- 해석마다 사용자가 ANSYS를 직접 실행하고 같은 설정을 반복해야 한다.
- 모델, 경계조건, 메시, 기준면적, 좌표계가 사람마다 달라 결과 비교가 어렵다.
- 장시간 해석 중 라이선스, 절전, 재부팅, 파일 잠금 문제가 발생하면 작업 상태를 잃기 쉽다.
- 대형 결과 파일, 요약 문서와 설계 자료가 로컬 PC, NAS, Notion 등에 흩어져 있다.
- 모든 팀원이 동일한 협업 서비스 계정을 보유하지 않아 특정 메신저에 종속된 알림이 적합하지 않다.
- 외부 서비스 장애가 해석 자체의 성공·실패와 뒤섞이면 불필요한 재해석이나 중복 알림이 발생한다.
- 향후 이메일, Notion, NAS를 다른 서비스로 교체할 가능성이 있다.

제품은 이 문제를 승인된 프로필, 영속 큐, 공급자 중립 통합 계층, 로컬 우선 저장과 추적 가능한 결과 패키지로 해결한다.

---

## 3. 제품 목표

### 3.1 핵심 목표

1. 승인된 작업은 사용자가 ANSYS를 수동 실행하지 않고 끝까지 처리한다.
2. 구조해석과 공력해석의 입력·단위·물리 정의·출력을 프로필로 표준화한다.
3. 작업 상태를 로컬 SQLite에 영속화하여 프로세스 또는 PC 재시작 후 복구한다.
4. 라이선스·CPU·RAM·디스크·전원 상태를 고려해 개인 PC에서 안전하게 실행한다.
5. 종료 코드뿐 아니라 결과 파일, 유한한 지표, 메시·수렴 기준을 확인해 공학적 완료 상태를 판정한다.
6. 접수 snapshot과 필수 결과 package는 local immutable ArtifactStore에 확정하고, 장기 보존 대용량 결과는 NAS에 복제하며, Notion에는 검색 가능한 요약·KPI·근거를 발행한다.
7. 가입 여부와 관계없이 유효한 이메일 주소로 결과를 전달한다.
8. ANSYS 완료, NAS 복제, Notion 발행, 이메일 발송 상태를 서로 독립적으로 관리한다.
9. 이메일·저장소·지식 플랫폼을 핵심 코드 변경 없이 어댑터와 설정으로 교체한다.
10. 모든 결과에 입력, 템플릿, ANSYS 버전, 파라미터, 단위, 체크섬과 수렴 근거를 연결한다.

### 3.2 제품 성공 조건

- 인증된 구조해석 및 Fluent 기준 작업이 ANSYS UI 조작 없이 종단간 완료된다.
- 동일 입력의 핵심 지표가 승인된 수동 기준 결과와 프로필별 허용 오차 안에서 일치한다.
- 같은 제출을 반복 감지해도 중복 solve가 발생하지 않는다.
- 에이전트 또는 PC 강제 재시작 후 작업·이벤트·알림이 유실되지 않는다.
- SMTP, NAS 또는 Notion 장애가 ANSYS solve를 다시 실행시키지 않는다.
- 완료 결과마다 재현에 필요한 버전·단위·조건·체크섬이 모두 남는다.
- SMTP 서버를 변경해도 ANSYS Core, 작업 manifest 및 큐 스키마를 수정하지 않는다.
- 자동 생성된 Notion 내용이 사람이 작성한 내용을 덮어쓰지 않는다.

---

## 4. 비목표

다음 항목은 본 제품의 기본 범위가 아니다.

- 임의 STEP/STL 파일에서 재료, 지지, 하중, 접촉 또는 유체 경계조건을 자동 추론
- 임의 형상에 대해 항상 성공하는 완전 자동 geometry-to-mesh
- 해석 전문가의 모델 검증과 공학적 판단 대체
- 검증되지 않은 템플릿 결과의 물리적 정확성 보증
- 사용자가 제출한 임의 APDL, Python, Workbench journal, Fluent journal 또는 실행 파일 실행
- PC가 꺼져 있거나 절전 중인 상태에서 계속되는 클라우드 서비스 수준의 실행 보장
- 단일-PC 제품 범위에서의 다중 PC 분산 해석, RSM, HPC 또는 클라우드 solve
- 단일-PC 제품 범위에서의 자동 형상 최적화 및 대규모 설계 탐색
- 원본 CAD, RST, CAS/DAT 등 대용량·민감 파일의 이메일 자동 첨부
- 수신 메일의 답장 내용을 명령으로 해석하는 기능
- 이메일의 실제 수신·열람 보장
- Notion을 큐 또는 대용량 원본 저장소로 사용하는 것
- 외부 공개 파일 호스팅

---

## 5. 제품 원칙

### 5.1 데이터 권위

| 데이터 | 권위 있는 저장소 |
|---|---|
| 작업 및 실행 상태 | 로컬 NTFS의 SQLite |
| 현재 attempt 작업 파일 | 짧은 ASCII 로컬 SSD 경로 |
| 접수된 Job 입력 snapshot | 로컬 immutable ArtifactStore |
| Job 성공을 증명하는 필수 결과 package | 로컬 immutable ArtifactStore |
| 장기 보존 대용량 결과 | NAS 또는 승인된 원격 ArtifactStore의 독립 archive/replica |
| 해석 결과의 검색용 projection | Notion |
| 외부 operation 상태 | 로컬 Integration Outbox |
| 비밀정보 | Windows Credential Manager 또는 DPAPI |

### 5.2 상태 분리

해석 요청, 실행 시도, solver 결과, 공학 판정, artifact 확정과 외부 연동 성공을 분리한다.

~~~text
제출물 접수·거부       = submission 상태
논리 해석 요청         = job 상태
한 번의 실제 실행      = attempt 상태
ANSYS 실행 결과        = solver_outcome
수렴·물리 판정         = engineering_outcome
필수 결과 패키지 확정  = artifact_status
최종 해석 결과         = job_terminal_status
NAS 복제              = storage operation 상태
Notion 발행           = publication operation 상태
알림 발송              = notification operation 상태
~~~

Job 성공의 권위 있는 commit point는 동일 attempt의 필수 결과 package가 로컬 immutable ArtifactStore에 원자적으로 확정되는 시점이다. NAS는 기본적으로 후속 archive/replica이며, NAS 미완료는 별도 archival 상태와 product rollup에 반영하되 analysis terminal status를 바꾸지 않는다. Notion, SMTP 또는 다른 provider가 실패해도 모든 analysis terminal status는 그대로 유지하고 실패한 외부 operation만 재시도한다.

### 5.3 Terminal semantics

| job_terminal_status | 필수 진입 조건 | 대표 후속 event |
|---|---|---|
| SUCCEEDED | solver_outcome=SOLVED, engineering_outcome=PASSED, mandatory result package COMMITTED | analysis.job.succeeded |
| COMPLETED_WITH_WARNINGS | solver_outcome=SOLVED, engineering_outcome=PASSED_WITH_WARNINGS 또는 policy가 허용한 UNKNOWN, mandatory result package COMMITTED | analysis.job.completed_with_warnings |
| FAILED_ENGINEERING_CHECK | solver_outcome=SOLVED, engineering_outcome=FAILED, immutable diagnostic package COMMITTED | analysis.job.engineering_failed |
| FAILED_EXECUTION | solver/preflight/artifact 실패가 retry 정책상 terminal이고 최소 immutable failure record와 확보 가능한 evidence index가 commit됨 | analysis.job.failed |
| CANCELLED | final result commit 전에 cancel이 승리하고 최소 immutable cancel record 및 partial artifact index가 commit됨 | analysis.job.cancelled |

REJECTED와 QUARANTINED는 Job 생성 전 submission terminal status다. Cancel Command의 FAILED는 Job terminal status가 아니며, 취소가 실패해 solver가 계속 실행되면 Job은 ACTIVE 상태를 유지한다. 외부 integration operation은 위 terminal 값 어느 것도 변경할 수 없다.

### 5.4 안전한 자동화

- 사용자는 승인된 profile과 허용된 parameter만 선택한다.
- 프로필은 정확한 ANSYS 버전과 템플릿 hash에 결합한다.
- 원본 프로젝트와 case는 직접 수정하지 않고 job workdir로 복제한다.
- 모든 job은 불변 입력 snapshot과 독립 attempt 디렉터리를 사용한다.
- 신뢰할 수 없는 제출물로 임의 코드를 실행하지 않는다.

### 5.5 공급자 중립성

Core는 SMTP, Notion, UNC 경로 또는 특정 외부 SDK를 직접 호출하지 않는다. 외부 연동은 기능 유형별 port와 provider adapter로만 접근한다.

---

## 6. 사용자 및 역할

### 6.1 제출자

- 승인된 해석 프로필을 선택한다.
- 허용된 파라미터와 입력 파일을 제출한다.
- 큐와 진행 상태를 조회한다.
- 본인 권한 범위에서 취소 또는 재시도를 요청한다.

### 6.2 해석 담당자 / Template Author

- ANSYS GUI에서 골든 템플릿을 제작한다.
- Named Selection, 경계조건, 재료, 메시, 수렴 기준과 결과 항목을 정의한다.
- 기준 해석과 허용 오차를 등록한다.
- 프로필 버전을 승인, 비활성화 또는 폐기한다.

### 6.3 운영자

- ANSYS 설치 경로, 라이선스, 자원 한도와 실행 정책을 관리한다.
- NAS, Notion, SMTP provider 설정과 비밀정보 참조를 관리한다.
- 큐, dead-letter, 충돌, 용량과 provider health를 확인한다.
- 설치, 업데이트, 진단 bundle과 백업·복구를 수행한다.

### 6.4 검토자

- 보고서, KPI, 수렴 근거와 원본 위치를 확인한다.
- Notion 초안을 승인하거나 수정한다.
- engineering check 실패 및 conflict를 검토한다.

### 6.5 이메일 수신자

- NAVER WORKS 가입 여부와 관계없이 유효한 이메일 주소로 요약 결과를 받는다.
- 계정 권한이 있는 경우 Notion 또는 NAS HTTPS 링크를 연다.

### 6.6 외부 시스템

- ANSYS 2021 R1 및 License Manager
- NAS/SMB
- Notion API
- SMTP relay
- 선택적 MCP 클라이언트

### 6.7 기본 권한 매트릭스

| 기능 | 제출자 | 해석 담당자 | 운영자 | 검토자 |
|---|---:|---:|---:|---:|
| 승인된 profile로 job 제출 | 허용 | 허용 | 허용 | 선택 |
| 본인 job 조회 | 허용 | 허용 | 허용 | 허용 |
| 전체 queue 조회 | 제한 | 허용 | 허용 | 제한 |
| queued job 취소 | 본인 job | 허용 | 허용 | 불가 |
| running job 강제 종료 | 불가 | 제한 | 허용 | 불가 |
| 실패 attempt 재시도 | 요청 | 승인 | 허용 | 요청 |
| profile 작성·수정 | 불가 | 허용 | 관리 | 불가 |
| profile 활성화·폐기 | 불가 | 승인 | 허용 | 불가 |
| provider·수신자 설정 | 불가 | 불가 | 허용 | 불가 |
| native result 접근 | 정책 기반 | 허용 | 허용 | 정책 기반 |
| Notion 초안 승인 | 불가 | 허용 | 허용 | 허용 |
| retention·삭제 실행 | 불가 | 제한 | 허용 | 불가 |

동일 사용자가 여러 역할을 가질 수 있으나, 작업 제출자가 manifest를 통해 자신의 권한을 확대할 수 없어야 한다.

기본 단일-PC 구성의 신뢰 주체는 Agent를 실행하는 한 명의 Windows 사용자이며 OS SID를 actor ID로 기록한다. manifest의 actor/role 문자열은 신뢰하지 않는다. 여러 Windows 사용자가 공유 제출하는 구성을 활성화할 때는 사용자별 ACL이 적용된 inbox, Windows 인증 또는 서명된 submission/API token 중 승인된 방식으로 actor를 검증해야 하며, 검증할 수 없는 제출은 익명 저권한 정책으로 거부한다.

### 6.8 핵심 사용자 스토리

- 제출자로서 승인된 profile과 입력을 제출하고 ANSYS를 열지 않은 채 결과 이메일을 받고 싶다.
- 해석 담당자로서 한 번 검증한 물리 조건과 결과 기준을 versioned profile로 반복 사용하고 싶다.
- 운영자로서 라이선스·재부팅·NAS·SMTP 장애가 있어도 작업과 결과를 잃지 않고 원인을 구분하고 싶다.
- 검토자로서 결과 수치뿐 아니라 수렴 근거, 단위, 기준면적, 입력과 template version을 확인하고 싶다.
- 팀원으로서 특정 협업 서비스에 가입하지 않아도 일반 이메일로 PDF 요약을 받고 싶다.
- 지식 관리자로서 NAS의 설계 자료를 중복 없이 분석·분류하고 Notion 초안으로 정리하고 싶다.
- 유지보수자로서 NAVER WORKS SMTP를 다른 SMTP 또는 알림 서비스로 바꿀 때 Core를 수정하지 않고 싶다.

---

## 7. 핵심 용어

| 용어 | 정의 |
|---|---|
| Job | 사용자가 제출한 하나의 논리적 해석 요청 |
| Attempt | Job을 실제로 실행한 한 번의 시도 |
| Workflow | 구조, MAPDL, 공력 등 해석 유형 |
| Profile | 허용 입력, 템플릿, solver, 물리 정의, 결과와 판정 기준의 버전된 묶음 |
| Template | 실제 Workbench project, MAPDL master deck, Fluent case/journal 등 실행 기반 파일 |
| Artifact | manifest, metrics, report, plot, log, native solver result 등의 산출물 |
| Domain Event | Core에서 발생한 공급자 중립 상태 변화 |
| Integration Operation | NAS 복제, Notion 발행, 이메일 발송 같은 외부 작업 |
| Provider | SMTP, SMB, Notion 등 특정 외부 구현 |
| Route | 논리적 목적지를 실제 provider instance에 매핑한 설정 |
| Golden Case | 프로필 검증에 사용한 승인된 기준 입력과 결과 |
| Provenance | 결과가 어떤 입력·버전·설정·원문 위치에서 생성됐는지 나타내는 근거 |

---

## 8. 제품 범위 및 우선순위 정의

이 문서의 Must, Should, Could는 구현 일정이 아니라 제품 필요도를 나타낸다.

- Must: 제품으로 인정되기 위한 필수 요구사항
- Should: 기본 운영 품질에 중요하며 누락 시 명시적 제한이 필요한 요구사항
- Could: 확장 지점으로 설계는 열어 두되 기본 동작에 필수는 아닌 요구사항

### 8.1 지원 Workflow

| Workflow ID | ANSYS 도구 | 요구 수준 | 용도 |
|---|---|---:|---|
| structural_mechanical | Workbench + Mechanical Static Structural | Must | 일반 CAD 기반 강도·접촉·하중 해석 |
| structural_mapdl | MAPDL native batch | Should | 준비된 parameterized APDL 모델 반복 해석 |
| aero_fluent | Fluent native batch | Must | 외부유동, drag, downforce, Cd, Cl |
| aero_to_structural_one_way | Fluent → Static Structural | Could | 공력압력 기반 단방향 구조해석 |
| cfx | CFX | Could | 승인된 CFX 템플릿이 있을 때 |

### 8.2 기본 제출 채널

| 채널 | 요구 수준 |
|---|---:|
| 로컬 Hot Folder | Must |
| 로컬 Dashboard | Must |
| CLI/PowerShell submit command | Should |
| 기존 ansys-mcp-server를 통한 MCP 제출·조회 | Could |
| Notion Analysis Request 데이터 소스 | Could, 기본 비활성 |

---

## 9. 상위 시스템 구조

~~~text
Hot Folder / Local UI / CLI / MCP / Optional Notion Request
                         │
                         ▼
                Ingestor + Validator
                         │
                         ▼
                 SQLite Durable Queue
                         │
                         ▼
              Dispatcher + Resource Guard
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      Mechanical       MAPDL          Fluent
          │              │              │
          └──────────────┼──────────────┘
                         ▼
        Engineering Validation + Postprocessing
                         │
                         ▼
             Local Artifact Finalization
                         │ Domain Events
                         ▼
            Transactional Integration Outbox
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          NAS/SMB      Notion      SMTP Email
~~~

### 9.1 주요 컴포넌트

- Agent Host: 자동 시작, singleton, lifecycle, health
- Ingestor: watcher, periodic scan, 안정화 확인, staging
- Validator: schema, 파일, 보안, profile, 환경 검사
- Queue Repository: SQLite transaction과 상태 전이
- Dispatcher: 우선순위, 자원, 라이선스, worker lease
- Solver Adapters: Mechanical, MAPDL, Fluent
- Process Supervisor: heartbeat, timeout, cancel, process tree
- Engineering Validator: 수렴·품질·결과 판정
- Postprocessor: KPI, 표, 그림, 보고서
- Artifact Manager: local finalize, checksum, retention
- Integration Router: event를 storage/publication/notification operation으로 변환
- Provider Workers: SMTP, SMB, Notion
- Document Pipeline: NAS/Notion 자료의 파싱·분석·검색·발행
- Local Dashboard/Tray: 사용자·운영자 UI
- Optional MCP Gateway: queue 기반 도구 제공

---

## 10. 주요 사용자 흐름

### 10.1 최초 설치 및 진단

1. 사용자가 배포 패키지를 설치한다.
2. 설치 프로그램이 로컬 데이터 루트와 Task Scheduler 항목을 구성한다.
3. 프로그램이 ANSYS 2021 R1 실행 파일을 탐지한다.
4. 프로그램이 batch 실행 가능 여부, workdir 쓰기, 디스크, NAS, Notion, SMTP를 각각 진단한다.
5. 실제 라이선스가 필요한 smoke test는 운영자가 명시적으로 실행한다.
6. 진단 결과는 비밀정보가 제거된 report로 저장한다.

### 10.2 Hot Folder 해석 제출

1. 사용자가 job package를 임시 이름으로 복사한다.
2. 복사가 끝난 뒤 atomic rename 또는 READY marker를 생성한다.
3. Ingestor가 파일 크기·mtime 안정성과 package 안전성을 확인한다.
4. 입력을 local staging으로 복사하고 checksum을 계산한다.
5. Validator가 manifest와 profile 계약을 검사한다.
6. 유효하면 accepted snapshot과 queue row를 생성하고, 유효하지 않으면 rejected/quarantine으로 이동한다.
7. 큐가 자원·라이선스 조건을 만족하면 solve를 시작한다.

### 10.3 무인 ANSYS 실행

1. adapter가 profile과 template snapshot에서 job script를 생성한다.
2. ANSYS를 batch mode로 실행한다.
3. stage marker, transcript, solver activity와 process heartbeat를 감시한다.
4. timeout·cancel·crash·라이선스 오류를 분류한다.
5. solve 종료 후 expected outputs, 유한 metric, 수렴 기준을 검사한다.
6. 결과 package를 local artifacts에 원자적으로 확정한다.

### 10.4 결과 보관·정리·전달

1. local artifact 완료 이벤트를 저장한다.
2. route policy가 storage, publication과 notification operation 및 dependency graph를 계획한다.
3. NAS replica와 Notion publication은 선언된 criticality와 dependency에 따라 실행된다.
4. 알림은 dependency deadline까지 link를 기다리고 정책에 따라 link 포함, summary-only 또는 후속 link-ready 알림을 선택한다.
5. 각 operation은 독립적으로 재시도되고 receipt를 남긴다.
6. 사용자는 local dashboard에서 analysis와 각 integration 상태 및 product rollup을 별도로 확인한다.

### 10.5 NAS 자료 분석과 Notion 정리

1. SMB source scanner가 승인된 NAS prefix를 주기적으로 검사한다.
2. 새 파일이나 변경 파일을 local immutable cache로 복사한다.
3. 파일 hash, 메타데이터와 source version을 기록한다.
4. parser가 본문을 Markdown 또는 중립 document model로 변환한다.
5. 분석기가 요약, 분류, 태그, 의사결정, 요구사항과 후속 작업을 생성한다.
6. 각 주장에 원본 위치와 version provenance를 연결한다.
7. local full-text index를 갱신한다.
8. Notion에 초안 page를 upsert한다.
9. 검토자가 승인하거나 수정한다.
10. 결과 링크를 필요한 수신자에게 이메일로 보낸다.

### 10.6 재부팅·장애 복구

1. Agent 시작 시 active attempt와 CLAIMED/EXECUTING integration operation을 각각 reconcile한다.
2. PID, process creation time, command, workdir와 heartbeat를 확인한다.
3. adapter가 survives_agent_crash와 reattach_supported를 선언하고 exact build에서 검증된 경우에만 살아 있는 process에 재부착한다.
4. 기본 kill-on-agent-close 정책 또는 재부착 미지원 profile은 orphan 여부를 검증해 종료·격리하고 attempt를 INTERRUPTED로 표시한다.
5. PC reboot 후 process 재부착은 시도하지 않고, 검증된 checkpoint resume 또는 clean-retry-safe 정책에 따라 새 attempt 후보로 전환한다.
6. NAS, Notion, SMTP outbox operation은 solve와 무관하게 이어서 처리한다.

---

## 11. 기능 요구사항

### 11.1 Agent 설치 및 실행

- FR-AGENT-001 Must: Windows 로그인 시 Task Scheduler로 자동 시작해야 한다.
- FR-AGENT-002 Must: 같은 PC에서 agent가 중복 실행되지 않도록 named mutex 또는 동등한 singleton을 사용해야 한다.
- FR-AGENT-003 Must: Workbench 호환성을 위해 기본 모드는 동일 사용자 세션에서 실행해야 한다.
- FR-AGENT-004 Must: 실행·데이터·설정·비밀정보 경로를 분리해야 한다.
- FR-AGENT-005 Must: ANSYS 경로를 자동 탐지하되 명시적 override를 지원해야 한다.
- FR-AGENT-006 Must: 시작 시 core config schema, workdir, DB와 필수 executable을 검사하고 provider/route config는 각각 독립적으로 진단해야 한다.
- FR-AGENT-007 Should: 트레이 아이콘에서 실행 상태, pause와 dashboard 열기를 제공해야 한다.
- FR-AGENT-008 Must: 자동 업데이트는 실행 중 job을 변경하지 않아야 하며 명시적 설치 방식으로만 수행해야 한다.
- FR-AGENT-009 Must: 배포 패키지에 ANSYS binary, license file 또는 상용 template을 무단 포함하지 않아야 한다.
- FR-AGENT-010 Must: uninstall은 기본적으로 queue DB, 결과, profile, config와 credential을 보존해야 한다.
- FR-AGENT-011 Must: 데이터 완전 삭제는 별도 명시적 purge 동작과 exact target 확인을 요구해야 한다.
- FR-AGENT-012 Must: 설치·업데이트 전후 version과 config migration 결과를 기록해야 한다.
- FR-AGENT-013 Must: optional provider/route config 오류 때문에 local queue와 solver 기능 전체를 차단하지 않고 해당 integration만 DEGRADED로 표시해야 한다.

### 11.2 Job Package 및 접수

- FR-INGEST-001 Must: 제출 단위는 폴더 또는 ZIP 기반 ansysjob package여야 한다.
- FR-INGEST-002 Must: job manifest, 입력 파일과 마지막 READY marker 또는 atomic final rename을 사용해야 한다.
- FR-INGEST-003 Must: FileSystemWatcher는 즉시 깨우기 용도로만 사용하고 periodic full scan으로 누락을 보정해야 한다.
- FR-INGEST-004 Must: package가 일정 시간 동안 크기와 mtime이 안정되기 전에는 접수하지 않아야 한다.
- FR-INGEST-005 Must: ZIP slip, 절대경로, 상위경로, symlink, junction, reparse escape를 차단해야 한다.
- FR-INGEST-006 Must: 파일 수, 총 크기, 개별 크기, 확장자와 압축비 제한을 적용해야 한다.
- FR-INGEST-007 Must: 제출물의 SHA-256과 크기를 저장해야 한다.
- FR-INGEST-008 Must: submission ID와 package hash를 이용해 중복 solve를 막아야 한다.
- FR-INGEST-009 Must: 같은 submission ID에 다른 hash가 오면 충돌로 격리해야 한다.
- FR-INGEST-010 Must: 접수 완료 후 입력 snapshot은 불변이어야 한다.
- FR-INGEST-011 Must: 원본 template이나 project/case를 in-place로 update하지 않아야 한다.

### 11.3 Manifest

Manifest는 최소한 다음을 포함해야 한다.

~~~yaml
schema_version: 1
submission_id: rear-wing-r17-yaw0
name: Rear Wing R17, yaw 0
analysis_type: aero_fluent
profile: aero_downforce_prepared_v1@1.0.0

input_mode: prepared_case
inputs:
  case: rear_wing_r17_211.cas

parameters:
  velocity_mps: 22.22
  yaw_deg: 0

resources:
  cores: 6
  memory_gb: 20
  timeout_min: 240

integration:
  storage_policy: engineering_archive
  publish_policy: engineering_knowledge
  notify_policy: engineering_results
~~~

- FR-MANIFEST-001 Must: schema version과 unique submission ID를 가져야 한다.
- FR-MANIFEST-002 Must: profile ID와 정확한 profile version을 지정해야 한다.
- FR-MANIFEST-003 Must: 모든 수치 parameter는 단위를 포함하거나 profile의 고정 단위로 resolve되어야 한다.
- FR-MANIFEST-004 Must: 사용자는 profile이 선언한 parameter만 지정할 수 있다.
- FR-MANIFEST-005 Must: cores, RAM과 timeout은 profile 및 machine 범위 안이어야 한다.
- FR-MANIFEST-006 Must: job manifest에는 provider URL, SMTP credential, 임의 수신자, UNC root 또는 executable 경로를 넣지 않아야 한다.
- FR-MANIFEST-007 Must: integration은 승인된 논리 policy 이름만 지정해야 한다.

### 11.4 Profile 및 Template

- FR-PROFILE-001 Must: profile은 immutable version으로 관리해야 한다.
- FR-PROFILE-002 Must: profile ID, version, owner, 설명, 승인 상태와 지원 ANSYS release를 포함해야 한다.
- FR-PROFILE-003 Must: template artifact와 SHA-256을 포함해야 한다.
- FR-PROFILE-004 Must: parameter schema에 type, unit, min/max/enum/default와 필수 여부를 정의해야 한다.
- FR-PROFILE-005 Must: 허용 입력 형식과 geometry contract를 정의해야 한다.
- FR-PROFILE-006 Must: 필수 Named Selection, zone, body count와 좌표·단위 계약을 정의해야 한다.
- FR-PROFILE-007 Must: solver setting, mesh policy, 결과 recipe와 convergence policy를 정의해야 한다.
- FR-PROFILE-008 Must: Golden Case, 기준 결과, 허용 오차와 승인자를 연결해야 한다.
- FR-PROFILE-009 Must: profile 상태는 draft, active, disabled, deprecated를 지원해야 한다.
- FR-PROFILE-010 Must: 실행 중인 job은 resolved profile snapshot과 hash를 보존해야 한다.
- FR-PROFILE-011 Must: 새로운 profile 활성화 전 golden end-to-end test를 통과해야 한다.
- FR-PROFILE-012 Must: arbitrary raw script mode는 기본 비활성이어야 한다.
- FR-PROFILE-013 Must: 각 profile은 input mode를 prepared_case, geometry_to_case 또는 template_parameters 중 하나로 고정하고 manifest와의 불일치를 거부해야 한다.
- FR-PROFILE-014 Must: prepared_case mode는 해당 ANSYS 2021 R1 build에서 인증된 native project/case와 허용된 parameter만 입력으로 받고 STEP/STL 등 raw geometry를 거부해야 한다.
- FR-PROFILE-015 Must: geometry_to_case mode는 사용 ANSYS 2021 R1 preprocessing backend, 검증된 script와 필요한 추가 license feature를 명시해야 한다.
- FR-PROFILE-016 Must: geometry_to_case mode는 enclosure 생성, defeaturing, body/zone 재구성, boundary naming, mesh 생성·품질 검사와 solver 전환 절차 중 적용되는 항목을 profile 계약으로 가져야 한다.
- FR-PROFILE-017 Must: geometry 또는 topology 변경 후 기존 Named Selection, contact, load scope, Fluent zone이 보존된다고 가정하지 않아야 한다.
- FR-PROFILE-018 Must: profile 활성화 시 template 내부 계약을 licensed validation으로 검사하고 validation report와 template hash를 서명된 sidecar 또는 동등한 불변 record로 보존해야 한다.
- FR-PROFILE-019 Must: profile은 workflow, solver adapter, preprocessing adapter와 필요한 license feature를 고정하고 제출자는 raw executable이나 임의 ANSYS tool을 override하지 않아야 한다.
- FR-PROFILE-020 Must: UI는 사용자가 목적별 승인 profile을 선택할 때 실제 실행 도구, input mode, 허용 parameter와 예상 output을 함께 보여야 한다.

### 11.5 사전 검증

- FR-VALID-001 Must: 정확한 ANSYS 2021 R1 executable과 확인 가능한 file compatibility를 검사해야 한다.
- FR-VALID-002 Must: template hash, manifest schema, parameter 단위·범위·enum을 검사해야 한다.
- FR-VALID-003 Must: disk free space, workdir 쓰기, 경로 길이와 예상 scratch를 검사해야 한다.
- FR-VALID-004 Must: 필수 Named Selection, zone, report definition과 output recipe를 실제 solve 전에 확인해야 한다.
- FR-VALID-005 Must: 정적 검사로 확인할 수 없는 template 내부와 job-dependent scoping은 licensed adapter preflight에서 검사해야 한다.
- FR-VALID-006 Must: Fluent의 reference area, density, velocity는 0보다 커야 한다.
- FR-VALID-007 Must: drag/lift vector와 downforce sign convention이 유효해야 한다.
- FR-VALID-008 Must: schema, hash, path, 확장자, parameter와 정적으로 판별 가능한 호환성 실패는 solver license 사용 전에 REJECTED 처리해야 한다.
- FR-VALID-009 Must: 거부 결과는 안정된 machine-readable error code와 사용자 해결 안내를 제공해야 한다.
- FR-VALID-010 Must: license unavailable은 invalid input이 아니라 transient environment 상태로 분류해야 한다.
- FR-VALID-011 Must: licensed adapter preflight 실패는 PREFLIGHT_FAILED 또는 PROFILE_INCOMPATIBLE로 분류하고 정적 입력 거부와 구분해야 한다.
- FR-VALID-012 Must: licensed preflight가 실제 solve를 시작하지 않았음을 marker와 solver evidence로 증명해야 한다.
- FR-VALID-013 Must: 활성 profile의 서명된 template validation record가 현재 hash와 exact ANSYS build에 일치하지 않으면 실행을 차단해야 한다.

### 11.6 Queue 및 상태

Submission 상태는 Job 생성 전 접수 과정을 나타낸다.

~~~text
DISCOVERED
→ STAGING
→ VALIDATING
→ ACCEPTED

REJECTED
QUARANTINED
~~~

ACCEPTED 시 불변 input/profile/config snapshot에 결합된 Job을 생성한다. Job은 논리 요청이며 다음 상태를 가진다.

~~~text
QUEUED
→ ACTIVE
→ SUCCEEDED | COMPLETED_WITH_WARNINGS
  | FAILED_ENGINEERING_CHECK | FAILED_EXECUTION | CANCELLED

RETRY_WAIT
RECOVERY_REQUIRED
~~~

Attempt는 Job을 실제로 실행한 한 번의 시도이며 process, lease와 workdir 상태를 가진다.

~~~text
CLAIMED
→ PREFLIGHT
→ RUNNING
→ POSTPROCESSING
→ PACKAGING
→ ATTEMPT_SUCCEEDED

PREFLIGHT_FAILED
PROFILE_INCOMPATIBLE
INTERRUPTED
ATTEMPT_FAILED
CANCELLING
ATTEMPT_CANCELLED
~~~

Cancel Command는 별도 aggregate로 다음 상태를 가진다.

~~~text
REQUESTED
→ ACCEPTED
→ COMPLETED

FAILED
~~~

Job은 cancel 요청 중에도 QUEUED 또는 ACTIVE를 유지하고, cancel command와 attempt cleanup이 성공한 뒤 terminal compare-and-set이 성공할 때만 CANCELLED가 된다. 각 Job terminal은 5.3에 정의된 종류별 result package, diagnostic package 또는 최소 failure/cancel record를 원자적으로 commit한 뒤 네 outcome 축을 평가해 확정한다.

외부 operation은 다음 독립 상태 머신을 사용한다.

~~~text
PENDING
→ CLAIMED
→ EXECUTING
→ SUCCEEDED

RETRY_WAIT
PERMANENT_FAILURE
POLICY_REVOKED
UNKNOWN
DEAD_LETTER
~~~

선택된 route들의 상태는 별도 product rollup인 PENDING, READY 또는 DEGRADED로 계산할 수 있으나 analysis terminal status는 변경하지 않는다.

- FR-QUEUE-001 Must: SQLite가 queue 상태의 유일한 source of truth여야 한다.
- FR-QUEUE-002 Must: 상태 전이와 event 저장을 같은 transaction에서 수행해야 한다.
- FR-QUEUE-003 Must: 기본 heavy solver concurrency는 1이어야 한다.
- FR-QUEUE-004 Must: priority와 FIFO 순서를 지원해야 한다.
- FR-QUEUE-005 Must: queue pause/resume, job cancel과 승인된 retry를 지원해야 한다.
- FR-QUEUE-006 Must: worker claim은 transaction, lease와 heartbeat를 사용해야 한다.
- FR-QUEUE-007 Must: PID뿐 아니라 process creation time, command와 workdir를 기록해야 한다.
- FR-QUEUE-008 Must: attempt마다 새 workdir와 불변 input snapshot을 사용해야 한다.
- FR-QUEUE-009 Must: retry가 기존 attempt 결과를 덮어쓰지 않아야 한다.
- FR-QUEUE-010 Must: 자동 retry는 원 Job의 동일한 resolved input/profile/config snapshot으로 새 attempt를 생성해야 한다.
- FR-QUEUE-011 Must: analysis terminal status와 storage/publication/notification operation 상태를 별도 필드와 테이블로 관리해야 한다.
- FR-QUEUE-012 Must: 외부 integration의 성공·실패·정책 철회가 어떤 analysis terminal status도 변경하지 않아야 한다.
- FR-QUEUE-013 Must: 최신 profile 또는 변경된 입력·config snapshot으로 다시 실행하는 동작은 retry가 아니라 새 Job 또는 명시적 Job revision이어야 한다.
- FR-QUEUE-014 Must: checkpoint resume도 새 attempt ID와 source attempt/checkpoint reference를 생성하고 원 attempt는 불변으로 보존해야 한다.
- FR-QUEUE-015 Must: cancel과 natural completion 경합은 state version compare-and-set으로 처리하며 final result commit 전에 cleanup과 cancel terminal-record commit이 먼저 성공하면 cancel이 승리하고, final result commit이 먼저 성공하면 completion이 승리해야 한다.
- FR-QUEUE-016 Must: submission, job, attempt, cancel command, outcome 축과 integration operation 상태를 서로 다른 필드 또는 테이블로 저장해야 한다.
- FR-QUEUE-017 Must: Job terminal event와 integration operation 생성을 같은 DB transaction의 transactional outbox로 확정해야 한다.
- FR-QUEUE-018 Must: terminal evidence record를 commit할 수 없는 disk/DB 장애에서는 Job을 RECOVERY_REQUIRED로 두고 거짓 terminal event나 외부 notification을 만들지 않아야 한다.

### 11.7 자원·전원·라이선스 관리

- FR-RESOURCE-001 Must: core, RAM, disk, solver/license feature를 자원 token으로 관리해야 한다.
- FR-RESOURCE-002 Must: OS용 CPU core와 RAM reserve를 남겨야 한다.
- FR-RESOURCE-003 Must: local scratch disk 여유가 부족하면 solve를 시작하지 않아야 한다.
- FR-RESOURCE-004 Should: AC 전원에서만 새 heavy job을 시작하는 정책을 지원해야 한다.
- FR-RESOURCE-005 Should: solve 중 Windows sleep 방지를 지원해야 한다.
- FR-RESOURCE-006 Must: license preflight와 실제 solver checkout 거부를 모두 처리해야 한다.
- FR-RESOURCE-007 Must: 라이선스 대기는 configurable backoff와 만료시간을 가져야 한다.
- FR-RESOURCE-008 Should: 장시간 resource pressure 또는 thermal warning을 표시해야 한다.

### 11.8 Solver Adapter 공통 계약

각 adapter는 다음 기능을 제공해야 한다.

~~~text
validate
prepare
launch
monitor
request_cancel
force_terminate
classify_exit
postprocess
resume_capability
cleanup
~~~

- FR-SOLVER-001 Must: 모든 solver 실행은 독립 local ASCII workdir에서 수행해야 한다.
- FR-SOLVER-002 Must: modal dialog와 사용자 입력을 요구하지 않는 batch mode여야 한다.
- FR-SOLVER-003 Must: child process 전체를 Windows Job Object 또는 동등한 방법으로 추적해야 한다.
- FR-SOLVER-004 Must: timeout 시 graceful cancel 후 bounded wait, 마지막에 process-tree 종료를 수행해야 한다.
- FR-SOLVER-005 Must: exit code만으로 성공을 판정하지 않아야 한다.
- FR-SOLVER-006 Must: completion marker, mandatory artifact, finite metric, error scan과 convergence를 함께 확인해야 한다.
- FR-SOLVER-007 Must: solver command와 환경 metadata를 비밀정보 없이 기록해야 한다.
- FR-SOLVER-008 Must: 지원하지 않는 resume를 추측하여 실행하지 않아야 한다.
- FR-SOLVER-009 Must: adapter/profile은 survives_agent_crash, reattach_supported, checkpoint_supported, graceful_cancel과 clean_retry_safe capability를 각각 선언해야 한다.
- FR-SOLVER-010 Must: Windows Job Object의 kill-on-close 사용 여부와 process 생존 정책을 attempt에 기록하고 reattach 요구사항과 모순되지 않게 구성해야 한다.
- FR-SOLVER-011 Must: 신뢰성 있게 golden-test된 durable supervisor/reattach가 없으면 기본 정책은 agent 종료 시 child tree 종료 또는 startup orphan 검증 후 종료여야 한다.
- FR-SOLVER-012 Must: PC reboot 후 process reattach를 지원한다고 표시하지 않아야 하며 검증된 checkpoint 또는 새 attempt만 허용해야 한다.
- FR-SOLVER-013 Must: native project/case가 참조하는 external script, extension, dynamic library와 executable hook은 profile-owned hash allowlist로 검증하고 user-controlled absolute/network path에서 로드하지 않아야 한다.

### 11.9 Mechanical / Workbench

기본 실행 패턴:

~~~powershell
RunWB2.exe -B -R job.wbjn
~~~

- FR-MECH-001 Must: Static Structural golden project를 job별로 복제해야 한다.
- FR-MECH-002 Must: Workbench journal은 project open과 schematic 제어뿐 아니라 Mechanical 2021 R1 native scripting surface의 SendCommand/ACT 또는 사전 구성된 parameter/result object를 통해 parameter 적용, solve, result evaluate/export를 수행하고 save/exit해야 한다.
- FR-MECH-003 Must: materials, contacts, support, load case와 mesh control은 profile에 정의되어야 한다.
- FR-MECH-004 Must: topology 변경 시 필수 Named Selection이 이름만 존재하는지에 그치지 않고 nonempty인지, entity type과 body/entity count가 profile 범위인지 확인해야 한다.
- FR-MECH-005 Must: Equivalent von Mises stress, total deformation과 reactions를 지원해야 한다.
- FR-MECH-006 Must: safety factor는 항복강도와 판정 기준이 있을 때만 생성해야 한다.
- FR-MECH-007 Must: nonlinear 해석은 모든 required load step과 convergence를 확인해야 한다.
- FR-MECH-008 Must: 결과 location, load case/time, unit와 material reference를 기록해야 한다.
- FR-MECH-009 Must: 검증되지 않은 PyMechanical 버전에 의존하지 않고 2021 R1 Workbench journal과 해당 release에서 검증된 Mechanical scripting/ACT를 사용해야 한다.
- FR-MECH-010 Must: Mechanical script engine, language, encoding과 API call은 exact 2021 R1 build에서 golden test로 검증해야 한다.
- FR-MECH-011 Must: raw geometry 교체 profile은 STEP 입력만으로 Named Selection, contact, support, load와 result scoping이 유지된다고 가정하지 않아야 한다.
- FR-MECH-012 Must: licensed preflight는 모든 required body의 material 할당, suppressed/unassigned body 부재, support/load/result object scoping과 contact region의 유효성을 검사해야 한다.
- FR-MECH-013 Must: licensed preflight는 예상하지 않은 open contact와 invalid contact를 검출하고 profile이 허용하지 않으면 solve를 차단해야 한다.
- FR-MECH-014 Must: mesh 생성 후 node/element/body 통계와 profile의 최소·최대·품질 계약을 검사한 뒤에만 solve로 진행해야 한다.
- FR-MECH-015 Must: ACT extension, Mechanical script와 external command는 profile-owned version/hash allowlist에 있는 것만 로드하고 project에 삽입된 임의 extension/hook을 거부해야 한다.

### 11.10 MAPDL

기본 실행 패턴:

~~~powershell
ANSYS211.exe -b -i input.dat -o output.out -dir WORKDIR -j UNIQUE_JOB -np N
~~~

- FR-MAPDL-001 Must: 승인된 parameterized master deck만 사용해야 한다.
- FR-MAPDL-002 Must: 사용자 제출 arbitrary APDL은 기본 금지해야 한다.
- FR-MAPDL-003 Must: batch prompt를 억제하고 unique jobname을 사용해야 한다.
- FR-MAPDL-004 Must: exit code와 ERR/OUT 내용을 함께 검사해야 한다.
- FR-MAPDL-005 Must: 결과 추출은 승인된 GET/VGET/VWRITE recipe 또는 검증된 postprocessor를 사용해야 한다.
- FR-MAPDL-006 Should: nonlinear/transient profile에서 load step, substep과 NLHIST 기반 진행 상태를 지원해야 한다.
- FR-MAPDL-007 Must: 기본 adapter는 native batch여야 하며 PyMAPDL은 별도 검증된 capability로만 허용해야 한다.
- FR-MAPDL-008 Must: MAPDL .err/.out의 license, abort, fatal과 unconverged marker를 안정된 error code로 분류해야 한다.

### 11.11 Fluent

기본 실행 패턴:

~~~powershell
fluent.exe 3ddp -g -wait -tN -i run.jou
~~~

기본 계수 정의는 profile이 명시한 기준값을 사용한다.

~~~text
Cd = Drag / (0.5 × density × velocity² × reference area)
Downforce = profile의 lift 축과 부호 계약으로 계산한 하향 힘
~~~

- FR-FLUENT-001 Must: journal과 case는 Fluent 2021 R1에서 직접 작성·검증되어야 한다.
- FR-FLUENT-002 Must: journal에 21.1 TUI version, overwrite policy, hide questions, exit-on-error, transcript, 명시적 save와 exit가 있어야 한다.
- FR-FLUENT-003 Must: profile은 authoritative raw force 또는 force-coefficient report definition과 그로부터 파생되는 drag_N, lift_N, downforce_N, Cd와 Cl 계산 계약을 정의해야 하며 모든 값을 독립적인 진실로 간주하지 않아야 한다.
- FR-FLUENT-004 Must: force 대상 wall zone을 명시해야 한다.
- FR-FLUENT-005 Must: reference density, velocity, area, length, pressure, named coordinate system, drag axis, lift axis와 downforce sign을 결과에 포함해야 한다.
- FR-FLUENT-006 Must: downforce의 authoritative 정의를 lift force의 음수 또는 명시적 downward-vector report 중 하나로 profile에 고정하고 redundant 값이 있으면 허용 오차 내에서 reconciliation해야 한다.
- FR-FLUENT-007 Must: residual만으로 수렴을 판정하지 않아야 한다.
- FR-FLUENT-008 Must: equation residual, mass imbalance와 Cd/downforce monitor 안정성 window를 함께 검사해야 한다.
- FR-FLUENT-009 Must: drag, lift/downforce, Cd/Cl, optional Cm, iterations, mass balance와 mesh quality를 출력해야 한다.
- FR-FLUENT-010 Must: last iteration 값과 안정성 window 평균·표준편차·slope를 구분해 보존해야 한다.
- FR-FLUENT-011 Must: PyFluent를 사용하지 않고 native journal/TUI를 사용해야 한다.
- FR-FLUENT-012 Should: solve를 iteration chunk로 나누고 chunk 사이 cancel marker와 checkpoint를 확인하는 profile hook을 지원해야 한다.
- FR-FLUENT-013 Should: contour image는 CFD-Post 또는 graphics-capable 별도 후처리로 생성해야 한다.
- FR-FLUENT-014 Must: profile은 steady/transient, turbulence model, wall treatment, 유체 물성과 operating condition을 정의해야 한다.
- FR-FLUENT-015 Must: profile은 domain/boundary, moving ground, rotating wheel, mesh quality와 y-plus 목표의 적용 여부를 정의해야 한다.
- FR-FLUENT-016 Must: Cm을 출력하는 profile은 reference length와 moment center를 정의해야 한다.
- FR-FLUENT-017 Must: geometry_to_case형과 prepared_case형 입력을 구분하고 input mode 불일치와 지원하지 않는 topology change를 거부해야 한다.
- FR-FLUENT-018 Must: prepared_case profile은 인증된 2021 R1 .cas/.dat 또는 profile-owned template만 허용하고 raw STEP/STL을 solver journal 입력으로 받지 않아야 한다.
- FR-FLUENT-019 Must: geometry_to_case profile은 SpaceClaim, Workbench 또는 Fluent Meshing 등 exact 2021 R1 preprocessing backend와 versioned script를 지정해야 한다.
- FR-FLUENT-020 Must: geometry_to_case preflight는 enclosure, defeaturing, boundary zone 재구성, mesh 생성/check와 solver mode 전환의 성공 evidence를 남겨야 한다.
- FR-FLUENT-021 Must: drag/lift 방향 벡터는 named coordinate system에서 정규화되고 서로 직교해야 한다.
- FR-FLUENT-022 Must: yaw parameter는 inlet 방향과 drag/lift 벡터에 동일한 deterministic transform으로 적용되어야 하며 변환 전후 벡터를 결과에 기록해야 한다.
- FR-FLUENT-023 Must: Cd/Cl reference value는 양수 검사뿐 아니라 resolved inlet/operating condition과 일치하는지 licensed preflight 또는 solver evidence로 확인해야 한다.
- FR-FLUENT-024 Must: TUI command error, journal 조기 종료, license exit와 solver fatal을 transcript 및 marker로 구분해야 한다.
- FR-FLUENT-025 Must: journal precision인 2d/3d/2ddp/3ddp가 case와 profile 계약에 일치해야 한다.
- FR-FLUENT-026 Must: UDF source/compiled library, Scheme hook와 external command는 profile-owned version/hash allowlist에 있는 것만 허용하고 job package의 임의 binary/code를 로드하지 않아야 한다.
- FR-FLUENT-027 Must: prepared case의 loaded library와 hook reference는 licensed preflight에서 열거하고 unresolved, user-controlled 또는 allowlist 밖 reference가 있으면 solve를 차단해야 한다.

### 11.12 진행률

공통 stage:

~~~text
VALIDATING
STAGING
PREPROCESSING
MESHING
SOLVING
POSTPROCESSING
PACKAGING
INTEGRATING
~~~

- FR-PROGRESS-001 Must: progress mode는 determinate, indeterminate 또는 stage여야 한다.
- FR-PROGRESS-002 Must: 근거가 없는 백분율을 표시하지 않아야 한다.
- FR-PROGRESS-003 Must: process heartbeat와 solver activity timestamp를 구분해야 한다.
- FR-PROGRESS-004 Must: event sequence를 저장해 중복·역순 event를 처리해야 한다.
- FR-PROGRESS-005 Must: Workbench는 generated script의 explicit stage marker를 우선해야 한다.
- FR-PROGRESS-006 Should: MAPDL은 가능한 경우 load step/substep을 표시해야 한다.
- FR-PROGRESS-007 Must: Fluent fixed iteration/time-step은 current/target을 표시해야 한다.
- FR-PROGRESS-008 Must: convergence-controlled solve는 iteration과 monitor 상태만 표시하고 임의 total을 만들지 않아야 한다.
- FR-PROGRESS-009 Must: 고빈도 progress는 local UI에만 기록하고 이메일에는 milestone/digest 정책을 적용해야 한다.

### 11.13 공학적 완료·수렴 판정

공통 convergence status:

~~~text
CONVERGED
NOT_CONVERGED
UNKNOWN
~~~

- FR-ENG-001 Must: 프로세스 종료 성공과 공학적 완료 상태를 구분해야 한다.
- FR-ENG-002 Must: 모든 최종 수치는 finite여야 하며 NaN/Inf를 허용하지 않아야 한다.
- FR-ENG-003 Must: 모든 metric은 unit와 source를 가져야 한다.
- FR-ENG-004 Must: NOT_CONVERGED를 일반 성공 메일처럼 표시하지 않아야 한다.
- FR-ENG-005 Must: profile 정책에 따라 COMPLETED_WITH_WARNINGS 또는 FAILED_ENGINEERING_CHECK로 변환해야 한다.
- FR-ENG-006 Must: convergence criteria와 observed evidence를 report에 포함해야 한다.
- FR-ENG-007 Must: automation execution success와 engineering model validation을 UI와 보고서에서 구분해야 한다.
- FR-ENG-008 Must: profile 승인자와 golden baseline 정보를 표시해야 한다.

### 11.14 취소

- FR-CANCEL-001 Must: cancel command의 REQUESTED, ACCEPTED, COMPLETED, FAILED를 Job 및 Attempt 상태와 분리해야 한다.
- FR-CANCEL-002 Must: queued job은 즉시 취소하고 solver를 실행하지 않아야 한다.
- FR-CANCEL-003 Must: running job은 profile이 graceful_cancel capability를 선언하고 exact build golden test를 통과한 경우에만 adapter별 graceful stop을 먼저 시도해야 한다.
- FR-CANCEL-004 Must: grace timeout 후 exact process tree를 종료해야 한다.
- FR-CANCEL-005 Must: cancel은 idempotent여야 한다.
- FR-CANCEL-006 Must: actor, 시간, 사유와 state version을 audit해야 한다.
- FR-CANCEL-007 Must: 취소된 attempt의 부분 결과는 final engineering result로 표시하지 않아야 한다.
- FR-CANCEL-008 Must: checkpoint_on_cancel은 profile이 해당 solver/build에서 구현·검증한 경우에만 사용하고, 그렇지 않으면 partial=true로 supervised process-tree termination해야 한다.
- FR-CANCEL-009 Must: MAPDL Jobname.ABT 기반 graceful abort는 nonlinear 또는 full-transient batch profile에서만 capability로 선언하고 ordinary linear solve에서는 지원된다고 표시하지 않아야 한다.
- FR-CANCEL-010 Must: Fluent checkpoint cancel은 journal이 iteration/time-step chunk 경계에서 case/data 저장과 cancel marker 검사를 구현한 profile에서만 허용해야 한다.
- FR-CANCEL-011 Must: Workbench cancel은 Mechanical 및 solver child process tree와 lock 정리를 검증해야 한다.
- FR-CANCEL-012 Must: queued cancel은 attempt 없이 cancel command를 COMPLETED로 만들고 Job terminal compare-and-set을 통해 CANCELLED로 전이해야 한다.
- FR-CANCEL-013 Must: running cancel은 Attempt만 CANCELLING에서 ATTEMPT_CANCELLED로 전이하고, cancel command 완료 후 Job terminal compare-and-set을 별도로 수행해야 한다.

### 11.15 재시도

- FR-RETRY-001 Must: retry는 새로운 attempt ID와 새 workdir를 생성해야 한다.
- FR-RETRY-002 Must: solver 자동 retry는 의미 있는 solve 진행 전의 license-server 연결·checkout 실패, 명시적으로 분류된 transient process launch와 일시적 local file lock으로 제한해야 한다.
- FR-RETRY-003 Must: invalid manifest, missing selection, mesh quality failure, divergence와 nonconvergence는 동일 입력으로 자동 반복하지 않아야 한다.
- FR-RETRY-004 Must: retry는 exponential backoff와 jitter, 최대 시도와 만료시간을 가져야 한다.
- FR-RETRY-005 Must: checkpoint resume와 clean retry를 서로 다른 action으로 취급해야 한다.
- FR-RETRY-006 Must: NAS, Notion, SMTP 등 provider network 실패는 해당 outbox operation만 retry하고 solver attempt를 다시 실행하지 않아야 한다.
- FR-RETRY-007 Must: mid-solve license loss, process crash와 machine reboot는 profile이 clean retry safe를 선언하거나 검증된 checkpoint가 있을 때만 자동 재개·재시도해야 한다.
- FR-RETRY-008 Must: checkpoint는 hash, solver/build, profile, input snapshot과 restart compatibility를 검증하고 손상·불일치 시 자동 resume하지 않아야 한다.

### 11.16 결과 및 Artifact

각 attempt의 기본 산출물:

~~~text
manifest.original
manifest.resolved
validation-report.json
events.jsonl
metrics.json
metrics.csv
convergence.csv
summary.html
summary.pdf
preview/*.png
solver/stdout.log
solver/stderr.log
solver/transcript
generated-script
hashes.json
native-results/*
terminal-record.json
~~~

- FR-ARTIFACT-001 Must: artifact descriptor에 ID, role, MIME, size, SHA-256, relative URI, producer, retention class와 sensitivity를 저장해야 한다.
- FR-ARTIFACT-002 Must: mandatory와 optional artifact를 profile에 구분해야 한다.
- FR-ARTIFACT-003 Must: mandatory artifact가 없거나 checksum이 불일치하면 package를 완료하지 않아야 한다.
- FR-ARTIFACT-004 Must: 완료 파일은 temp name으로 작성한 뒤 검증 후 atomic rename해야 한다.
- FR-ARTIFACT-005 Must: COMPLETE marker를 마지막에 생성해야 한다.
- FR-ARTIFACT-006 Must: native result와 restart file을 summary artifact와 구분해야 한다.
- FR-ARTIFACT-007 Must: local absolute path, 사용자명, license server와 secret을 외부 report에서 제거해야 한다.
- FR-ARTIFACT-008 Must: failure/cancel terminal record는 full result packaging과 독립된 최소 writer로 job/attempt, outcome, error/cancel reason, evidence index, timestamp와 hash를 원자적으로 확정해야 한다.
- FR-ARTIFACT-009 Must: mandatory result packaging 자체가 실패해도 최소 terminal record를 만들 수 없으면 Job terminal로 추측 전이하지 않고 recovery-required 상태로 유지해야 한다.

### 11.17 NAS / SMB

- FR-NAS-001 Must: mapped drive letter가 아닌 UNC path를 사용해야 한다.
- FR-NAS-002 Must: SQLite와 ANSYS work/scratch를 NAS에서 실행하지 않아야 한다.
- FR-NAS-003 Must: NAS 입력은 local part file로 복사하고 size/hash 검증 후 immutable cache로 확정해야 한다.
- FR-NAS-004 Must: NAS 결과 업로드는 temp write 후 atomic rename을 사용해야 한다.
- FR-NAS-005 Must: atomic rename 보장이 없으면 checksum manifest와 COMPLETE marker를 마지막에 써야 한다.
- FR-NAS-006 Must: NAS 연결 단절 시 local result와 operation을 보존하고 재연결 후 재개해야 한다.
- FR-NAS-007 Must: NAS offline 상태를 remote deletion으로 해석하지 않아야 한다.
- FR-NAS-008 Must: source read-only와 result write 권한을 분리해야 한다.
- FR-NAS-009 Must: 경로 prefix, 파일 형식, 크기와 민감도 allowlist를 적용해야 한다.
- FR-NAS-010 Must: 외부 수신자에게 UNC path를 이메일로 보내지 않아야 한다.
- FR-NAS-011 Should: NAS가 제공하는 인증된 HTTPS share link capability를 선택적으로 지원해야 한다.
- FR-NAS-012 Must: 자동 삭제는 명시된 retention 정책과 권한이 있을 때만 수행해야 한다.
- FR-NAS-013 Must: NAS upload가 required_for_product_rollup이면 checksum/COMPLETE 검증 뒤에만 archival_complete로 표시해야 한다.
- FR-NAS-014 Must: 장기 보존 대상으로 지정된 local 대형 artifact는 NAS archival_complete 이전에 purge하지 않아야 하며 purge 후에도 manifest, checksum, provenance와 remote reference를 보존해야 한다.

### 11.18 Notion 및 지식관리

- FR-NOTION-001 Must: Notion integration token과 대상 page/data source ID를 config와 SecretStore로 주입해야 한다.
- FR-NOTION-002 Must: allowlist된 page/data source만 읽고 써야 한다.
- FR-NOTION-003 Must: page를 Markdown 또는 중립 document model로 읽고 쓸 수 있어야 한다.
- FR-NOTION-004 Must: stable identity는 local job ID 또는 provider_instance와 canonical external source ID의 조합으로 정의하고 content hash를 identity로 사용하지 않아야 한다.
- FR-NOTION-005 Must: source version과 content hash를 idempotent version key로 사용하여 동일 version이 중복 page나 block을 생성하지 않아야 한다.
- FR-NOTION-006 Must: Notion page ID, URL, remote version 또는 concurrency token, last published hash와 origin marker를 local DB에 저장해야 한다.
- FR-NOTION-007 Must: Notion 장애나 rate limit은 publication outbox에서만 재시도해야 한다.
- FR-NOTION-008 Must: 사람이 편집하는 영역과 automation-managed 영역을 분리해야 한다.
- FR-NOTION-009 Must: publish 직전 remote version을 검사하는 optimistic concurrency를 사용해야 한다.
- FR-NOTION-010 Must: 기본 conflict policy는 fail-and-review여야 한다.
- FR-NOTION-011 Should: fork-new-page, append-new-version, overwrite-managed-region 정책을 지원해야 한다.
- FR-NOTION-012 Must: 전체 page blind overwrite를 금지해야 한다.
- FR-NOTION-013 Must: remote 삭제는 tombstone/archive로 처리하고 자동 영구 삭제하지 않아야 한다.
- FR-NOTION-014 Must: 원문 version이 바뀌면 기존 분석·index·publication을 stale로 표시해야 한다.
- FR-NOTION-015 Must: Notion에는 KPI, 요약, 작은 plot/report와 NAS link를 중심으로 발행해야 한다.
- FR-NOTION-016 Must: 대형 native ANSYS result를 기본 업로드하지 않아야 한다.
- FR-NOTION-017 Must: API version을 provider config에 명시적으로 고정해야 한다.
- FR-NOTION-018 Must: local-only 운영에서는 polling과 periodic full reconciliation을 지원해야 한다.
- FR-NOTION-019 Could: 공개 HTTPS relay가 있을 때 webhook을 가속 수단으로 사용할 수 있다.
- FR-NOTION-020 Could: Analysis Request data source를 job 제출 채널로 사용할 수 있으나 profile과 parameter allowlist를 동일하게 적용해야 한다.
- FR-NOTION-021 Must: 모든 list/search/block/property read는 pagination cursor를 끝까지 순회하고 page 수와 item 수를 기록해야 한다.
- FR-NOTION-022 Must: block, property와 본문 write는 현재 API request limit에 맞게 chunking하고 각 성공 chunk와 resume cursor를 영속화해야 한다.
- FR-NOTION-023 Must: 중간 chunk 성공 뒤 429, timeout 또는 agent crash가 발생하면 완료 chunk를 중복 생성하지 않고 미완료 chunk부터 idempotent resume하며 내용을 조용히 잘라내지 않아야 한다.
- FR-NOTION-024 Must: provider가 native version/ETag를 제공하지 않으면 adapter-derived concurrency token을 사용하고 conflict 시 base, generated와 remote snapshot을 모두 보존해야 한다.
- FR-NOTION-025 Must: automation origin marker와 published hash를 사용하여 self-publication이 새 inbound 변경으로 재수집되는 loop를 차단해야 한다.
- FR-NOTION-026 Must: page/property/block 한도 때문에 전체 내용을 발행할 수 없으면 성공으로 축소하지 않고 명시적 partial 또는 permanent failure와 대체 artifact link를 기록해야 한다.
- FR-NOTION-027 Must: remote publication은 PUBLISHING 또는 PARTIAL 상태로 시작하고 전체 chunk count, ordered content hash와 managed property를 검증한 뒤 마지막 commit barrier에서만 PUBLISHED와 publication revision/hash를 확정해야 한다.
- FR-NOTION-028 Must: PUBLISHED 전에는 canonical page pointer, publication receipt와 notification용 Notion link를 새 revision으로 갱신하지 않아야 한다.
- FR-NOTION-029 Must: penultimate chunk 이후 crash에서도 기존 page는 PARTIAL로 식별되고 resume 완료 뒤 단 한 번만 PUBLISHED transition과 receipt를 만들어야 한다.

### 11.19 자료 Parsing·분석·검색

- FR-DOC-001 Must: PDF, DOCX, PPTX, XLSX, TXT, Markdown, CSV와 HTML parser capability를 제공해야 한다.
- FR-DOC-002 Should: 스캔 PDF와 이미지 OCR을 선택적 parser로 지원해야 한다.
- FR-DOC-003 Must: parser ID, version, 입력 hash와 결과 hash를 기록해야 한다.
- FR-DOC-004 Must: document, document version, chunk와 source locator를 구분해야 한다.
- FR-DOC-005 Must: 기본 full-text 검색은 local SQLite FTS 또는 동등한 local index로 제공해야 한다.
- FR-DOC-006 Could: semantic/vector index를 SearchIndexProvider로 추가할 수 있어야 한다.
- FR-DOC-007 Must: ContentAnalyzer는 특정 LLM 또는 model provider에 종속되지 않는 port여야 한다.
- FR-DOC-008 Must: 분석 profile에 summary, classification, tags, requirements, decisions, risks, action items 등 수행 항목을 정의해야 한다.
- FR-DOC-009 Must: model/version, analyzer version, prompt/profile hash와 입력 document version을 기록해야 한다.
- FR-DOC-010 Must: 요약과 주장에 source provider, external ID, version/hash, section/page/block locator를 연결해야 한다.
- FR-DOC-011 Must: 민감 문서가 외부 ContentAnalyzer, storage, knowledge, notification provider로 전달되기 전에 단계별 egress policy와 redaction을 검사해야 한다.
- FR-DOC-012 Must: 분석 실패가 원본 파일 상태를 변경하지 않아야 한다.
- FR-DOC-013 Must: PDF는 page별 text와 table locator, DOCX는 paragraph/table/header, PPTX는 slide text/table/speaker note, XLSX는 sheet/cell displayed value와 formula provenance를 지원 범위로 선언해야 한다.
- FR-DOC-014 Must: TXT/Markdown/CSV는 encoding과 구조를 보존하고 HTML은 script를 실행하지 않은 visible text/table만 추출해야 한다.
- FR-DOC-015 Must: macro, embedded executable/object와 external link를 실행하지 않아야 하며 encrypted/password-protected 또는 지원하지 않는 요소는 명시적 parser status로 보고해야 한다.
- FR-DOC-016 Must: 각 Must 형식은 대표 text, table, Unicode, 빈 문서와 손상 문서를 포함하는 golden parser acceptance set을 가져야 한다.
- FR-DOC-017 Must: parser adapter는 text, table, notes, formula, OCR, encrypted와 embedded-object capability를 선언해야 한다.

### 11.20 범용 SMTP 이메일

기본 알림 경로는 Bot/Message API가 아니라 범용 SMTP다. NAVER WORKS를 사용할 때도 메일 relay provider로 취급하며, 수신자는 NAVER WORKS 계정 보유 여부와 관계없이 승인된 이메일 주소가 될 수 있다.

- FR-MAIL-001 Must: 유효한 내부·외부 이메일 주소를 수신자로 지원해야 한다.
- FR-MAIL-002 Must: SMTP host, port, security mode, auth mode, header From, display name, reply-to와 envelope-from을 설정할 수 있어야 한다.
- FR-MAIL-003 Must: 비밀번호, app password와 OAuth token은 credential reference로만 설정해야 한다.
- FR-MAIL-004 Must: HTML과 plain text를 함께 보내는 multipart email을 생성해야 한다.
- FR-MAIL-005 Must: Message-ID, Date, Auto-Submitted와 X-Job-ID를 포함해야 한다.
- FR-MAIL-006 Must: 수신자 주소를 정규화·중복 제거해야 한다.
- FR-MAIL-007 Must: job manifest에는 임의 수신자를 쓰지 않고 승인된 recipient group을 사용해야 한다.
- FR-MAIL-008 Must: SMTP 4xx, 5xx, timeout과 authentication failure를 다른 정책으로 분류해야 한다.
- FR-MAIL-009 Must: SMTP 4xx와 network timeout은 outbox에서 retry해야 한다.
- FR-MAIL-010 Must: SMTP 5xx와 invalid recipient는 permanent failure 또는 관리자 정책으로 처리해야 한다.
- FR-MAIL-011 Must: relay가 메시지를 수락한 상태를 accepted_by_relay로 표현하고 실제 수신 완료로 표시하지 않아야 한다.
- FR-MAIL-012 Must: event와 idempotency key로 중복 의도를 차단해야 한다.
- FR-MAIL-013 Must: provider가 exactly-once를 보장하지 않을 때 delivery semantics를 at-least-once 또는 UNKNOWN으로 명시해야 한다.
- FR-MAIL-014 Must: 첨부 MIME allowlist와 총 크기 제한을 적용해야 한다.
- FR-MAIL-015 Must: 기본 첨부는 PDF, PNG/JPEG와 CSV로 제한해야 한다.
- FR-MAIL-016 Must: RST, CAS/DAT, CAD, executable, script와 암호화 archive 첨부를 차단해야 한다.
- FR-MAIL-017 Must: 첨부 한도를 넘으면 안전한 HTTPS link 또는 요약-only 방식으로 전환해야 한다.
- FR-MAIL-018 Must: Notion link는 수신자 접근 가능성이 확인된 policy에서만 포함해야 한다.
- FR-MAIL-019 Must: 외부 수신자에게 UNC path와 restricted artifact를 보내지 않아야 한다.
- FR-MAIL-020 Should: 테스트 메일과 SMTP health check를 제공해야 한다.
- FR-MAIL-021 Must: recipient group별 전송 방식을 to, bcc 또는 individual-delivery 중에서 설정할 수 있어야 한다.
- FR-MAIL-022 Must: 외부 수신자 주소가 서로 노출되지 않아야 하는 policy에서는 BCC 또는 individual-delivery를 사용해야 한다.
- FR-MAIL-023 Should: quiet hours, event throttle과 반복 warning digest를 설정할 수 있어야 한다.
- FR-MAIL-024 Must: open tracking pixel과 외부 추적 기능은 기본 비활성이어야 한다.
- FR-MAIL-025 Must: security mode는 implicit_tls, starttls_required와 development 전용 plaintext를 구분하고 production에서 plaintext를 금지해야 한다.
- FR-MAIL-026 Must: starttls_required에서 STARTTLS 미지원, downgrade 또는 handshake 실패 시 fail closed하고 TLS 확립 전에 AUTH command와 message body를 전송하지 않아야 한다.
- FR-MAIL-027 Must: auth mode는 none, password_or_app_password와 oauth2 capability를 지원하며 secret/token은 operation 실행 시 SecretStore에서 resolve해야 한다.
- FR-MAIL-028 Must: 표시용 header From과 bounce·반송 처리를 위한 SMTP envelope-from을 분리하고 relay 정책과 일치하게 검증해야 한다.
- FR-MAIL-029 Must: TLS certificate hostname과 trust chain을 검증하고 production insecure override를 허용하지 않아야 한다.
- FR-MAIL-030 Must: 기본 이메일 발송은 수신자의 NAVER WORKS tenant 가입이나 Bot 설치를 요구하지 않아야 한다.
- FR-MAIL-031 Must: batched SMTP transaction은 각 envelope recipient별 RCPT 응답, accepted_by_relay, transient, permanent와 UNKNOWN 상태를 영속화해야 한다.
- FR-MAIL-032 Must: 혼합 RCPT 결과에서는 transient recipient만 별도 retry하고 이미 accepted_by_relay 또는 permanent로 확정된 주소에 같은 notification을 재전송하지 않아야 한다.
- FR-MAIL-033 Must: relay가 DATA를 수락한 직후 local receipt commit 전 crash가 발생하면 영향 recipient를 UNKNOWN으로 두고 blind resend하지 않으며 운영 policy에 따른 reconciliation 또는 수동 결정을 요구해야 한다.

### 11.21 알림 문서 및 이메일 렌더링

필수 이벤트:

- Job 접수
- Validation 거부
- 해석 시작
- 해석 완료
- 공학적 검증 경고 또는 비수렴
- 해석 실패
- 취소 완료
- 라이선스 장기 대기
- NAS 복제 실패 및 복구
- Notion 발행 실패 및 복구
- SMTP provider degraded

완료 이메일에는 최소한 다음을 포함한다.

- Job ID, attempt ID와 analysis type
- profile ID/version과 ANSYS version
- 모델 및 주요 입력 조건
- 구조해석: 최대응력, 최대변위, 최소 안전율, convergence
- 공력해석: 속도, drag, downforce, Cd, Cl, convergence
- 시작·완료 시각과 실행 시간
- report 첨부 또는 안전한 link
- NAS artifact ID 또는 내부 확인 안내
- Notion page link가 허용되는 경우 해당 link
- warning 및 engineering validation 상태

사용자 입력은 HTML escape와 header/control-character 정제를 거쳐야 한다.

- FR-NOTIFY-001 Must: Core template는 NotificationDocument를 만들고 SMTP adapter가 이를 plain text/HTML multipart email로 렌더링해야 한다.
- FR-NOTIFY-002 Must: KPI가 profile상 not_applicable이면 사유를 표시하거나 항목을 생략하고 존재하지 않는 값을 0으로 표시하지 않아야 한다.
- FR-NOTIFY-003 Must: notification route는 link dependency를 bounded wait하고, 기한 내 준비되지 않으면 summary-only를 보내거나 정책상 대기 상태를 유지해야 한다.
- FR-NOTIFY-004 Must: summary-only 선발송 후 NAS/Notion link가 준비되면 별도 idempotency key를 가진 link-ready 후속 알림을 보낼 수 있어야 한다.

### 11.22 Local Dashboard 및 Tray

- FR-UI-001 Must: UI는 기본적으로 127.0.0.1에만 bind해야 한다.
- FR-UI-002 Must: queue, running job, stage, progress, warnings와 integration 상태를 보여야 한다.
- FR-UI-003 Must: submit, pause, resume, cancel, approved retry와 result open을 지원해야 한다.
- FR-UI-004 Must: analysis 상태와 provider-neutral storage/publication/notification operation의 route/status를 별도 열로 표시하고 특정 provider 이름을 domain schema로 고정하지 않아야 한다.
- FR-UI-005 Must: rejected/error code와 해결 방법을 보여야 한다.
- FR-UI-006 Must: profile 정보, version, 승인자와 golden status를 보여야 한다.
- FR-UI-007 Must: provider health, disk, RAM, license와 queue worker health를 보여야 한다.
- FR-UI-008 Must: secret, raw token, password와 private key를 표시하지 않아야 한다.
- FR-UI-009 Must: 역할 제어를 활성화한 구성에서 운영자 설정 변경은 인증된 OS 사용자 권한을 요구해야 한다.
- FR-UI-010 Should: 진단 bundle을 비밀정보 제거 후 export할 수 있어야 한다.

기본 화면:

1. Overview: worker, license, resource, provider health
2. Submit Job: profile 선택, 입력, parameter, validation preview
3. Queue: 대기·실행·완료·실패 목록과 제어
4. Job Detail: event timeline, progress, metric, artifact, integration 상태
5. Profiles: version, 승인 상태, Golden Case와 허용 parameter
6. Documents: NAS/Notion ingest, 분석, stale와 conflict 상태
7. Integrations: storage, publication, notification route와 실제 provider label, health, retry와 dead-letter
8. Settings/Diagnostics: machine config, 테스트, 진단 bundle

### 11.23 MCP Gateway

- FR-MCP-001 Could: 기존 ansys-mcp-server를 queue client/gateway로 재사용할 수 있다.
- FR-MCP-002 Must: MCP가 장시간 solver process의 source of truth가 되어서는 안 된다.
- FR-MCP-003 Could: submit_job, queue_status, cancel_job, retry_job, get_result와 list_profiles 도구를 제공할 수 있다.
- FR-MCP-004 Must: raw APDL 및 arbitrary Workbench script tool은 production profile에서 기본 비활성이어야 한다.
- FR-MCP-005 Must: MCP 요청도 local UI/Hot Folder와 동일한 validation과 authorization을 거쳐야 한다.

---

## 12. 공급자 중립 통합 요구사항

### 12.1 Port

~~~text
NotificationProvider.send(message, destination, idempotency_key)
StorageProvider.stat/list/open_read/begin_write/commit_write
ArtifactLinkProvider.create_link(artifact_ref, audience, expires_at, idempotency_key)/reconcile/revoke(link_id)
KnowledgeBaseProvider.list_changes/get/create/update/archive
SearchIndexProvider.upsert/delete/query
ContentAnalyzerProvider.analyze
SecretStoreProvider.resolve

NotificationDocument(title, summary, severity, facts, sections, actions, artifact_refs)
DestinationRef(route_id, logical_audience)
~~~

- INT-PORT-001 Must: Core는 provider SDK를 직접 참조하지 않아야 한다.
- INT-PORT-002 Must: provider는 manifest, version, host API range, config schema와 capabilities를 선언해야 한다.
- INT-PORT-003 Must: startup에서 capability negotiation을 수행해야 한다.
- INT-PORT-004 Must: 지원하지 않는 attachment, link, rich content는 정책에 따라 degrade하거나 config 오류로 막아야 한다.
- INT-PORT-005 Must: 테스트용 fake provider와 local-folder provider를 제공해야 한다.
- INT-PORT-006 Must: 모든 adapter는 공통 contract test를 통과해야 한다.
- INT-PORT-007 Must: 안전한 artifact link는 ArtifactLinkProvider를 통해서만 만들고 expiry, revocation, audience binding과 access audit capability를 가져야 한다.
- INT-PORT-008 Must: 영구 bearer URL을 기본 생성하지 않아야 하며 만료·해지가 불가능하면 external sharing capability를 지원하지 않는 것으로 선언해야 한다.
- INT-PORT-009 Must: Core와 template는 provider-neutral NotificationDocument와 DestinationRef만 생성하고 SMTP multipart, Slack card 등 provider 표현은 adapter가 렌더링해야 한다.
- INT-PORT-010 Must: link receipt에는 link ID, artifact ID, audience, 생성·만료·해지 시각과 provider receipt를 저장하되 전체 bearer URL/token은 encrypted secret reference로만 보존해야 한다.
- INT-PORT-011 Must: link 생성은 idempotency key를 사용하고 provider 성공 직후 crash 시 provider-side metadata로 reconcile하여 중복 유효 link를 만들지 않아야 한다.
- INT-PORT-012 Must: bearer URL/token을 log, event, audit, preview와 error에 평문으로 남기지 않고 authorized publication/notification render 시점에만 JIT resolve해야 한다.
- INT-PORT-013 Must: delivery-scoped link의 notification이 POLICY_REVOKED 또는 permanent failure가 되거나 authorized consumer가 없어지면 해당 link를 revoke하고 receipt를 갱신해야 한다.

### 12.2 논리 Route

Job은 provider ID 대신 논리 policy를 사용한다.

~~~yaml
policies:
  engineering_results:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
      - analysis.job.failed
      - analysis.job.cancelled
    route: result_notice
  engineering_archive:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
      - analysis.job.failed
      - analysis.job.cancelled
    artifact_roles:
      - mandatory_result
      - summary_report
      - diagnostic_package
      - failure_record
      - cancel_record
    if_present: true
    route: archive_results
  engineering_result_link:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
    artifact_roles:
      - summary_report
    route: create_result_link
  engineering_knowledge:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
    artifact_roles:
      - summary_report
      - metrics
    route: publish_summary

routes:
  result_notice:
    mode: fanout
    destination: analysis_team
    depends_on:
      - route: create_result_link
        when_planned: true
      - route: publish_summary
        when_planned: true
    dependency_deadline_sec: 300
    dependency_fallback: summary_only_then_link_ready_followup
    targets:
      - provider: primary_smtp
        criticality: required_for_product_rollup

  archive_results:
    mode: first_success
    targets:
      - provider: nas_results
        criticality: required_for_product_rollup

  create_result_link:
    mode: first_success
    destination: analysis_team
    depends_on:
      - route: archive_results
        receipt_role: remote_artifact
    targets:
      - provider: nas_result_links
        criticality: optional

  publish_summary:
    mode: first_success
    depends_on:
      - route: create_result_link
        when_planned: true
    dependency_deadline_sec: 300
    dependency_fallback: publish_without_artifact_link
    targets:
      - provider: engineering_notion
        criticality: optional
~~~

Provider 교체는 route config 변경으로 완료되어야 한다.

- INT-ROUTE-001 Must: route는 ordered target, fanout 또는 first_success mode, fallback, capability degrade, audience와 sensitivity allowlist를 선언해야 한다.
- INT-ROUTE-002 Must: 각 target은 optional, required_for_publication 또는 required_for_product_rollup criticality를 선언해야 한다.
- INT-ROUTE-003 Must: operation dependency graph를 선언하여 local artifact, storage publish, knowledge publish와 notification 사이의 선행 조건을 표현해야 한다.
- INT-ROUTE-004 Must: dependency에는 무한 대기를 막는 deadline과 summary-only, skip, fail 또는 follow-up fallback을 정의해야 한다.
- INT-ROUTE-005 Must: optional provider의 잘못된 config는 해당 route를 DEGRADED로 만들되 solver agent와 무관한 route의 시작을 차단하지 않아야 한다.
- INT-ROUTE-006 Must: core queue/ArtifactStore 등 필수 config 오류와 optional provider/route 오류를 서로 다른 health 및 startup policy로 분류해야 한다.
- INT-ROUTE-007 Must: policy는 trigger event, 대상 artifact role, if-present/required 조건과 route를 명시하여 어떤 terminal 결과에서 operation을 만드는지 결정해야 한다.
- INT-ROUTE-008 Must: safe-link operation은 archive/storage receipt의 remote artifact reference를 입력으로 소비하고 생성된 link receipt를 publication/notification operation에 전달해야 한다.
- INT-ROUTE-009 Must: startup에서 operation dependency graph의 cycle, 존재하지 않는 route/provider와 충족 불가능한 required dependency를 거부해야 한다.

### 12.3 Event와 Outbox

공통 event envelope:

~~~json
{
  "schema_version": 1,
  "event_id": "01J...",
  "event_type": "analysis.job.succeeded",
  "occurred_at": "UTC ISO-8601",
  "aggregate_id": "job-...",
  "aggregate_version": 12,
  "correlation_id": "submission-id",
  "sequence": 12,
  "severity": "info",
  "payload_ref": "artifact://job-id/summary.json"
}
~~~

- INT-EVENT-001 Must: event는 versioned schema와 unique event ID를 가져야 한다.
- INT-EVENT-002 Must: 큰 binary와 본문은 event payload가 아니라 artifact/document reference로 전달해야 한다.
- INT-EVENT-003 Must: domain state와 event는 transactional outbox pattern으로 함께 저장해야 한다.
- INT-EVENT-004 Must: operation idempotency key에 event, policy revision, route, provider, destination, template revision과 operation kind를 포함해야 한다.
- INT-EVENT-005 Must: outbox worker는 lease, heartbeat, attempt count와 next-attempt 시간을 사용해야 한다.
- INT-EVENT-006 Must: provider receipt, remote ID, sanitized error와 delivery state를 저장해야 한다.
- INT-EVENT-007 Must: inbound polling/webhook은 provider external event/version key로 dedupe해야 한다.
- INT-EVENT-008 Must: retry exhausted operation은 dead-letter로 이동해야 한다.
- INT-EVENT-009 Must: provider config/template revision을 operation에 snapshot해야 한다.
- INT-EVENT-010 Must: secret은 operation 실행 시 SecretStore에서 최신 값을 resolve해야 한다.
- INT-EVENT-011 Must: immutable content/config snapshot과 별개로 모든 외부 side effect 직전에 현재 recipient membership, external-send permission, artifact sensitivity, destination allowlist, link와 Notion target permission을 다시 평가해야 한다.
- INT-EVENT-012 Must: 현재 policy 또는 authorization이 철회되었으면 operation을 POLICY_REVOKED로 중단하고 검토 없이는 전송·발행·업로드하지 않아야 한다.
- INT-EVENT-013 Must: provider/route 전환 시 PENDING operation만 운영자의 명시적 re-plan과 audit를 거쳐 새 route로 이동할 수 있어야 한다.
- INT-EVENT-014 Must: EXECUTING 또는 UNKNOWN operation은 중복 side effect 위험 때문에 자동 migration하지 않고 기존 provider receipt reconciliation 또는 수동 결정을 요구해야 한다.
- INT-EVENT-015 Must: SUCCEEDED/accepted receipt와 원래 snapshot은 provider 제거 후에도 retention 정책에 따라 보존해야 한다.
- INT-EVENT-016 Must: DB, event schema, provider config와 adapter migration 전 backup과 dry-run validation을 수행하고 실패 시 rollback 또는 read-only safe mode로 전환해야 한다.

---

## 13. 데이터 모델

### 13.1 주요 SQLite 테이블

~~~text
submissions
jobs
attempts
cancel_commands
job_events
artifacts
artifact_links
resource_leases
profiles
profile_snapshots

domain_events
integration_operations
integration_attempts
provider_receipts
notification_recipients
integration_inbox
provider_instances
egress_decisions

external_objects
documents
document_versions
document_chunks
index_entries
sync_cursors
publications
publication_chunks
conflicts
~~~

jobs에는 solver_outcome, engineering_outcome, artifact_status와 job_terminal_status를 서로 다른 필드로 저장하고, attempts에는 process/lease/preflight/recovery/cancel 상태를 저장한다.

### 13.2 Metric

공통 metric 필드:

~~~text
metric_id
name
value
unit
kind
requirement_status
not_applicable_reason
scope
aggregation
coordinate_system
direction
step
quality
source
~~~

각 profile은 metric을 required, optional 또는 not_applicable(reason)로 선언한다. scalar metric과 시계열 evidence는 분리한다.

구조 기본 metric:

- max_von_mises_stress
- max_total_deformation
- reaction_force_x/y/z
- mesh_node_count
- mesh_element_count
- convergence_status
- min_safety_factor: 항복강도와 판정 기준이 정의된 profile에서만 required

공력 기본 metric:

- drag_force
- lift_force
- downforce
- Cd
- Cl
- optional Cm
- profile-defined control-surface mass flow와 mass_imbalance
- mesh_cell_count
- mesh quality
- convergence_status

시계열 및 분포 evidence:

~~~text
series_id
metric_name
unit
axis_name
sample_count
storage_artifact_ref
summary_min/max/mean/std/slope
source
~~~

- DATA-METRIC-001 Must: residual history, force monitor history와 window series를 scalar value 하나에 넣지 않고 series artifact로 보존해야 한다.
- DATA-METRIC-002 Must: 외부유동에서 inlet/outlet 명칭을 가정하지 않고 profile이 정의한 control surface 전체의 질량 보존 evidence를 사용해야 한다.
- DATA-METRIC-003 Must: required metric이 누락되면 artifact validation을 실패시키고 optional/not_applicable metric은 명시적 status와 사유를 가져야 한다.
- DATA-METRIC-004 Must: report와 notification은 not_applicable 값을 0 또는 정상 수치처럼 표현하지 않아야 한다.

### 13.3 Artifact Reference

~~~text
artifact_id
provider_instance
object_key
version_id_or_etag
role
media_type
size_bytes
sha256
retention_class
sensitivity
created_at
producer
~~~

### 13.4 Document Provenance

~~~text
source_provider
external_id
source_version
source_sha256
retrieved_at
parser_id_and_version
analyzer_id_and_version
analysis_profile_hash
page_section_block_locator
normalized_content_ref
~~~

---

## 14. 폴더 및 배포 구조

### 14.1 배포 패키지

~~~text
MECar-Ansys-Automation/
├─ app/
├─ schemas/
├─ profiles/
├─ templates/
│  ├─ structural/
│  └─ aero/
├─ adapters/
├─ report-templates/
├─ notification-templates/
├─ scripts/
│  ├─ install.ps1
│  ├─ uninstall.ps1
│  ├─ verify.ps1
│  └─ submit.ps1
├─ docs/
└─ config.example.yaml
~~~

### 14.2 운영 데이터

~~~text
C:\AnsysAuto\
├─ drop\
├─ staging\
├─ accepted\
├─ work\<job-id>\<attempt-id>\
├─ results\<job-id>\
├─ rejected\
├─ quarantine\
├─ cache\documents\
├─ state\queue.db
├─ state\knowledge.db
├─ logs\
├─ config\
└─ outbox\
~~~

로컬 경로는 OneDrive와 한글 경로를 피한 짧은 ASCII 경로를 기본으로 한다.

### 14.3 NAS 권장 구조

~~~text
\\NAS\MECar\
├─ accepted-input-archive\
├─ analysis-results\
│  └─ <job-id>\
├─ engineering-documents\
├─ archive\
└─ quarantine\
~~~

accepted-input-archive는 접수 완료 snapshot의 장기 보존 위치이며 NAS job 제출 inbox가 아니다. 기본 NAS scanner의 자동 수집 대상은 allowlist된 engineering-documents이고, NAS 기반 job 제출을 별도로 활성화하려면 Hot Folder와 동일한 READY, dedupe, actor/ACL과 quarantine 계약을 적용해야 한다.

---

## 15. Notion 데이터 소스 요구사항

권장 필드:

| 필드 | 용도 |
|---|---|
| Title | 문서 또는 해석 제목 |
| Canonical ID | local job/document ID |
| Source Type | ANSYS, NAS document, Notion |
| Source URI | 내부 artifact reference |
| Source SHA-256 | 중복 및 버전 판별 |
| Revision | 원본 revision |
| Project | 프로젝트 |
| Discipline | Structure, Aero, Controls 등 |
| Document Type | Report, Drawing, Specification 등 |
| Status | Draft, Review, Approved, Stale |
| Sensitivity | Internal, Restricted, External Shareable |
| Tags | 검색용 태그 |
| Profile | 해석/분석 profile |
| ANSYS Version | solver version |
| Convergence | 수렴 상태 |
| Cd | 공력 KPI |
| Downforce | 공력 KPI |
| Max Stress | 구조 KPI |
| Safety Factor | 구조 KPI |
| Related Job | 관련 analysis job |
| Last Analyzed | 분석 시각 |
| Publication Revision | 자동 발행 revision |
| Managed By | 자동화 origin marker |

권장 page 본문:

1. 요약
2. 입력 및 해석 조건
3. 핵심 지표
4. 수렴·품질 판정
5. 주요 결론
6. 설계상 주의점
7. 요구사항·의사결정·후속 작업
8. 원문 또는 NAS 원본
9. 관련 해석·문서
10. Provenance와 생성 버전
11. 사람 검토 메모

자동화가 관리하는 section과 사람 검토 메모 section을 분리한다.

---

## 16. 보안 및 개인정보 요구사항

- SEC-001 Must: 최소 권한 Windows 계정으로 실행해야 한다.
- SEC-002 Must: SMTP password, NAS credential, Notion token과 private key를 YAML, SQLite, event, log와 report에 저장하지 않아야 한다.
- SEC-003 Must: secret reference만 config에 허용해야 한다.
- SEC-004 Must: 실행 파일, script, provider endpoint, recipient와 NAS prefix를 allowlist해야 한다.
- SEC-005 Must: manifest 기반 path traversal, zip bomb, symlink/junction/reparse escape를 차단해야 한다.
- SEC-006 Must: localhost UI를 외부 interface에 bind하지 않아야 한다.
- SEC-007 Must: 원격 state-changing action은 인증된 POST, CSRF 보호, nonce와 short-lived token을 사용해야 한다.
- SEC-008 Must: 이메일 GET link로 cancel/retry를 수행하지 않아야 한다.
- SEC-009 Must: 문서와 artifact에 Internal, Restricted, External Shareable 분류를 지원해야 한다.
- SEC-010 Must: Restricted CAD, 재료 데이터와 native solver result의 외부 이메일·Notion 업로드를 기본 차단해야 한다.
- SEC-011 Must: 외부 수신자 발송은 명시적 policy가 있을 때만 허용해야 한다.
- SEC-012 Must: log의 이메일 주소를 필요한 범위에서 마스킹하고 본문·첨부 내용을 기록하지 않아야 한다.
- SEC-013 Must: report와 email에서 local username, absolute path, license server, stack trace와 secret을 redaction해야 한다.
- SEC-014 Must: TLS certificate를 검증하고 insecure override를 production에서 금지해야 한다.
- SEC-015 Must: template/profile 승인·변경·실행과 cancel/retry를 audit해야 한다.
- SEC-016 Must: 자동 영구 삭제를 기본 금지해야 한다.
- SEC-017 Must: local data root, SQLite, logs와 cached documents에 해당 Windows 실행 계정 중심의 NTFS ACL을 적용해야 한다.
- SEC-018 Should: 민감 자료를 저장하는 PC는 BitLocker 또는 동등한 full-disk encryption을 사용해야 한다.
- SEC-019 Must: Local UI, Tray와 동일 사용자 CLI action은 Windows SID와 session을 actor로 기록하고 manifest의 자기신고 actor/role을 권한 판단에 사용하지 않아야 한다.
- SEC-020 Must: 공유 Hot Folder 또는 remote MCP를 활성화하면 Windows 인증, 사용자별 ACL inbox 또는 서명된 token 중 하나로 actor identity와 권한을 검증해야 한다.
- SEC-021 Must: parse, analyze, storage upload, knowledge publish, link create와 notify 각 egress boundary에서 현재 sensitivity, audience, redaction과 provider location policy를 평가해야 한다.
- SEC-022 Must: provider adapter는 local/external, data residency, supported sensitivity와 retention capability를 선언해야 한다.
- SEC-023 Must: Restricted 원문은 명시적으로 허용된 policy와 redaction 결과가 없으면 외부 ContentAnalyzer 또는 SaaS로 보내지 않아야 한다.
- SEC-024 Must: egress decision은 policy revision, input sensitivity, destination, redaction 결과와 actor를 audit해야 한다.

---

## 17. 신뢰성·복구 요구사항

- NFR-REL-001 Must: agent 또는 PC crash로 committed job/event/operation이 유실되지 않아야 한다.
- NFR-REL-002 Must: SQLite transaction, WAL, backup과 integrity check를 지원해야 한다.
- NFR-REL-003 Must: 결과 finalization은 atomic이어야 한다.
- NFR-REL-004 Must: worker lease 만료와 orphan process reconciliation을 지원해야 한다.
- NFR-REL-005 Must: notification/storage/publication retry가 solver retry를 유발하지 않아야 한다.
- NFR-REL-006 Must: provider별 circuit breaker와 health 상태를 가져야 한다.
- NFR-REL-007 Must: HTTP 429/529 및 Retry-After, SMTP 4xx, SMB reconnect를 provider별로 처리해야 한다.
- NFR-REL-008 Must: DB, result, profile, template과 config의 backup/restore 절차가 있어야 한다.
- NFR-REL-009 Must: disk-low 시 새 job을 중단하고 기존 결과 삭제 없이 운영자에게 알려야 한다.
- NFR-REL-010 Must: purge는 retention policy, pin 상태와 dependency를 검사해야 한다.

---

## 18. 성능 및 자원 격리

- NFR-PERF-001 Must: heavy solve 기본 동시 실행 수는 1이어야 한다.
- NFR-PERF-002 Must: 문서 indexing, NAS upload와 Notion/email worker가 CFD solve의 CPU/RAM/I/O를 과도하게 방해하지 않도록 resource class를 가져야 한다.
- NFR-PERF-003 Must: provider별 concurrency와 rate limit을 적용해야 한다.
- NFR-PERF-004 Should: 큰 파일은 streaming 또는 chunked copy를 사용해야 한다.
- NFR-PERF-005 Must: local UI는 solver 상태 조회로 queue DB를 장시간 lock하지 않아야 한다.
- NFR-PERF-006 Must: log와 event는 rolling/retention 정책을 가져야 한다.

---

## 19. 호환성 및 버전 정책

- COMP-001 Must: ANSYS 2021 R1, v211 exact executable을 기본 지원 대상으로 한다.
- COMP-002 Must: 다른 ANSYS release로 silent fallback하지 않아야 한다.
- COMP-003 Must: 더 최신 release/build에서 저장된 Workbench project, Mechanical database, Fluent case/data, MAPDL .db/.rst와 restart artifact를 2021 R1이 소비하지 않도록 거부해야 한다.
- COMP-004 Must: Fluent journal은 21.1 TUI version으로 고정해야 한다.
- COMP-005 Must: 2021 R1과 exact compatibility가 검증되지 않은 PyMechanical과 PyFluent를 실행 기반으로 사용하지 않아야 한다.
- COMP-006 Must: native Workbench journal/ACT, MAPDL batch와 Fluent journal/TUI를 기본으로 한다.
- COMP-007 Must: Python/runtime과 dependency는 배포 패키지 또는 설치 검증으로 고정해야 한다.
- COMP-008 Must: provider API version, schema와 migration을 명시해야 한다.
- COMP-009 Must: 자동 dependency upgrade로 운영 job의 결과가 바뀌지 않아야 한다.
- COMP-010 Must: resolved profile에는 exact product build/service pack, executable absolute path와 file version, template authoring build, case/project format과 Fluent precision을 기록해야 한다.
- COMP-011 Must: static file header로 release를 확정할 수 없는 native file은 licensed preflight에서 열어 compatibility를 판정하고 intake 단계에서 호환된다고 추측하지 않아야 한다.
- COMP-012 Must: Golden Case 비교는 동일 solver build, core 수, parallel mode, precision과 report averaging window를 기준으로 하며 달라진 조건은 별도 baseline 승인을 요구해야 한다.

---

## 20. 관측성과 감사

- OBS-001 Must: 모든 log/event에 job ID, attempt ID, correlation ID를 포함해야 한다.
- OBS-002 Must: structured rolling log를 제공해야 한다.
- OBS-003 Must: process heartbeat, solver activity, stage와 last progress를 구분해야 한다.
- OBS-004 Must: provider health, retry count, next retry와 dead-letter를 보여야 한다.
- OBS-005 Must: solver/version/profile/input/artifact hash를 result에 포함해야 한다.
- OBS-006 Must: user action, config/profile approval, cancel/retry와 publication conflict를 audit해야 한다.
- OBS-007 Must: diagnostic bundle은 secret과 민감 내용을 제거해야 한다.
- OBS-008 Should: machine CPU/RAM/disk/power/license 상태 history를 제한적으로 보존해야 한다.

---

## 21. 오류 분류

안정된 error category와 code 체계를 제공한다.

| Category | 예시 | 기본 처리 |
|---|---|---|
| INPUT_INVALID | schema, unit, range, missing file | Reject, 자동 retry 안 함 |
| PROFILE_INVALID | hash, version, selection/zone 없음 | Reject, 관리자 검토 |
| PROFILE_INCOMPATIBLE | licensed preflight의 build/file/template 불일치 | Attempt fail, profile 비활성 검토 |
| PREFLIGHT_FAILED | licensed 내부 scope/mesh/zone 검사 실패 | Attempt fail, 자동 retry 안 함 |
| SECURITY_REJECTED | traversal, raw script, forbidden path | Quarantine |
| LICENSE_UNAVAILABLE | checkout 거부 | Retry wait |
| RESOURCE_UNAVAILABLE | RAM, disk, power | Queue wait 또는 fail |
| SOLVER_START_FAILED | executable/process startup | 제한적 retry |
| MESH_FAILED | mesh 생성·품질 실패 | Engineering fail, 자동 retry 안 함 |
| NON_CONVERGED | 구조/CFD 수렴 실패 | Warning 또는 engineering fail |
| SOLVER_FATAL | crash, fatal log | 제한적 retry 또는 fail |
| TIMEOUT | wall time 초과 | Cancel 후 fail |
| CANCELLED | 사용자·운영자 요청 | Cancelled |
| ARTIFACT_FAILED | mandatory package 실패 | Packaging fail |
| NAS_FAILED | SMB 복제 실패 | Storage outbox retry |
| NOTION_FAILED | publication 실패 | Publication outbox retry |
| SMTP_TRANSIENT | 4xx, timeout | Notification outbox retry |
| SMTP_PERMANENT | 5xx, invalid recipient | Dead-letter |
| POLICY_REVOKED | recipient, sensitivity, destination 권한 철회 | 외부 side effect 중단, 검토 필요 |
| CONFIG_INVALID | core 또는 provider/route/schema 오류 | core 시작 차단 또는 해당 route 비활성 |

---

## 22. Retention 및 삭제

프로젝트별로 설정 가능해야 하며 기본 원칙은 다음과 같다.

- manifest, metrics, summary, provenance와 audit는 장기 보존 대상이다.
- native result와 restart는 용량 기반 보존 대상이며 pin을 지원한다.
- workdir는 결과 확정과 검증이 끝난 뒤에만 정리 후보가 된다.
- 실패·취소 attempt는 진단에 필요한 log와 partial artifact를 보존한다.
- NAS 원본과 승인된 결과의 자동 영구 삭제는 기본 금지한다.
- Notion remote 삭제는 local tombstone을 만들며 자동으로 원본을 삭제하지 않는다.
- 삭제 작업은 exact 대상, policy, actor와 결과를 audit한다.
- storage quota 부족 시 newest job을 무조건 지우지 않고 새 작업 시작을 차단한다.

---

## 23. 인수 기준

### 23.1 설치 및 무인 실행

1. 설치 후 Windows 로그인 시 agent가 자동 시작한다.
2. structural_mechanical golden job을 Hot Folder에 제출하면 Workbench UI 클릭 없이 완료된다.
3. aero_fluent golden job을 제출하면 Fluent GUI 없이 완료된다.
4. 지원되는 structural_mapdl golden job이 native batch로 완료된다.
5. 완료 후 modal dialog, child process와 stale lock이 남지 않고 다음 job이 시작된다.

### 23.2 검증 및 중복 방지

1. missing file, bad unit/range와 wrong profile hash는 license-free static validation에서 REJECTED된다.
2. missing/empty/wrong-entity Named Selection, invalid contact, unassigned material, missing zone/report와 inconsistent reference value는 licensed preflight에서 full solve 전에 차단된다.
3. 존재하는 이름은 같지만 entity/body count와 scope가 profile 계약에서 벗어난 Mechanical 모델이 통과하지 않는다.
4. prepared_case profile에 STEP을 제출하거나 geometry_to_case profile에 backend/script 계약이 없으면 실행하지 않는다.
5. 다른 ANSYS release/build, template authoring build, case precision 또는 호환되지 않는 project/case/database/restart를 거부한다.
6. path traversal, arbitrary executable/script와 job root escape가 실행되지 않는다.
7. project/case의 unapproved ACT extension, UDF/DLL, Scheme 또는 external hook이 licensed preflight를 통과하거나 실행되지 않는다.
8. 같은 submission ID와 hash를 두 번 제출해도 solve는 한 번만 실행된다.
9. 같은 submission ID에 다른 hash가 들어오면 충돌로 격리된다.
10. 복사 중 파일, 0-byte 파일과 손상 archive를 접수하지 않는다.

### 23.3 결과 정확성

1. golden 구조 job 핵심 metric이 승인된 수동 결과와 profile tolerance 안에서 일치한다.
2. golden Fluent job의 drag, downforce와 Cd가 기준 결과와 profile tolerance 안에서 일치한다.
3. Golden 비교 record에 exact solver build, core 수, parallel mode, precision과 report averaging window가 일치한다.
4. report에 unit, named coordinate system, 변환 전후 axes, sign, density, velocity와 reference area가 표시된다.
5. yaw를 변경해도 inlet/drag/lift transform과 downforce sign invariant가 golden tolerance 안에서 유지된다.
6. authoritative downforce와 redundant lift/downward-vector 값이 정의된 허용 오차 안에서 reconciliation된다.
7. artificial nonconverged case를 일반 성공으로 표시하지 않는다.
8. Fluent TUI error와 license exit, MAPDL .err fatal/license failure가 서로 다른 안정된 code로 분류된다.
9. exit code 0이지만 mandatory output 또는 convergence evidence가 없는 case를 성공 처리하지 않는다.
10. 모든 mandatory artifact hash와 실제 파일이 일치한다.

### 23.4 진행률·취소·복구

1. stage event가 역행하지 않는다.
2. Fluent fixed iteration run의 current/target이 report와 일치한다.
3. 알 수 없는 전체량에 false percentage를 표시하지 않는다.
4. queued cancel은 solver를 시작하지 않는다.
5. Workbench running cancel 후 Mechanical child tree와 lock이 정리되고 partial 결과가 final로 표시되지 않는다.
6. MAPDL nonlinear/full-transient ABT cancel과 ordinary linear force termination을 각각 시험하고 capability가 정확히 표시된다.
7. Fluent chunk checkpoint profile과 force-termination profile을 각각 시험하며 checkpoint 미지원 run을 재개 가능으로 표시하지 않는다.
8. 손상되거나 build/profile/input hash가 다른 checkpoint는 자동 resume하지 않는다.
9. cancel과 final artifact commit 경합은 정의된 compare-and-set 규칙대로 한 terminal event만 만든다.
10. agent kill과 PC reboot 후 queue DB가 손상되지 않는다.
11. orphan attempt가 중복 실행 없이 interrupted/recovery 상태로 전환된다.

### 23.5 NAS

1. 부분 복사 중인 NAS 파일을 ingest하지 않는다.
2. NAS disconnect 중 local result와 outbox를 잃지 않는다.
3. NAS 재연결 후 복제를 이어서 수행한다.
4. remote upload checksum이 local artifact와 일치한다.
5. 외부 이메일에 UNC path가 포함되지 않는다.
6. 생성된 HTTPS link는 audience와 만료시간에 결합되고 만료·해지 후 접근할 수 없으며 audit receipt가 남는다.
7. link provider 성공 직후 agent를 종료해도 reconcile 후 유효 link가 하나만 존재하고 bearer token은 log/event에 노출되지 않는다.

### 23.6 Notion 및 문서

1. allowlist되지 않은 Notion page/data source에 접근하지 않는다.
2. 같은 job/source hash를 재처리해도 중복 page를 만들지 않는다.
3. 같은 canonical source의 content hash가 변경되면 기존 identity의 새 version으로 처리하고 무관한 새 page를 만들지 않는다.
4. Notion 장애 중에도 solve와 NAS 저장은 완료된다.
5. 장애 복구 후 publication만 재시도된다.
6. 사람이 편집한 영역이 자동 갱신으로 삭제되지 않는다.
7. 동시 수정은 conflict로 감지되고 fail-and-review 처리된다.
8. 원문 변경 시 기존 분석이 stale로 표시된다.
9. 요약 결과가 원본 version과 section/page/block provenance를 가진다.
10. Notion 전체 제목 검색에 의존하지 않고 local 본문 검색이 동작한다.
11. 한 API page/batch를 넘는 긴 page, block tree와 property list를 누락 없이 끝까지 읽고 쓴다.
12. 여러 write chunk 중간에 429와 agent restart를 발생시켜도 완료 chunk가 중복되지 않고 남은 chunk부터 재개한다.
13. native version이 없는 동시 수정 conflict에서 base, generated와 remote snapshot을 모두 보존한다.
14. automation이 발행한 page가 inbound polling에서 자기 자신을 새 문서로 무한 재처리하지 않는다.
15. penultimate write chunk 직후 crash하면 page는 PUBLISHED로 보이지 않고 PARTIAL 상태에서 resume한 뒤 전체 hash 검증 후 한 번만 PUBLISHED가 된다.

### 23.7 SMTP 이메일

1. NAVER WORKS 가입 여부와 무관하게 내부·외부 유효 주소로 테스트 이메일을 보낸다.
2. 같은 결과 데이터에서 plain text와 HTML 본문을 생성한다.
3. SMTP password가 config, DB, log, error report에 노출되지 않는다.
4. SMTP 4xx와 timeout은 재시도되고 5xx는 별도 permanent 상태가 된다.
5. agent 재시작 후 pending email이 유실되지 않는다.
6. 동일 event가 의도적으로 중복 queue되지 않는다.
7. 초과 크기·금지 확장자 첨부가 차단되고 안전한 link 또는 요약으로 대체된다.
8. 외부 수신자에게 restricted artifact, credential 또는 UNC path가 전달되지 않는다.
9. SMTP 발송 실패가 solve 결과를 변경하거나 solve를 재실행하지 않는다.
10. starttls_required relay가 STARTTLS을 제공하지 않거나 handshake가 실패하면 AUTH와 message body가 전송되지 않는다.
11. pending email 재시도 전 recipient가 그룹에서 제거되거나 artifact가 Restricted로 재분류되면 POLICY_REVOKED로 중단되고 메일이 발송되지 않는다.
12. header From과 envelope-from이 설정대로 분리되고 relay receipt에 envelope 결과가 기록된다.
13. 한 transaction의 RCPT가 250/450/550으로 섞이면 recipient별 상태가 저장되고 450 주소만 재시도되며 250 주소는 다시 받지 않는다.
14. 정책 철회 또는 permanent delivery failure로 소비자가 없어진 delivery-scoped link는 자동 revoke된다.

### 23.8 공급자 교체

1. fake SMTP, local ArtifactStore와 fake KnowledgeBase로 전체 workflow를 실행할 수 있다.
2. SMTP server/provider 변경이 config만으로 가능하다.
3. Slack/Teams 등 시험 adapter를 추가해도 Core, job manifest와 DB domain schema를 변경하지 않는다.
4. attachment capability가 없는 provider는 정책에 따라 link/plain text로 degrade한다.
5. route dependency deadline 전에 link가 준비되면 포함하고, 미준비 시 설정된 summary-only/후속 알림 fallback이 중복 없이 동작한다.
6. provider 교체 시 PENDING operation만 승인 후 re-plan되고 EXECUTING/UNKNOWN은 자동 이동하지 않는다.
7. NAS, Notion, SMTP 전체 outage 중에도 완료된 solver attempt 수가 증가하지 않고 provider operation만 재시도된다.

### 23.9 보안

1. malicious archive, path, executable override가 실행되지 않는다.
2. 모든 secret은 Credential Manager/DPAPI reference로만 사용된다.
3. report와 email에 Windows username, license server, stack trace와 token이 포함되지 않는다.
4. 외부 SaaS 발행 전에 sensitivity와 redaction policy가 적용된다.
5. cancel/retry/profile approval/config 변경이 audit된다.
6. external ContentAnalyzer 호출 전에 Restricted 문서 egress가 차단되고 parse/analyze/publish/notify/storage 각 decision이 audit된다.
7. manifest의 위조 actor/role로 운영자 권한을 얻을 수 없고 Windows SID 또는 승인된 signed identity가 기록된다.

---

## 24. 필수 장애 시험

- 동일 제출 중복 및 watcher duplicate/missed event
- 복사 중 파일, 손상 ZIP, zip bomb, long path와 한글 파일명
- ANSYS executable 없음, wrong release/build/service pack과 잘못된 Fluent precision
- prepared_case에 STEP 제출, geometry_to_case preprocessing backend/script/license 누락
- unapproved Mechanical ACT/external command와 Fluent UDF/DLL/Scheme hook
- license 없음, checkout 실패와 mid-solve license loss
- disk full, DB lock, package 작성 중 process kill
- Workbench/Mechanical fatal, Mechanical empty/wrong scoping, invalid contact/material/mesh
- MAPDL .err fatal/license, nonlinear ABT cancel과 linear force termination
- Fluent TUI script error, license exit, yaw axis/downforce sign 불일치
- solver exit 0이나 결과 누락
- 구조 nonlinear nonconvergence
- Fluent residual·mass balance·force monitor nonconvergence
- 잘못된 drag/lift sign과 reference area
- agent kill, solver kill, logout, sleep, reboot와 reattach capability 불일치
- cancel과 natural completion 경합
- corrupt/incompatible checkpoint와 resume 중 process kill
- retry 중 config/profile update 및 최신 profile로 잘못된 자동 retry 시도
- NAS offline, 재연결, partial upload, permission 변경, checksum mismatch
- Notion rate limit, token revoke, 다중 page/block/property pagination, 중간 write chunk 429, property schema 변경
- Notion penultimate chunk crash, PARTIAL 노출과 final PUBLISHED commit barrier
- Notion page 동시 수정, archive/delete와 self-publication loop
- SMTP STARTTLS 미지원/downgrade/handshake 실패, authentication failure, 4xx, 5xx, timeout
- SMTP RCPT별 250/450/550 혼합 응답과 accepted recipient 선택적 재전송 방지
- SMTP relay accepted 직후 agent crash
- oversized attachment와 모든 link/fallback 불가
- 안전 link 생성 직후 crash/reconcile, audience 불일치, bearer redaction, expiry와 revoke
- pending operation 중 recipient 제거, external-send 철회와 artifact Restricted 재분류
- provider outage 중 solver retry 불발 검증
- secret rotation과 system time/timezone 변경

---

## 25. 설정 요구사항

설정은 다음 계층으로 분리한다.

1. App default
2. Machine config
3. Versioned profile
4. Provider instance config
5. Route/policy config
6. Runtime state
7. SecretStore

예시:

~~~yaml
app:
  data_root: C:\AnsysAuto
  timezone: Asia/Seoul
  max_parallel_heavy: 1

ansys:
  release: "211"
  root: C:\Program Files\ANSYS Inc\v211

providers:
  local_results:
    kind: storage
    adapter: local
    root: C:\AnsysAuto\results

  nas_results:
    kind: storage
    adapter: smb
    root: \\NAS01\MECar\analysis-results
    credential_ref: wincred://mecar/nas/results

  nas_result_links:
    kind: artifact_link
    adapter: approved_nas_https_share
    credential_ref: wincred://mecar/nas/share
    default_expiry_hours: 72

  engineering_notion:
    kind: knowledge
    adapter: notion
    token_ref: wincred://mecar/notion/token
    allowed_parent_ids:
      - REPLACE_WITH_ID

  primary_smtp:
    kind: notification
    adapter: smtp
    host: smtp.worksmobile.com
    port: 587
    security: starttls_required
    auth_mode: password_or_app_password
    username_ref: wincred://mecar/mail/username
    password_ref: wincred://mecar/mail/password
    header_from: analysis@example.com
    envelope_from: bounces@example.com
    max_attachment_bytes: 10485760

destination_groups:
  analysis_team:
    audience: internal_engineering
    delivery_mode: individual
    addresses:
      - member1@example.com
      - member2@gmail.com

routes:
  archive_results:
    mode: first_success
    targets:
      - provider: nas_results
        criticality: required_for_product_rollup

  create_result_link:
    mode: first_success
    destination: analysis_team
    depends_on:
      - route: archive_results
        receipt_role: remote_artifact
    targets:
      - provider: nas_result_links
        criticality: optional

  publish_summary:
    mode: first_success
    depends_on:
      - route: create_result_link
        when_planned: true
    dependency_deadline_sec: 300
    dependency_fallback: publish_without_artifact_link
    targets:
      - provider: engineering_notion
        criticality: optional

  result_notice:
    mode: fanout
    destination: analysis_team
    depends_on:
      - route: create_result_link
        when_planned: true
      - route: publish_summary
        when_planned: true
    dependency_deadline_sec: 300
    dependency_fallback: summary_only_then_link_ready_followup
    targets:
      - provider: primary_smtp
        criticality: required_for_product_rollup

policies:
  engineering_archive:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
      - analysis.job.failed
      - analysis.job.cancelled
    artifact_roles:
      - mandatory_result
      - summary_report
      - diagnostic_package
      - failure_record
      - cancel_record
    if_present: true
    route: archive_results
  engineering_result_link:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
    artifact_roles:
      - summary_report
    route: create_result_link
  engineering_knowledge:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
    artifact_roles:
      - summary_report
      - metrics
    route: publish_summary
  engineering_results:
    events:
      - analysis.job.succeeded
      - analysis.job.completed_with_warnings
      - analysis.job.engineering_failed
      - analysis.job.failed
      - analysis.job.cancelled
    route: result_notice
    sensitivity_allowlist:
      - Internal
~~~

모든 config는 schema/version을 가지며 시작 시 검증한다. running job과 pending integration operation에는 사용한 config revision을 snapshot한다.

---

## 26. 운영 전 필수 준비물

### 26.1 ANSYS

- 정상 접근 가능한 ANSYS 2021 R1 라이선스 또는 VPN
- Workbench, Mechanical, MAPDL, Fluent 설치 상태
- 대표 구조 Golden Case 및 수동 검증 결과
- 대표 공력 Golden Case 및 수동 검증 결과
- 구조 profile의 Named Selection, 재료, 하중, mesh와 결과 정의
- 공력 profile의 wall zone, 축, 부호, reference area, 유속/밀도, ground/wheel와 수렴 기준
- 배포 대상 PC마다 license/VPN/DNS 연결을 확인하고 exact build live batch smoke test를 통과할 것

### 26.2 로컬 PC

- 충분한 local SSD 용량
- Task Scheduler 실행 사용자
- AC/절전 정책
- 로컬 ASCII data root
- Windows Credential Manager/DPAPI 사용 권한

### 26.3 NAS

- UNC root
- source read 계정과 result write 계정 또는 최소권한 ACL
- 결과 retention과 backup 정책
- 내부 사용자 접근 방식
- 필요 시 인증된 HTTPS share link 기능

### 26.4 Notion

- Internal integration 또는 승인된 connection
- 읽기/쓰기 대상 page/data source
- property schema
- 자동화 managed 영역 및 사람 편집 영역
- 민감도별 게시 정책
- 초안 승인 책임자

### 26.5 이메일

- 사용할 SMTP relay
- 고정 발신 주소와 display name
- 외부 앱 비밀번호 또는 SMTP credential
- 수신자 논리 그룹
- 외부 발송 허용/차단 정책
- SPF, DKIM, DMARC 및 relay 정책에 대한 운영자 확인
- 첨부 크기와 허용 MIME 정책
- NAVER WORKS SMTP를 사용할 경우 Core Standard/Standard Plus 메일 사용 여부, 관리자 SMTP 허용과 외부 앱 비밀번호

---

## 27. 결정이 필요한 운영 정책

다음 값은 구현 전에 조직 또는 운영자가 확정해야 한다.

1. 구조해석 첫 Golden Case와 각 하중 case
2. Fluent 첫 Golden Case와 drag/lift 축, downforce 부호, 기준면적 정의
3. 각 profile의 engineering acceptance tolerance
4. NOT_CONVERGED를 warning으로 완료할지 engineering failure로 처리할지
5. 기본 CPU/RAM/disk reserve와 timeout
6. auto retry 최대 횟수와 license 대기 만료
7. NAS에 required_for_product_rollup으로 보존할 artifact 범위와 archival_complete 이후 local 대형 artifact 보존 기간
8. native result, restart, log, summary의 retention
9. 외부 수신자에게 보낼 수 있는 정보와 첨부 범위
10. 안전한 HTTPS link가 없을 때 외부 이메일의 대체 방식
11. Notion의 read-only, draft-approval, auto-publish 적용 범위
12. Notion Analysis Request를 job 제출 채널로 활성화할지 여부
13. MCP raw tools를 완전 비활성화할지 trusted admin mode로 둘지 여부
14. SMTP delivery uncertainty에서 중복 가능성과 누락 가능성 중 우선 정책
15. profile 승인자, 결과 검토자와 장애 대응 책임자

---

## 28. 공식 기술 근거

ANSYS 실행 계약의 규범 기준은 배포된 2021 R1 설치본 Help와 해당 release의 command reference, 그리고 exact v211 Golden Case evidence다. 아래의 더 최신 ANSYS 온라인 문서는 개념과 명령 체계 확인을 위한 비규범 참고자료이며, v211에서 직접 재검증하지 않은 option/API를 구현 근거로 사용해서는 안 된다.

- [Ansys Workbench command-line execution](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/wb2_js/wb2js_cmdlineexec.html)
- [Ansys Fluent batch execution](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/flu_ug/flu_ug_BatchExecution.html)
- [Ansys Fluent solution monitoring and report definitions](https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/flu_ug/flu_ug_reporting_sec_monitoring_solution.html)
- [PyMAPDL version compatibility](https://mapdl.docs.pyansys.com/version/stable/getting_started/versioning.html)
- [PyMechanical installation and compatibility](https://mechanical.docs.pyansys.com/version/dev/getting_started/installation.html)
- [NAVER WORKS SMTP settings](https://help.worksmobile.com/ko/use-guides/mail/settings/pop3-imap-smtp/)
- [NAVER WORKS external app password](https://help.worksmobile.com/ko/use-guides/settings/security/3rd-party-app-password/)
- [Notion authorization](https://developers.notion.com/guides/get-started/authorization)
- [Notion Markdown content API](https://developers.notion.com/guides/data-apis/working-with-markdown-content)
- [Notion files and media](https://developers.notion.com/guides/data-apis/working-with-files-and-media)
- [Notion search API](https://developers.notion.com/reference/post-search)
- [Notion request limits](https://developers.notion.com/reference/request-limits)
- [Notion webhooks](https://developers.notion.com/reference/webhooks)

---

## 29. 최종 제품 경계 요약

본 제품은 검증된 해석 템플릿을 반복 가능하고 추적 가능한 방식으로 무인 실행하는 로컬 자동화 플랫폼이다.

- 사용자는 정상 반복 작업에서 ANSYS를 직접 열지 않는다.
- 해석 전문가는 profile과 Golden Case를 소유한다.
- SQLite는 큐와 상태를 소유한다.
- 로컬 SSD의 immutable ArtifactStore는 접수 snapshot과 Job 성공의 필수 결과 package를 확정한다.
- NAS는 별도 archive/replica operation으로 원본과 장기 보존 대용량 결과를 보관한다.
- Notion은 문서·해석 결과를 분석하고 검색하는 지식 projection이다.
- 이메일은 가입 여부와 무관한 전달 채널이다.
- 외부 provider 장애는 solve 상태를 바꾸지 않는다.
- 외부 서비스는 port/adapter와 route config로 교체한다.
- 자동 실행 성공과 공학 모델 검증은 항상 구분한다.
