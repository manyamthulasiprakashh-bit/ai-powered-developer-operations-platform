class AppException(Exception):
    """Base exception for application-level errors."""


class ValidationError(AppException):
    """Raised when request data is invalid."""


class ExternalServiceError(AppException):
    """Raised when an external service call fails."""


class NotFoundError(AppException):
    """Raised when a requested resource does not exist."""


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
