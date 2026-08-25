from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from .support import PACKAGE_ROOT, PROFILES


SCRIPT = PACKAGE_ROOT / "scripts" / "Manage-MECarAutomationTask.ps1"


@unittest.skipUnless(os.name == "nt", "Windows Task Scheduler script")
class SchedulerScriptTests(unittest.TestCase):
    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            shell=False,
        )

    def test_default_plan_is_dry_run_and_requires_no_paths(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["Action"], "Plan")
        self.assertFalse(payload["Apply"])
        self.assertEqual(payload["DefaultTaskState"], "Disabled")
        self.assertFalse(payload["CredentialOnCommandLine"])

    def test_install_plan_requires_absolute_paths_service_account_and_agent_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "app.json"
            config.write_text(
                json.dumps(
                    {
                        "external_execution_enabled": False,
                        "agent": {"enabled": True, "poll_interval_sec": 5},
                    }
                ),
                encoding="utf-8",
            )
            result = self._run(
                "-Action",
                "Install",
                "-RuntimeRoot",
                str(root / "runtime"),
                "-ConfigPath",
                str(config),
                "-PythonExe",
                sys.executable,
                "-ProfilesRoot",
                str(PROFILES),
                "-ServiceAccount",
                "DOMAIN\\svc-mecar",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["Apply"])
            self.assertEqual(payload["DefaultTaskState"], "Disabled")
            self.assertFalse(payload["EnableTaskRequested"])
            self.assertFalse(payload["CredentialOnCommandLine"])
            self.assertNotIn("svc-mecar", payload["Arguments"])
            self.assertIn(" agent", payload["Arguments"])

            refused = self._run(
                "-Action",
                "Install",
                "-RuntimeRoot",
                str(root / "runtime"),
                "-ConfigPath",
                str(config),
                "-PythonExe",
                sys.executable,
                "-ProfilesRoot",
                str(PROFILES),
                "-ServiceAccount",
                "DOMAIN\\svc-mecar",
                "-Apply",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("PromptForCredential", refused.stderr)

    def test_script_has_no_credential_or_schtasks_command_line_port(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("[string]$Password", source)
        self.assertNotIn("schtasks", source.casefold())
        self.assertNotIn("/rp", source.casefold())
        self.assertIn("Get-Credential", source)
        self.assertIn("CredentialOnCommandLine = $false", source)


if __name__ == "__main__":
    unittest.main()
