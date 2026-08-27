from controlplane.errors import (
    ConfigurationError,
    ControlPlaneError,
    DependencyError,
    InternalError,
    TimeoutError,
    ValidationError,
)


def test_validation_error_shape():
    err = ValidationError("bad input")
    assert err.error_code == "VALIDATION_ERROR"
    assert err.http_status == 422
    assert err.retryable is False
    assert err.to_dict() == {
        "error_code": "VALIDATION_ERROR",
        "message": "bad input",
        "retryable": False,
    }


def test_dependency_and_timeout_errors_are_retryable():
    assert DependencyError("x").retryable is True
    assert TimeoutError("x").retryable is True


def test_internal_and_configuration_errors_are_not_retryable():
    assert InternalError("x").retryable is False
    assert ConfigurationError("x").retryable is False


def test_all_error_types_are_controlplane_errors():
    for cls in (ValidationError, ConfigurationError, InternalError, DependencyError, TimeoutError):
        assert issubclass(cls, ControlPlaneError)
