# 운영 활성화 전 결정표

코드는 아래 결정을 config/profile 값으로 받을 준비가 되어 있습니다. 확정 전 기본값은 전부 비활성입니다.

## MAPDL 2021 R1

- 실제 ANSYS211.exe 절대 경로, SHA-256과 exact build/service pack
- 사용할 라이선스 feature 이름과 동시에 허용할 seat 수
- 승인 master DAT 파일, SHA-256, 변경 책임자
- 필수 결과 파일 목록과 파일별 최소 유효 조건
- fatal/error/license/nonconvergence 판정 기준
- Golden Case의 입력, 수동 결과, 허용 오차
- timeout, CPU, RAM, disk reserve, 자동 재시도 횟수

확정 후 mapdl-v211-pending profile을 새 ID/version으로 복사하고 placeholder hash를 교체합니다. profile enabled와 external_execution_enabled를 켠 뒤 machine config의 external_execution_enabled를 마지막으로 켭니다.

## Fluent 2021 R1

- fluent.exe 절대 경로, SHA-256과 exact build/service pack
- 2ddp 또는 3ddp, CPU 수, 라이선스 feature/seat
- 승인 journal과 prepared case 및 부속 asset 경로, staging target, 각각의 SHA-256
- 좌표축, yaw 정의, drag/lift/downforce 부호
- density, velocity, reference area와 wheel/ground 조건
- residual, mass balance, force monitor averaging과 convergence 판정
- 필수 metrics.json/convergence.json 생성 계약
- Golden Case 수동 결과와 허용 오차

확정 후 Fluent pending profile을 새 version으로 복사해 같은 3단계 enable 순서를 따릅니다.

## SMTP

- SMTP host/port와 STARTTLS 또는 implicit TLS
- header From과 envelope-from
- Windows Credential Manager target 두 개: username_ref와 password_ref
- 허용 domain/address, 내부/외부 수신자 정책, 최대 수신자 수
- 4xx retry 횟수와 backoff, 5xx 운영 알림 정책

Windows Credential Manager에는 config의 wincred:// 뒤 문자열과 같은 target 이름으로 Generic Credential을 등록합니다. 비밀번호 자체는 config, DB, receipt, log에 기록하지 않습니다. app config와 notification config의 두 enable switch를 마지막에 켭니다.

## NAS

- versioned route ID와 승인 UNC root
- Agent 실행 계정, 쓰기 전용 범위와 최소 ACL
- archive 대상 artifact role 목록
- 결과 보존 기간, local purge 허용 시점과 공간 부족 기준
- `max_attempts`, 실행 주기와 장애 운영 알림 기준
- NAS archive가 product rollup에 필수인지 여부

코드는 이 값들을 `artifacts.archive` config로 받을 준비가 끝났습니다. 실제 UNC 값이나 credential은 저장소 예제에 넣지 않습니다. 기본 예제의 adapter와 두 enable switch는 모두 꺼져 있습니다.

활성화 시 `adapter=nas`, 고유 `route_id`, 절대 `root`, `roles`, `max_attempts`를 먼저 확정합니다. 그 뒤 route의 `external_enabled`와 machine의 `external_archive_enabled`를 마지막에 모두 true로 설정해야 합니다. 둘 중 하나라도 false이면 storage adapter 호출 전에 BLOCKED가 기록되고 대상 root를 건드리지 않습니다.

archive operation은 local immutable artifact와 별도 append-only 상태로 관리됩니다. NAS 장애는 analysis 상태를 바꾸거나 solver retry를 만들지 않습니다. 장애를 해결한 뒤 `archive-retry --job-id ...`와 `archive`만 실행합니다. 같은 route ID의 root fingerprint가 달라지면 기존 operation은 차단되므로 root 변경은 새 version의 route ID로 승인합니다.

## 로컬 Agent 운영

- C:\MECarRuntime\ansys-automation 용량과 백업 범위
- `agent.poll_interval_sec`, cycle별 job/archive 한도
- Task Scheduler 전용 실행 계정, AC/sleep/reboot 정책과 task 최종 enable 승인
- max_attempts와 stale process 운영 정책
- dispatcher 동시 실행 프로세스 한 개 보장 방식
- SQLite와 ArtifactStore 백업/복구 점검 주기

기본 예제는 agent와 Task를 모두 비활성 상태로 둡니다. 전용 계정과 절대 runtime/config/Python 경로를 결정한 뒤 관리 스크립트의 Plan을 검토하고, `-Apply -PromptForCredential`로 Disabled task를 등록합니다. `-EnableTask`는 최종 별도 결정입니다.

## License health probe

- 승인 lmutil.exe 또는 lmstat.exe 절대 경로와 SHA-256
- 명시적 `port@host`, 확인할 feature allowlist
- 0.1~30초 probe timeout과 EXHAUSTED/ERROR 운영 알림 기준

확정 전 `license_probe.adapter=disabled`와 두 gate는 false입니다. 활성화 시 `adapter=lmutil`, executable/hash/server/features/timeout을 채운 뒤 `license_probe.external_enabled`와 `external_license_probe_enabled`를 마지막에 모두 true로 설정합니다. probe는 health 진단 전용이며 solver 성공/실패 판정에는 사용하지 않습니다.
