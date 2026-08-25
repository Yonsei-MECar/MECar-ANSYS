# MECar Analysis Automation MVP

개인 Windows PC에서 검증된 해석 프로필을 안전하게 반복 실행하기 위한 의존성 없는 Python 3.11 MVP입니다. 현재 더미 어댑터는 끝까지 실제 실행되며, MAPDL 및 Fluent 2021 R1 포트는 승인할 입력과 체크섬, 실행 파일, 라이선스와 Golden Case가 확정되기 전에는 실행을 거부합니다.

## 구현된 경계

- 버전 1.0.0 manifest/profile JSON Schema와 별도의 표준 라이브러리 검증기
- manifest.json.ready 마커를 마지막에 쓰는 안정성 검사 Hot Folder
- 동일 submission ID와 동일 hash는 중복 접수, 다른 hash는 격리
- SQLite migration, WAL, append-only 작업/시도 전이·이벤트·아티팩트·archive operation·outbox 기록
- 더미 성공, 선언 실패, hang timeout, 비정상 crash 실행과 재기동 복구
- 작업별 UUID 격리 경로, stdout/stderr 보존, 프로세스 트리 종료
- CPU, 메모리, 라이선스 feature 용량 gate와 dispatcher pause/resume
- bounded poll interval, singleton lock, signal/stop-marker 종료를 갖는 persistent agent
- resource/license/disk gate 대기를 공학 실패와 분리하는 WAITING_RESOURCE 상태
- content-addressed 불변 로컬 아티팩트, SHA-256, provenance record 및 무결성 검증
- 로컬 immutable commit 이후에만 별도 실행되는 NAS archive route
- NAS staging copy, SHA-256 재검증, atomic replace와 content-addressed idempotency
- archive BLOCKED/RETRY/FAILED/SUCCEEDED 상태와 analysis terminal 상태의 완전한 분리
- 수신자 allowlist를 발송 직전에 재검사하는 SMTP outbox와 fake sender
- TLS 필수, wincred credential_ref 필수, 두 개의 명시적 enable switch가 필요한 live SMTP 포트
- CPU/RAM/disk, queue, recent error, agent, provider 상태를 한 번에 보여 주는 health
- 절대 경로·SHA-256·30초 이하 timeout·이중 gate가 필요한 선택적 lmutil/lmstat health probe
- 기본 dry-run/disabled Windows Task Scheduler 관리 스크립트
- submit, list, show, cancel, retry, pause, resume, drain, archive, archive-retry, agent, agent-stop, verify, health CLI

## 빠른 확인

패키지 루트에서 다음을 실행합니다.

    py -3.11 -m venv .venv
    .venv\Scripts\python.exe -m pip install -e .
    .venv\Scripts\mecar-analysis.exe --runtime-root C:\MECarRuntime\ansys-automation submit examples\manifests\valid-dummy.json
    .venv\Scripts\mecar-analysis.exe --runtime-root C:\MECarRuntime\ansys-automation drain --max-jobs 1
    .venv\Scripts\mecar-analysis.exe --runtime-root C:\MECarRuntime\ansys-automation show dummy-success-001
    .venv\Scripts\mecar-analysis.exe --runtime-root C:\MECarRuntime\ansys-automation verify --job-id dummy-success-001

개발 트리에서 설치 없이 실행할 때는 src를 PYTHONPATH에 추가할 수 있습니다.

    $env:PYTHONPATH = (Resolve-Path src).Path
    py -3.11 -m mecar_automation --runtime-root C:\MECarRuntime\ansys-automation health

## Hot Folder 계약

런타임 root 아래 hotfolder\incoming에 먼저 job.json을 완전히 쓴 뒤, 마지막 원자적 commit 표시로 job.json.ready를 생성합니다. Agent는 두 파일의 나이와 크기/수정 시각이 안정된 경우에만 읽습니다.

- 정상 또는 동일 hash 재접수: hotfolder\accepted 아래로 이동하고 receipt 생성
- schema/profile 오류, 동일 ID의 다른 hash: hotfolder\quarantine 아래 원본과 redacted receipt 보존
- 아직 복사 중인 파일: 건드리지 않고 DEFERRED
- ready만 있는 경우: READY_WITHOUT_MANIFEST로 격리

## 기본 안전 설정

config\app.example.json은 solver 실행, 원격 발송, NAS 접근을 모두 끕니다. 아래 조건을 모두 만족하지 않으면 외부 동작은 일어나지 않습니다.

- MAPDL/Fluent: profile enabled, profile external_execution_enabled, machine external_execution_enabled가 모두 true
- MAPDL/Fluent: profile이 고정한 CPU/RAM/license reservation과 timeout ceiling을 machine capacity가 충족
- 승인 실행 파일, master input 및 부속 asset: 절대 경로의 파일이 존재하고 profile의 SHA-256과 정확히 일치
- ANSYS: profile release가 정확히 211이고 실행 파일이 존재
- SMTP: external_notification_enabled와 notification.external_send_enabled가 모두 true
- SMTP: STARTTLS 필수 또는 implicit TLS, Windows Credential Manager 참조, 현재 수신자 allowlist 통과
- 로컬 artifact: `artifacts.local_root`는 runtime root 내부의 상대 경로만 허용
- NAS: `external_archive_enabled`와 `artifacts.archive.external_enabled`가 모두 true인 승인 route만 접근
- NAS: route ID, 절대 root, archive 대상 role과 retry 한도를 config에서 고정하고, root fingerprint가 바뀌면 기존 intent를 차단
- Agent: `agent.enabled=true` 전에는 persistent loop 실행 거부, poll interval은 0.1~3600초 범위만 허용
- License probe: `external_license_probe_enabled`와 `license_probe.external_enabled`가 모두 true이고 승인 lmutil/lmstat hash가 일치할 때만 실행

manifest로 executable, APDL, journal 또는 임의 shell 명령을 바꿀 수 없습니다. solver 포트는 profile 작성자가 승인하고 hash를 고정한 master input과 부속 asset만 격리 작업 폴더로 복사합니다.
외부 solver의 CPU/RAM/license 요청도 manifest 값이 아니라 접수 시 동결된 승인 profile 값을 사용합니다.

## 테스트

    $env:PYTHONPATH = (Resolve-Path src).Path
    py -3.11 -m unittest discover -s tests -t . -v

테스트는 외부 ANSYS, SMTP, NAS, license server에 연결하지 않습니다. 더미 subprocess와 fake lmstat runner를 통해 success, failure, hang, crash, timeout 종료, graceful agent stop, stale recovery, dedupe/conflict quarantine, outbox retry/policy revoke, artifact corruption 및 외부 포트 fail-closed를 검증합니다.

## Persistent agent와 Windows Task Scheduler

`agent`는 Hot Folder scan, stale reconcile, queued solve, archive와 outbox drain을 한 cycle로 반복합니다. `Ctrl+C`, SIGTERM 또는 `agent-stop` marker를 받으면 현재 cycle을 정리한 뒤 종료합니다. 기본 예제는 `agent.enabled=false`, `external_execution_enabled=false`입니다.

    mecar-analysis --config C:\approved\app.json agent --once
    mecar-analysis --config C:\approved\app.json agent
    mecar-analysis --config C:\approved\app.json agent-stop

`scripts\Manage-MECarAutomationTask.ps1`은 인자 없이 실행하면 Plan만 출력합니다. Install/Uninstall은 `-Apply`가 없으면 변경하지 않고, 새 task는 `-EnableTask`가 없으면 Disabled 상태입니다. Install에는 절대 runtime/config/Python 경로, `agent.enabled=true`, 명시적 service account와 `-PromptForCredential`이 모두 필요합니다. credential을 script parameter나 예약 작업 command line으로 전달하는 기능은 없습니다.

    powershell -NoProfile -File scripts\Manage-MECarAutomationTask.ps1
    powershell -NoProfile -File scripts\Manage-MECarAutomationTask.ps1 -Action Install `
      -RuntimeRoot C:\MECarRuntime\ansys-automation -ConfigPath C:\approved\app.json `
      -PythonExe C:\approved-python\python.exe -ServiceAccount DOMAIN\svc-mecar

위 Install 예시는 dry-run입니다. 실제 등록은 검토 후 `-Apply -PromptForCredential`을 추가하며, `-EnableTask`는 마지막 별도 승인입니다.

## Health와 license probe

`health`는 DB integrity, CPU/RAM/disk reserve, queue state, 최근 analysis/archive/notification 오류, agent heartbeat, solver/profile, archive, notification과 license 상태를 JSON으로 반환합니다. lmutil은 기본 DISABLED이며 다음 값을 모두 채운 후 두 gate를 켜야만 subprocess를 시작합니다.

- `license_probe.adapter=lmutil`
- `license_probe.executable`, `license_probe.executable_sha256`
- `license_probe.server`의 명시적 `port@host`
- `license_probe.features`, `license_probe.timeout_sec`
- `license_probe.external_enabled=true`
- `external_license_probe_enabled=true`

경로/hash/timeout/출력 parse 중 하나라도 어긋나면 raw output을 노출하지 않고 ERROR로 닫힙니다. 이 probe는 관측용이며 engineering 판정을 만들지 않습니다. 실행 전 CPU/RAM/license/disk gate가 막힌 job은 FAILED 대신 WAITING_RESOURCE가 되고, 설정 또는 자원을 확보한 뒤 `retry JOB_ID`로 재개합니다.

## 선택적 NAS archive 활성화

`config\app.example.json`은 NAS adapter와 두 enable switch를 모두 끈 상태입니다. 운영 결정을 반영한 별도 config에서 다음 순서로 활성화합니다.

1. `artifacts.archive.adapter`를 `nas`로 바꾸고 승인된 고유 `route_id`, 절대 NAS root, 대상 artifact `roles`, `max_attempts`를 채웁니다.
2. 실행 계정의 최소 쓰기 ACL과 staging/rename 동작을 운영자가 확인합니다.
3. route의 `external_enabled`와 machine의 `external_archive_enabled`를 마지막에 모두 `true`로 바꿉니다.
4. 일반 `drain`은 analysis와 archive를 각각 처리합니다. archive만 처리하려면 `archive`를 실행합니다.
5. BLOCKED/FAILED operation의 원인을 수정한 뒤 `archive-retry --job-id JOB_ID`, 이어서 `archive`를 실행합니다. 이 명령은 solver attempt를 새로 만들지 않습니다.

로컬 immutable artifact가 확정된 시점이 analysis의 commit point입니다. NAS I/O가 실패해도 job의 SUCCEEDED/FAILED/TIMED_OUT/CANCELLED 상태는 바뀌지 않으며 `show`와 `verify`의 `archive_operations`/`archive_status`에서 별도로 확인합니다. 동일 checksum과 이름은 같은 content-addressed 목적지로 수렴하므로 receipt 기록 전 중단 후 재실행해도 중복 사본을 만들지 않습니다. 승인된 root를 바꾸려면 새 version의 route ID를 사용해야 합니다.

    mecar-analysis --config C:\approved\app.json archive --max-operations 100
    mecar-analysis --config C:\approved\app.json archive-retry --job-id JOB_ID
    mecar-analysis --config C:\approved\app.json archive --max-operations 100

## 운영 전 남은 외부 결정

docs\DECISIONS_PENDING.md의 값만 확정하면 코드 변경 없이 profile/config를 복사해 활성화할 수 있습니다. 다만 MAPDL/Fluent engineering acceptance가 검증됐다는 의미는 아니며, 각 Golden Case의 수동 기준 결과와 일치한 뒤에만 enable switch를 켜야 합니다.
