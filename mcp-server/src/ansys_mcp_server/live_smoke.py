from __future__ import annotations

import json

from .backend import AnsysBackend
from .config import Settings


def main() -> None:
    backend = AnsysBackend(Settings.from_env())
    try:
        launch = backend.launch(nproc=1)
        result = backend.live_smoke()
        print(json.dumps({"launch": launch, "result": result}, indent=2))
    finally:
        backend.exit(force=True)


if __name__ == "__main__":
    main()
