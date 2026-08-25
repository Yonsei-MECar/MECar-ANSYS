class AutomationError(RuntimeError):
    """Base error with a stable machine-readable code."""

    code = "AUTOMATION_ERROR"


class ValidationError(AutomationError):
    code = "VALIDATION_ERROR"


class SubmissionConflict(AutomationError):
    code = "SUBMISSION_ID_CONFLICT"


class InvalidTransition(AutomationError):
    code = "INVALID_STATE_TRANSITION"


class ExternalExecutionDisabled(AutomationError):
    code = "EXTERNAL_EXECUTION_DISABLED"


class ResourceUnavailable(AutomationError):
    code = "RESOURCE_UNAVAILABLE"


class ResourceCapacityUnavailable(ResourceUnavailable):
    code = "RESOURCE_CAPACITY_UNAVAILABLE"


class ResourceWaitTimeout(ResourceUnavailable):
    code = "RESOURCE_WAIT_TIMEOUT"


class DiskReserveUnavailable(ResourceUnavailable):
    code = "DISK_RESERVE_UNAVAILABLE"


class ArtifactCorruption(AutomationError):
    code = "ARTIFACT_CORRUPTION"


class PolicyRejected(AutomationError):
    code = "POLICY_REJECTED"
