from __future__ import annotations

import smtplib
import ssl
import os
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Callable, Protocol

from .db import QueueDatabase
from .errors import ExternalExecutionDisabled, PolicyRejected, ValidationError


class TransientSendError(RuntimeError):
    pass


class PermanentSendError(RuntimeError):
    pass


class Sender(Protocol):
    def send(self, payload: dict) -> str: ...


@dataclass(frozen=True)
class RecipientPolicy:
    version: str = "1"
    allowed_domains: frozenset[str] = field(default_factory=frozenset)
    allowed_addresses: frozenset[str] = field(default_factory=frozenset)
    max_recipients: int = 20

    def check(self, recipients: list[str]) -> None:
        if not recipients or len(recipients) > self.max_recipients:
            raise PolicyRejected("Recipient count violates policy")
        for address in recipients:
            canonical = address.strip().lower()
            domain = canonical.rsplit("@", 1)[-1] if "@" in canonical else ""
            if canonical not in self.allowed_addresses and domain not in self.allowed_domains:
                raise PolicyRejected(f"Recipient is not allowed by current policy: {address}")


class FakeSender:
    def __init__(self, failure: str | None = None):
        self.failure = failure
        self.sent: list[dict] = []

    def send(self, payload: dict) -> str:
        if self.failure == "transient":
            raise TransientSendError("fake transient failure")
        if self.failure == "permanent":
            raise PermanentSendError("fake permanent failure")
        self.sent.append(payload)
        return f"fake-{uuid.uuid4()}"


class WindowsCredentialResolver:
    """Reads a Windows Generic Credential without logging its secret blob."""

    def __call__(self, reference: str) -> str:
        if not reference.startswith("wincred://"):
            raise ValidationError("CLI live SMTP supports only wincred:// credential references")
        if os.name != "nt":
            raise ExternalExecutionDisabled("Windows Credential Manager is unavailable on this platform")
        target = reference[len("wincred://") :]
        if not target:
            raise ValidationError("Empty Windows Credential Manager target")
        import ctypes
        from ctypes import wintypes

        class Credential(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWrittenLow", wintypes.DWORD),
                ("LastWrittenHigh", wintypes.DWORD),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        pointer = ctypes.POINTER(Credential)()
        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        if not advapi32.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            error = ctypes.get_last_error()
            raise ExternalExecutionDisabled(f"Windows credential reference is unavailable (error {error})")
        try:
            credential = pointer.contents
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            try:
                value = blob.decode("utf-16-le")
            except UnicodeDecodeError:
                value = blob.decode("utf-8")
            if not value:
                raise ExternalExecutionDisabled("Windows credential contains an empty value")
            return value
        finally:
            advapi32.CredFree(pointer)


class SmtpSender:
    """Live sender requiring explicit enablement, TLS, and a secret reference resolver."""

    def __init__(
        self,
        config: dict,
        credential_resolver: Callable[[str], str],
        *,
        enabled: bool = False,
    ):
        self.config = config
        self.credential_resolver = credential_resolver
        self.enabled = enabled
        if config.get("security") not in {"starttls_required", "implicit_tls"}:
            raise ValidationError("SMTP security must require STARTTLS or implicit TLS")
        for field in ("username_ref", "password_ref"):
            reference = config.get(field, "")
            if not isinstance(reference, str) or not reference.startswith("wincred://"):
                raise ValidationError(f"SMTP {field} must be a wincred:// reference")
        if "password" in config or "username" in config:
            raise ValidationError("Literal SMTP credentials are forbidden")

    def send(self, payload: dict) -> str:
        if not self.enabled or not self.config.get("external_send_enabled", False):
            raise ExternalExecutionDisabled("Live SMTP sending is disabled")
        message = EmailMessage()
        message["From"] = self.config["header_from"]
        message["To"] = ", ".join(payload["to"])
        message["Subject"] = payload["subject"]
        message.set_content(payload["text"])
        if payload.get("html"):
            message.add_alternative(payload["html"], subtype="html")
        username = self.credential_resolver(self.config["username_ref"])
        smtp_credential_blob = self.credential_resolver(self.config["password_ref"])
        context = ssl.create_default_context()
        host = self.config["host"]
        port = int(self.config["port"])
        try:
            if self.config["security"] == "implicit_tls":
                client_factory = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
            else:
                client_factory = smtplib.SMTP(host, port, timeout=20)
            with client_factory as client:
                if self.config["security"] == "starttls_required":
                    client.ehlo()
                    client.starttls(context=context)
                    client.ehlo()
                client.login(username, smtp_credential_blob)
                refused = client.send_message(message, from_addr=self.config["envelope_from"])
            if refused:
                raise PermanentSendError("One or more recipients were refused")
            return message.get("Message-ID") or f"smtp-{uuid.uuid4()}"
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientSendError(f"SMTP_{exc.smtp_code}") from exc
            raise PermanentSendError(f"SMTP_{exc.smtp_code}") from exc
        except smtplib.SMTPException as exc:
            raise PermanentSendError(type(exc).__name__) from exc
        except (TimeoutError, OSError, smtplib.SMTPServerDisconnected) as exc:
            raise TransientSendError(type(exc).__name__) from exc


class OutboxDrainer:
    def __init__(self, database: QueueDatabase, sender: Sender, policy: RecipientPolicy):
        self.database = database
        self.sender = sender
        self.policy = policy

    def drain(self, limit: int = 100) -> list[dict]:
        results: list[dict] = []
        for message in self.database.claim_outbox(limit):
            payload = message["payload"]
            try:
                self.policy.check(payload.get("to", []))
                receipt = self.sender.send(payload)
                state, error = "SENT", None
            except PolicyRejected as exc:
                receipt, state, error = None, "POLICY_REVOKED", exc.code
            except TransientSendError:
                receipt, state, error = None, "RETRY", "SMTP_TRANSIENT"
            except (PermanentSendError, ExternalExecutionDisabled):
                receipt, state, error = None, "PERMANENT", "SMTP_PERMANENT"
            self.database.record_outbox_delivery(
                message["message_id"], state, receipt=receipt, error_code=error
            )
            results.append({"message_id": message["message_id"], "state": state, "error_code": error})
        return results
