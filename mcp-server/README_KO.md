# MECar Ansys 2021 R1 MCP Server

Ansys 2021 R1의 MAPDL gRPC와 Workbench 배치 실행을 Codex 같은 MCP 클라이언트에 연결하는 Windows용 독립 패키지입니다. 최신 PyMechanical을 2021 R1에 억지로 연결하지 않고, 다음 두 경로를 분리합니다.

- MAPDL: PyMAPDL gRPC로 실행, APDL, 메시, 해석, 응력·변위 결과 조회
- Workbench/Mechanical: 기존 `.wbpj`, `.wbjn`, `.py`를 `RunWB2.exe -B`로 실행

## 제공 도구

| MCP 도구 | 기능 |
|---|---|
| `ansys_status` | 설치 경로, Workbench, 연결 상태 확인 |
| `launch_mapdl` / `close_mapdl` | MAPDL gRPC 세션 시작·종료 |
| `run_apdl` | 연결된 MAPDL에 APDL 명령 실행 |
| `open_database` | 작업 루트 안의 MAPDL DB 재개 |
| `mesh` | 현재 선택된 모든 체적 메시 생성 |
| `solve` | 현재 모델 해석 |
| `get_stress` | 마지막 결과의 최대 nodal von Mises 응력 |
| `get_displacement` | 마지막 결과의 최대 총변위 |
| `export_results` | 응력·변위 요약을 JSON/CSV로 저장 |
| `open_project` | 임시 journal을 생성해 Workbench 프로젝트를 `-B -R`로 배치 로드 |
| `run_workbench_script` | Workbench journal/스크립트 배치 실행 |

`mesh`는 이미 요소 종류·재료·형상·속성이 정의된 MAPDL 체적 모델을 대상으로 합니다. Mechanical 트리의 Named Selection이나 하중을 일반화해 자동 생성하지는 않습니다. 해당 작업은 프로젝트별 ACT/Workbench 스크립트로 작성한 뒤 `run_workbench_script`로 실행하십시오.

## 설치

PowerShell 5.1 이상과 Python 3.10~3.12가 필요합니다. Ansys 2021 R1 기본 설치 위치는 `C:\Program Files\ANSYS Inc\v211`입니다.

런타임은 검증된 `mcp==1.29.0`, `ansys-mapdl-core==0.73.2`를 사용합니다. 빌드·검증 도구까지 포함한 모든 전이 의존성은 `requirements.lock.txt`에 정확한 버전과 PyPI SHA-256으로 고정되어 있습니다. 설치 스크립트는 pip 자체를 업그레이드하지 않고 이 잠금 파일을 `--require-hashes`로 먼저 설치한 뒤, 로컬 패키지를 `--no-deps --no-build-isolation`으로 설치합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd ".\Projects\MECar-ANSYS\mcp-server"
$projectRoot = (Resolve-Path '..\..\..').Path
.\install.ps1 -ProjectRoot $projectRoot
```

`install.ps1`은 잠금 의존성 설치에도 `--only-binary=:all:`을 적용하므로, 소스 배포본(sdist)의 임의 빌드가 발생하지 않습니다.

기본 설치는 잠금 파일에 기록된 배포 파일만 PyPI에서 받습니다. 사설 index나 범위 기반 재해석은 사용하지 않습니다.

MAPDL 2021 R1의 작업 폴더 인코딩 문제를 피하기 위해 해석 실행 폴더는 기본적으로
공백과 비 ASCII 문자가 없는 `C:\MECarRuntime\ansys`를 사용합니다. 다른 전용 폴더를
사용하려면 설치와 검증에 같은 `-RunLocation` 값을 전달합니다.

스크립트는 OneDrive 파일 잠금을 피하기 위해 `%LOCALAPPDATA%\MECar\ansys-mcp-server\venv-py311`에 전용 가상환경을 만들고 패키지를 설치한 뒤, 프로젝트의 `.codex\config.toml`에서 `ansys_2021r1` 항목만 갱신합니다. 기존 설정은 타임스탬프가 붙은 파일로 백업합니다. 원시 APDL과 Workbench 스크립트는 기본 비활성화되며, 승인된 개발 환경에서만 설치 옵션으로 따로 활성화하십시오. 설치 후 Codex를 다시 시작하십시오.

다른 위치의 Ansys를 쓰면 다음처럼 지정합니다.

```powershell
.\install.ps1 -ProjectRoot $projectRoot -AnsysRoot "E:\ANSYS Inc\v211"
```

가상환경 위치도 바꾸려면 설치와 검증에 같은 `-VenvPath`를 전달하십시오.

원시 코드 실행 도구는 기본적으로 꺼져 있습니다. 승인된 개발 환경에서 필요한 기능만 다음처럼 켭니다.

```powershell
.\install.ps1 -ProjectRoot $projectRoot -EnableRawApdl
.\install.ps1 -ProjectRoot $projectRoot -EnableWorkbenchScripts
```

### 오프라인 설치

인터넷이 되는 Windows x64 PC에서 대상 PC와 같은 Python minor version으로 wheelhouse를 한 번 준비합니다. 다음 예시는 기본 설치 우선순위인 Python 3.11용입니다.

```powershell
$wheelhouse = 'C:\MECarTools\ansys-mcp-wheelhouse-py311'
New-Item -ItemType Directory -Force $wheelhouse | Out-Null
py -3.11 -m pip download --disable-pip-version-check --require-hashes `
  --only-binary=:all: -r .\requirements.lock.txt -d $wheelhouse
```

패키지 폴더와 wheelhouse를 대상 PC로 함께 옮긴 뒤 다음처럼 설치합니다. `-Offline`은 `--no-index`를 강제하므로 wheelhouse에 파일이 하나라도 빠지면 온라인으로 우회하지 않고 실패합니다.

```powershell
.\install.ps1 -ProjectRoot $projectRoot `
  -Wheelhouse 'D:\MECarOffline\ansys-mcp-wheelhouse-py311' -Offline
```

Python 3.10 또는 3.12를 쓰는 PC는 wheelhouse도 같은 minor version으로 준비합니다. `-Wheelhouse`만 지정하고 `-Offline`을 생략하면 로컬 wheelhouse를 우선 후보로 제공하되, 누락 파일은 공개 index에서 받을 수 있습니다.

### 잠금 파일 갱신

의존성 변경을 승인한 경우에만 다음 명령으로 잠금을 재생성하고 전체 검증을 다시 수행합니다. Python 3.10을 최소 호환 기준으로 사용하므로 생성된 정확한 버전은 3.10~3.12 모두에서 설치 가능해야 합니다.

```powershell
uv pip compile pyproject.toml --extra dev --python-version 3.10 `
  --python-platform x86_64-pc-windows-msvc --generate-hashes `
  --exclude-newer 2026-08-23T00:00:00Z -o requirements.lock.txt
```

## 검증

기본 검증은 Ansys 라이선스를 사용하지 않습니다.

```powershell
.\verify.ps1
```

실제로 MAPDL을 한 번 시작하고 종료하는 gRPC·라이선스 검증:

```powershell
.\verify.ps1 -LaunchMapdl
```

## 배포

가상환경, 캐시, 해석 결과는 제외하고 폴더를 ZIP으로 묶습니다.

```powershell
.\build-package.ps1
```

생성된 `dist\mecar-ansys-mcp-server-0.1.1.zip`과 `.sha256` 파일을 함께 전달하십시오. ZIP에는 해시 잠금 파일과 전체 잠금 검증기도 포함됩니다. 다른 PC에 풀고 온라인 `install.ps1`을 실행하거나, 위에서 만든 wheelhouse와 함께 `-Offline`으로 설치하면 됩니다. 설치와 `verify.ps1`은 잠금의 83개 버전을 전부 비교하고 `pip check`도 통과해야 합니다. Ansys, 라이선스 및 대용량 Python wheelhouse는 ZIP에 포함되지 않습니다. 호환성 근거와 출처는 `SOURCES.md`에 기록되어 있습니다.

## 안전 경계

- 구조화된 도구에 전달하는 파일 경로는 `ANSYS_MCP_WORK_ROOT` 안으로 제한됩니다.
- `run_apdl`의 `/SYS`, `/INPUT`, `/DELETE` 등과 Workbench `.py`/`.wbjn`은 임의 명령 실행 기능이므로 작업 루트 밖의 파일에도 접근하거나 변경할 수 있습니다.
- 원시 APDL과 Workbench 스크립트는 기본 비활성화됩니다.
- 승인된 개발 환경에서만 설치 시 `-EnableRawApdl` 또는 `-EnableWorkbenchScripts`를 명시합니다.
- 단위는 자동 변환하지 않습니다. 모델에서 사용 중인 일관 단위계를 그대로 사용합니다.

## 알려진 한계

- 2021 R1용 최신 PyMechanical 직접 제어기가 아닙니다.
- Workbench의 `open_project`는 프로젝트를 배치로 열고 갱신하는 통로입니다. 범용 Mechanical 트리 편집은 프로젝트별 ACT 스크립트가 필요합니다.
- `get_stress`는 PyMAPDL 결과 파일의 nodal equivalent stress를 사용합니다. 검증·인증용 결과에는 반드시 Mechanical/MAPDL 원본 결과와 수동 교차검증을 수행하십시오.
- 일반 최대값 조회는 정적 및 과도 해석용입니다. 모달·좌굴·조화 해석은 정규화/복소 진폭의 의미가 달라 분석별 APDL 후처리를 사용해야 합니다.
