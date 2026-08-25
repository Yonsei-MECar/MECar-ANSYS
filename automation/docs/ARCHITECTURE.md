# Architecture and invariants

## 처리 흐름

Hot Folder 또는 CLI가 manifest를 검증하고 SQLite에 접수합니다. Dispatcher가 QUEUED 작업을 BEGIN IMMEDIATE transaction 안에서 한 번만 claim하고 attempt를 만듭니다. Adapter는 승인 profile만 작업별 격리 경로에 준비하며 ProcessSupervisor가 로컬 자원 gate 안에서 자식 프로세스를 관리합니다. Adapter의 결과 판정 뒤 local ArtifactStore가 필수 증거를 checksum 기반으로 확정하고, 같은 DB transaction에서 terminal transition, domain event와 SMTP outbox intent를 기록합니다. 외부 발송 실패는 solver 상태를 바꾸지 않습니다.

## 불변 조건

1. jobs, submissions, attempts, 모든 transition, events, artifacts, outbox message/delivery는 UPDATE와 DELETE trigger로 보호됩니다.
2. 현재 상태는 가장 마지막 append-only transition의 projection입니다.
3. 접수 transaction은 canonical manifest와 profile 본문/hash를 함께 동결합니다. 실행과 retry는 파일시스템의 최신 profile이 아니라 이 snapshot을 사용합니다.
4. 동일 submission ID와 동일 manifest/profile hash는 solve를 추가 생성하지 않습니다.
5. 동일 submission ID에서 manifest 또는 같은 버전 profile 본문이 달라지면 새 버전으로 추정하지 않고 충돌 격리합니다.
6. solver exit code 0만으로 성공하지 않습니다. Adapter의 mandatory output와 fatal evidence 검사를 통과해야 합니다.
7. local result publish는 staging copy, SHA-256, atomic replace 순서입니다.
8. provenance에는 manifest hash, profile identity/version/hash, adapter, automation/Python version, reason code와 source role이 포함됩니다.
9. SMTP intent는 terminal transition과 같은 transaction에서 생성됩니다.
10. 수신자 정책은 enqueue 시점이 아니라 실제 발송 직전에 다시 검사됩니다.
11. 외부 solver의 CPU/RAM/license 수와 timeout ceiling은 manifest가 아니라 동결된 승인 profile이 소유합니다.
12. 외부 solver, SMTP, NAS, lmutil license server probe는 각각 명시 enable 설정 없이는 호출되지 않습니다.
13. CPU/RAM/license/disk gate 실패는 engineering FAILED가 아니라 WAITING_RESOURCE이며 해당 attempt에는 공학 결과 artifact를 만들지 않습니다.
14. Persistent agent는 drain과 같은 cycle을 singleton dispatcher lock 아래 반복하고 signal 또는 stop marker에서 현재 cycle 이후 종료합니다.

## 재기동 복구

Agent 시작 시 reconcile은 latest attempt가 RUNNING인데 PID가 존재하지 않는 항목을 INTERRUPTED로 기록합니다. max_attempts 미만이면 작업을 QUEUED로 돌리고, 한도에 도달하면 FAILED로 전이합니다. cancel 요청 중 죽은 프로세스는 CANCELLED가 됩니다. PID가 살아 있으면 자동으로 새 solver를 시작하지 않습니다.

현재 MVP의 PID 검사는 단일 PC 프로세스 존재 여부까지입니다. 실제 ANSYS 운영에서는 PID 재사용 오판을 없애기 위해 executable path와 process creation time을 함께 기록하는 Windows Job Object 확장이 권장됩니다.

## 플러그인 포트

AnalysisAdapter는 prepare와 evaluate 두 메서드를 요구합니다. prepare는 profile을 manifest와 분리하고 안전한 command tuple을 반환합니다. evaluate는 process 결과와 mandatory evidence로 engineering 결과를 판정하고, 발행할 artifact 역할과 경로를 반환합니다. Dummy, MAPDL v211, Fluent v211이 같은 계약을 사용합니다.
