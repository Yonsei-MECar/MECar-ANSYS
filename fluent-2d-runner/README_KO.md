# MECar Fluent 2021 R1 2D Runner

Fluent 26.1 case template 없이 Gmsh 메시부터 Fluent 2021 R1 TUI 21.1 case를 매번 새로 구성하는 fail-closed 러너다. 입력 검증, case 격리, resume, 고정 iteration, 제한된 자동 연장, 원시 힘과 계수 정의, 공학 수렴 게이트, report/CSV/PNG/case-data 산출물을 한 계약으로 묶는다.

## 현재 검증 상태

2026-08-23 로컬 ANSYS Fluent 2021 R1 Build 10179에서 `golden-naca0012-h080-a0`를 실제 headless `-gu` 모드로 검증했다.

- Gmsh 4.13.1로 24,216 nodes / 41,726 mixed cells 생성(익형 경계층 18층 포함)
- v211 `/mesh/check` 통과, non-positive cell 0
- k-omega SST, 12.5 m/s inlet, freestream 속도의 moving ground, 1 m span 가정
- 100회 1차 + 300회 2차, 총 400 iteration 완료
- solver process와 engineering gate 통과
- mass imbalance ratio `3.2690e-11`, 마지막 5개 표본 relative range는 drag `1.9680e-6`, downforce `4.9031e-6`
- raw force `Fx=0.71138992 N`, `Fy=-8.2396914 N`
- 정의상 계산값 `Cd=0.0158155293`, `C_DF=0.1831837602`
- resolved manifest SHA-256 `23ea60cedf17911d89e4beed7ecc6b543730aaa4221b7d45e35f8d62c3cb383b`
- Fluent ASCII mesh SHA-256 `3630bd7d46fb3cbfde2126a1643943d718f97e63d68ad7dcdde5f6ea69ac53c2`
- case/data, residual/force CSV, HTML/JSON report, velocity/pressure/vector PNG 생성
- 실행 종료 후 Fluent/cortex orphan process 없음

위 계수는 자동화 파이프라인의 재현 가능한 결과지만 아직 **권위 있는 공력 기준값이 아니다**. 같은 좌표·mesh·physics·reference로 수행한 승인된 수동 GUI 결과와 사용자가 정한 허용오차가 manifest에 입력되어야 `authority.authoritative=true`가 된다.

## 설치 및 확인

Gmsh wheel은 `4.13.1` Windows x86-64로 고정되어 있고 SHA-256은 `00F3C86B3146C1AF1259E695ED646880C9DA0C2DED2D1E48B240A1D3D194BAE6`이다. 설치 스크립트는 기본적으로 다운로드하지 않는다. wheel이 없을 때만 사용자가 명시적으로 `-AllowDownload`를 지정할 수 있으며, 설치 전에 checksum을 검사한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_gmsh.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

환경과 manifest를 확인한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 verify-environment
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 validate .\config\golden-naca0012.json
```

메시와 journal까지만 준비하거나 실제 해석을 실행한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 prepare .\config\golden-naca0012.json --runtime-root C:\MECarRuntime\fluent
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 run .\config\golden-naca0012.json --runtime-root C:\MECarRuntime\fluent
```

정상 완료된 동일 manifest는 artifact checksum을 확인한 뒤 resume에서 건너뛴다. CSV가 존재하기만 하거나 Fluent가 exit code 0만 반환한 경우에는 성공하지 않는다. 완료 marker, fatal TUI 진단 부재, 잔차, mass balance, force plateau, 유한 force/coefficient, 전체 artifact 계약을 모두 통과해야 한다.

`--no-resume`은 의도적으로 메시를 다시 생성한다. Gmsh의 비정형 삼각화는 동일 설정에서도 세부 연결이 달라질 수 있으므로, 승인 baseline 비교에서는 report에 기록된 `fluentMeshSha256`이 같은 실행끼리 비교하거나 승인된 `mesh.msh` artifact를 함께 동결해야 한다.

## 168-case sweep

기본 plan은 4 profiles × 6 heights × 7 angles = 168 cases를 정의한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 generate-sweep .\config\golden-naca0012.json .\config\sweep-plan.example.json C:\MECarRuntime\fluent\sweep-plan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run.ps1 sweep C:\MECarRuntime\fluent\sweep-plan\manifests --runtime-root C:\MECarRuntime\fluent
```

현재 NACA6412/NACA6409는 해석식 generator로 84 manifests를 만들 수 있다. S1223/E423 84 cases는 승인된 DAT 원본, 출처, license와 SHA-256이 없으므로 생성 단계에서 차단된다. 파일을 `sweep-plan/manifests/inputs/airfoils/` 아래에 놓고 plan의 `source`, `license`, `sha256`을 채우면 같은 명령으로 168개가 모두 생성된다. 다른 익형으로 조용히 대체하지 않는다.

각 manifest는 독립 case다. 한 case 실패가 다음 case를 중단하지 않으며, 재실행은 checksum까지 유효한 완료 case만 건너뛴다. `autoExtend=true`이면 engineering gate가 실패한 경우에만 `extensionChunk` 단위로 연장하고 `hardMaximum`에서 반드시 멈춘다.

## 경로와 산출물 계약

source DAT 경로는 manifest 기준 상대경로만 허용한다. `..`, drive-letter absolute path와 root path를 거부한다. 실행 파일은 CLI/`AWP_ROOT211`에서 해석하고 실제 console banner가 `ANSYS Fluent 2021 R1 / Build 10179`인지 다시 검사한다. 모든 계산 산출물은 짧은 runtime root 아래에 격리된다.

```text
C:\MECarRuntime\fluent\cases\<caseId>\
  resolved-manifest.json
  input\mesh.msh
  journal\run.jou, extension-*.jou
  logs\console-*.log, fluent*.trn
  reports\report.json, summary.html, residuals.csv, forces.csv, mesh-quality.json
  artifacts\case.cas.h5, case.dat.h5, velocity-contour.png,
            pressure-contour.png, vector.png
```

좌표와 부호는 고정되어 있다.

- `+x`: freestream 방향
- `+y`: 위쪽
- raw force: fluid가 body에 가하는 힘
- `q=0.5*rho*V^2`, `Cd=Fx/(q*A)`, `C_DF=-Fy/(q*A)`
- 2D reference area는 manifest의 1 m span 가정을 포함한 `A=chord*1 m`

기본 gate는 mesh 양의 면적·최소 quality `0.01`, continuity/k residual `1e-3`, omega `1e-4`, x/y velocity `1e-5`, mass imbalance ratio `1e-3`, 마지막 drag/downforce 표본 각각의 relative range `1%`를 동시에 요구한다. 이 값은 `config/golden-naca0012.json`에 명시되며 결과를 맞추려고 실행 중에 자동 완화하지 않는다.

## 사용자가 나중에 결정할 항목

권위 계수 승격에는 아래 네 값만 채우면 된다.

```json
"authority": {
  "manualBaselineId": "approved-gui-run-id",
  "manualCd": 0.0158,
  "manualCDF": 0.1832,
  "manualTolerance": 0.005
}
```

위 숫자는 형식 예시다. 실제 승인 GUI 값과 프로젝트가 결정한 절대 허용오차로 교체해야 한다.

S1223/E423 sweep에는 원본 DAT, 정확한 출처, 사용/재배포 조건, SHA-256이 필요하다. 이 외의 실행·resume·수렴·산출물 경로는 이미 구현되어 있다.
