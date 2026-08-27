"""Common error contract.

docs/architecture/CONTROLPLANE_CROSS_CUTTING_SYSTEM_SPEC.md SS7 defines a
larger error-code taxonomy (MODEL_ERROR, RETRIEVAL_ERROR, ...). Layer 1
only needs the subset that can actually occur before any capability
exists: validation, configuration, dependency, timeout, and internal
errors. Later layers add error classes here rather than inventing a
parallel error model.
"""

from __future__ import annotations


class ControlPlaneError(Exception):
    """Base class for every error the API surfaces in a structured response."""

    error_code = "INTERNAL_ERROR"
    http_status = 500
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
        }


class ValidationError(ControlPlaneError):
    error_code = "VALIDATION_ERROR"
    http_status = 422
    retryable = False


class ConfigurationError(ControlPlaneError):
    error_code = "CONFIGURATION_ERROR"
    http_status = 500
    retryable = False


class InternalError(ControlPlaneError):
    error_code = "INTERNAL_ERROR"
    http_status = 500
    retryable = False


class DependencyError(ControlPlaneError):
    error_code = "DEPENDENCY_ERROR"
    http_status = 502
    retryable = True


class TimeoutError(ControlPlaneError):
    error_code = "TIMEOUT_ERROR"
    http_status = 504
    retryable = True
