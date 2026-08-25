from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bad-csv-only", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    logs = root / "logs"
    reports = root / "reports"
    artifacts = root / "artifacts"
    for path in (logs, reports, artifacts):
        path.mkdir(parents=True, exist_ok=True)
    if args.bad_csv_only:
        (reports / "residuals.csv").write_text("iteration,continuity\n400,1e-9\n", encoding="utf-8")
        (reports / "forces.csv").write_text("iteration,dragN\n400,1\n", encoding="utf-8")
        transcript = "; CSV files exist but no Fluent engineering evidence\n; MECAR_RUN_COMPLETE\n"
    else:
        rows = []
        for iteration in (300, 325, 350, 375, 400):
            rows.extend(
                [
                    f"{iteration} 9.0e-6 8.0e-7 7.0e-7 6.0e-6 5.0e-6 0:00:01 0",
                    f"; MECAR_FORCE_SAMPLE iteration={iteration}",
                    "Net (1 2 0) (2 3 0) (10 -20 0) (0 0 0) (0 0 0) (0 0 0)",
                ]
            )
        rows.extend(
            [
                "; MECAR_FINAL_FORCE",
                "Net (1 2 0) (2 3 0) (10 -20 0) (0 0 0) (0 0 0) (0 0 0)",
                "; MECAR_MASS_FLOW",
                "inlet 10.0",
                "outlet -9.999",
                "Net 0.001",
                "; MECAR_RUN_COMPLETE",
            ]
        )
        transcript = "\n".join(rows) + "\n"
    (logs / "fluent.trn").write_text(transcript, encoding="utf-8")
    png = b"\x89PNG\r\n\x1a\nFAKE"
    for name in ("vector.png", "velocity-contour.png", "pressure-contour.png"):
        (artifacts / name).write_bytes(png)
    (artifacts / "case.cas.h5").write_bytes(b"FAKE-CAS")
    (artifacts / "case.dat.h5").write_bytes(b"FAKE-DAT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

