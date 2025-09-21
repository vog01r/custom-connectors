"""Exceptions personnalisées pour les connecteurs."""

from typing import Any, Dict, Optional


class ConnectorError(Exception):
    """Exception de base pour tous les connecteurs."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialise l'exception avec message et contexte optionnel.
        
        Args:
            message: Message d'erreur descriptif
            error_code: Code d'erreur optionnel pour classification
            context: Contexte additionnel pour le debugging
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}

    def __str__(self) -> str:
        """Représentation string de l'exception."""
        base_msg = self.message
        if self.error_code:
            base_msg = f"[{self.error_code}] {base_msg}"
        
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            base_msg += f" (context: {context_str})"
            
        return base_msg


class ConfigurationError(ConnectorError):
    """Erreur de configuration du connecteur."""

    def __init__(
        self,
        message: str,
        missing_config: Optional[str] = None,
        invalid_value: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise l'erreur de configuration.
        
        Args:
            message: Message d'erreur
            missing_config: Nom de la configuration manquante
            invalid_value: Valeur de configuration invalide
            **kwargs: Arguments supplémentaires pour ConnectorError
        """
        context = kwargs.pop("context", {})
        if missing_config:
            context["missing_config"] = missing_config
        if invalid_value:
            context["invalid_value"] = invalid_value
            
        super().__init__(
            message=message,
            error_code="CONFIG_ERROR",
            context=context,
            **kwargs,
        )


class APIError(ConnectorError):
    """Erreur liée aux appels API externes."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        endpoint: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise l'erreur API.
        
        Args:
            message: Message d'erreur
            status_code: Code de statut HTTP
            response_body: Corps de la réponse d'erreur
            endpoint: Endpoint API concerné
            **kwargs: Arguments supplémentaires pour ConnectorError
        """
        context = kwargs.pop("context", {})
        if status_code:
            context["status_code"] = status_code
        if response_body:
            context["response_body"] = response_body[:500]  # Limiter la taille
        if endpoint:
            context["endpoint"] = endpoint
            
        super().__init__(
            message=message,
            error_code="API_ERROR",
            context=context,
            **kwargs,
        )


class RetryableError(ConnectorError):
    """Erreur temporaire qui peut justifier un retry."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        max_retries: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise l'erreur retryable.
        
        Args:
            message: Message d'erreur
            retry_after: Délai recommandé avant retry (secondes)
            max_retries: Nombre maximum de retries recommandé
            **kwargs: Arguments supplémentaires pour ConnectorError
        """
        context = kwargs.pop("context", {})
        if retry_after:
            context["retry_after"] = retry_after
        if max_retries:
            context["max_retries"] = max_retries
            
        super().__init__(
            message=message,
            error_code="RETRYABLE_ERROR",
            context=context,
            **kwargs,
        )


class AuthenticationError(APIError):
    """Erreur d'authentification API."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialise l'erreur d'authentification."""
        super().__init__(
            message=message,
            status_code=kwargs.pop("status_code", 401),
            **kwargs,
        )
        self.error_code = "AUTH_ERROR"


class RateLimitError(RetryableError):
    """Erreur de dépassement de rate limit."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise l'erreur de rate limit."""
        super().__init__(
            message=message,
            retry_after=retry_after,
            **kwargs,
        )
        self.error_code = "RATE_LIMIT_ERROR"


class DataValidationError(ConnectorError):
    """Erreur de validation des données."""

    def __init__(
        self,
        message: str,
        invalid_fields: Optional[list] = None,
        **kwargs: Any,
    ) -> None:
        """Initialise l'erreur de validation.
        
        Args:
            message: Message d'erreur
            invalid_fields: Liste des champs invalides
            **kwargs: Arguments supplémentaires pour ConnectorError
        """
        context = kwargs.pop("context", {})
        if invalid_fields:
            context["invalid_fields"] = invalid_fields
            
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            context=context,
            **kwargs,
        )
