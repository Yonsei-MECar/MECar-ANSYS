class Fluent2DError(RuntimeError):
    """Base error with a stable, machine-readable error code."""

    code = "FLUENT2D_ERROR"

    def __init__(self, message: str, *, hint: str | None = None):
        super().__init__(message)
        self.hint = hint


class ManifestError(Fluent2DError):
    code = "INVALID_MANIFEST"


class InputError(Fluent2DError):
    code = "MISSING_OR_INVALID_INPUT"


class EnvironmentError(Fluent2DError):
    code = "ENVIRONMENT_UNAVAILABLE"


class SolverError(Fluent2DError):
    code = "SOLVER_FAILED"


class EngineeringGateError(Fluent2DError):
    code = "ENGINEERING_GATE_FAILED"

