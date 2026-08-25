# 로컬 운영 절차

## 설치와 초기 확인

1. Python 3.11 venv를 만들고 editable install을 수행합니다.
2. health 명령에서 database integrity가 ok인지 확인합니다.
3. app.example.json을 운영 경로로 복사하되 외부 enable 값은 false로 유지합니다.
4. valid-dummy manifest를 새 submission ID로 복사해 submit하고 drain합니다.
5. show에서 SUCCEEDED, attempt 1개, manifest_snapshot/solver_result/summary_report artifact를 확인합니다.
6. verify에서 모든 artifact valid가 true인지 확인합니다.

## 일상 명령

    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation submit request.json
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation list
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation show JOB_ID
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation cancel JOB_ID
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation retry JOB_ID
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation pause
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation resume
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation drain
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation --config C:\approved\app.json agent
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation --config C:\approved\app.json agent-stop
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation archive
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation verify
    mecar-analysis --runtime-root C:\MECarRuntime\ansys-automation health

drain과 agent cycle은 Hot Folder scan, stale reconcile, queued solve, archive, outbox 순서로 수행합니다. 기본 fake sender와 disabled license probe는 네트워크를 사용하지 않습니다. agent 종료는 Ctrl+C/SIGTERM 또는 agent-stop을 사용합니다.

## 장애 처리

- FILE_NOT_STABLE: 복사가 끝날 때까지 기다립니다. 파일을 고치거나 이동하지 않습니다.
- SUBMISSION_ID_CONFLICT: quarantine receipt와 두 manifest의 운영상 identity를 검토합니다. 기존 DB를 수정하지 말고 새 submission ID를 발급합니다.
- PROCESS_TIMEOUT: timeout 원인과 stdout/stderr를 보고 retry 여부를 결정합니다.
- PROCESS_CRASH: solver log와 Windows Event Viewer를 확인합니다.
- STALE_PROCESS: 재기동 reconcile 결과가 QUEUED인지 FAILED인지 확인합니다.
- RESOURCE_CAPACITY_UNAVAILABLE/DISK_RESERVE_UNAVAILABLE/RESOURCE_WAIT_TIMEOUT: 공학 실패가 아니라 WAITING_RESOURCE입니다. capacity/license/disk 원인을 고친 뒤 retry합니다.
- ARTIFACT_CORRUPTION: 원본을 덮어쓰지 말고 스토리지를 격리한 뒤 백업/원본 attempt에서 복구합니다.
- SMTP_TRANSIENT: solver를 재실행하지 않고 outbox만 다음 drain에서 재시도합니다.
- POLICY_REVOKED: 현재 수신자 allowlist를 검토하고 새 알림 이벤트를 생성하는 운영 결정을 합니다.
- LICENSE_PROBE_*: raw lmstat 출력을 신뢰하지 말고 executable hash, 두 gate, timeout, feature 이름과 서버 상태를 확인합니다. probe 실패는 solver engineering 결과를 변경하지 않습니다.

## Task Scheduler

`scripts\Manage-MECarAutomationTask.ps1`의 기본 Action은 Plan입니다. Install/Uninstall은 `-Apply` 전에는 변경이 없고, Install 후 task는 기본 Disabled입니다. 실제 설치 시 절대 경로, 전용 service account, `agent.enabled=true`, `-PromptForCredential`을 요구합니다. 비밀번호 parameter는 없으며 예약 작업 argument에는 runtime/config/profile 경로와 `agent` 명령만 들어갑니다. 설치 후 Status와 Health를 확인하고 마지막에만 `-EnableTask`를 승인합니다.

## 백업

Agent를 pause한 뒤 state\automation.sqlite3와 artifacts 전체를 같은 시점 snapshot으로 백업합니다. SQLite WAL/SHM이 존재할 수 있으므로 파일 복사 전 health 확인과 checkpoint 정책을 운영 절차에 추가해야 합니다. 복구 연습은 별도 runtime root에서 수행하고 원본 DB에 UPDATE/DELETE를 시도하지 않습니다.
