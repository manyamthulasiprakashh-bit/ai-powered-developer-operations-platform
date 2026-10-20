class AppException(Exception):
    """Base exception for application-level errors."""


class ValidationError(AppException):
    """Raised when request data is invalid."""


class ExternalServiceError(AppException):
    """Raised when an external service call fails."""


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""


class AuthenticationError(AppException):
    """Raised when a request is missing valid API-key credentials."""


class AuthenticationConfigurationError(AppException):
    """Raised when API-key authentication is enabled but not configured server-side."""


class GitHubServiceError(ExternalServiceError):
    """Raised when the GitHub API call fails."""


class GitHubHTTPError(GitHubServiceError):
    """Raised for an upstream HTTP response that may be transient."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubAuthError(GitHubServiceError):
    """Raised when GitHub authentication fails."""


class GitHubRateLimitError(GitHubServiceError):
    """Raised when GitHub rate limiting is hit."""


class GitHubNotFoundError(NotFoundError, GitHubServiceError):
    """Raised when a GitHub repository cannot be found."""


class GitHubTimeoutError(GitHubServiceError, TimeoutError):
    """Raised when a GitHub API request times out."""


class GitHubCircuitOpenError(GitHubServiceError):
    """Raised when GitHub calls are temporarily stopped after repeated failures."""


class UnsupportedDocumentError(AppException):
    """Raised when an uploaded document has an unsupported type or encoding."""


class DocumentTooLargeError(AppException):
    """Raised when an uploaded document exceeds the configured size limit."""


class InvalidDocumentError(AppException):
    """Raised when an uploaded document is empty or is not valid UTF-8 text."""


class DocumentNotFoundError(NotFoundError):
    """Raised when a requested document does not exist."""


class DocumentNotExtractableError(AppException):
    """Raised when a document's current status does not permit extraction."""


class DocumentNotDecidableError(AppException):
    """Raised when a document's current state does not permit a decision."""


class ExtractionProviderError(ExternalServiceError):
    """Raised when the document extraction provider fails."""


class ExtractionTimeoutError(ExtractionProviderError, TimeoutError):
    """Raised when a document extraction provider request times out."""


class ExtractionOutputError(ExtractionProviderError):
    """Raised when a provider returns output that cannot be validated."""
