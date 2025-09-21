"""Tests pour les exceptions personnalisées."""

import pytest
from custom_connectors.core.exceptions import (
    ConnectorError,
    ConfigurationError,
    APIError,
    RetryableError,
    AuthenticationError,
    RateLimitError,
    DataValidationError,
)


class TestConnectorError:
    """Tests pour ConnectorError."""

    def test_basic_error(self) -> None:
        """Test création d'erreur basique."""
        error = ConnectorError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code is None
        assert error.context == {}

    def test_error_with_code(self) -> None:
        """Test erreur avec code d'erreur."""
        error = ConnectorError("Test error", error_code="TEST_001")
        assert str(error) == "[TEST_001] Test error"
        assert error.error_code == "TEST_001"

    def test_error_with_context(self) -> None:
        """Test erreur avec contexte."""
        context = {"user_id": "123", "action": "fetch"}
        error = ConnectorError("Test error", context=context)
        assert "user_id=123" in str(error)
        assert "action=fetch" in str(error)
        assert error.context == context

    def test_error_with_all_params(self) -> None:
        """Test erreur avec tous les paramètres."""
        context = {"key": "value"}
        error = ConnectorError(
            "Test error",
            error_code="TEST_001",
            context=context,
        )
        error_str = str(error)
        assert "[TEST_001]" in error_str
        assert "Test error" in error_str
        assert "key=value" in error_str


class TestConfigurationError:
    """Tests pour ConfigurationError."""

    def test_missing_config(self) -> None:
        """Test erreur de configuration manquante."""
        error = ConfigurationError(
            "Missing configuration",
            missing_config="api_key",
        )
        assert error.error_code == "CONFIG_ERROR"
        assert error.context["missing_config"] == "api_key"

    def test_invalid_value(self) -> None:
        """Test erreur de valeur invalide."""
        error = ConfigurationError(
            "Invalid value",
            invalid_value="invalid_url",
        )
        assert error.context["invalid_value"] == "invalid_url"


class TestAPIError:
    """Tests pour APIError."""

    def test_basic_api_error(self) -> None:
        """Test erreur API basique."""
        error = APIError("API call failed")
        assert error.error_code == "API_ERROR"

    def test_api_error_with_details(self) -> None:
        """Test erreur API avec détails."""
        error = APIError(
            "API call failed",
            status_code=500,
            response_body="Internal server error",
            endpoint="/api/customers",
        )
        assert error.context["status_code"] == 500
        assert error.context["response_body"] == "Internal server error"
        assert error.context["endpoint"] == "/api/customers"

    def test_api_error_truncates_large_response(self) -> None:
        """Test que les réponses longues sont tronquées."""
        large_response = "x" * 1000
        error = APIError("API call failed", response_body=large_response)
        assert len(error.context["response_body"]) == 500


class TestRetryableError:
    """Tests pour RetryableError."""

    def test_retryable_error(self) -> None:
        """Test erreur retryable."""
        error = RetryableError("Temporary failure")
        assert error.error_code == "RETRYABLE_ERROR"

    def test_retryable_error_with_retry_info(self) -> None:
        """Test erreur retryable avec infos de retry."""
        error = RetryableError(
            "Temporary failure",
            retry_after=30,
            max_retries=3,
        )
        assert error.context["retry_after"] == 30
        assert error.context["max_retries"] == 3


class TestAuthenticationError:
    """Tests pour AuthenticationError."""

    def test_auth_error(self) -> None:
        """Test erreur d'authentification."""
        error = AuthenticationError("Invalid credentials")
        assert error.error_code == "AUTH_ERROR"
        assert error.context["status_code"] == 401

    def test_auth_error_custom_status(self) -> None:
        """Test erreur d'auth avec status personnalisé."""
        error = AuthenticationError(
            "Token expired",
            status_code=403,
        )
        assert error.context["status_code"] == 403


class TestRateLimitError:
    """Tests pour RateLimitError."""

    def test_rate_limit_error(self) -> None:
        """Test erreur de rate limit."""
        error = RateLimitError("Rate limit exceeded")
        assert error.error_code == "RATE_LIMIT_ERROR"

    def test_rate_limit_with_retry_after(self) -> None:
        """Test rate limit avec retry_after."""
        error = RateLimitError(
            "Rate limit exceeded",
            retry_after=60,
        )
        assert error.context["retry_after"] == 60


class TestDataValidationError:
    """Tests pour DataValidationError."""

    def test_validation_error(self) -> None:
        """Test erreur de validation."""
        error = DataValidationError("Invalid data format")
        assert error.error_code == "VALIDATION_ERROR"

    def test_validation_error_with_fields(self) -> None:
        """Test erreur de validation avec champs invalides."""
        invalid_fields = ["email", "phone"]
        error = DataValidationError(
            "Invalid fields",
            invalid_fields=invalid_fields,
        )
        assert error.context["invalid_fields"] == invalid_fields
