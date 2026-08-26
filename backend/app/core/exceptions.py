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


class GitHubAuthError(GitHubServiceError):
    """Raised when GitHub authentication fails."""


class GitHubRateLimitError(GitHubServiceError):
    """Raised when GitHub rate limiting is hit."""


class GitHubNotFoundError(NotFoundError, GitHubServiceError):
    """Raised when a GitHub repository cannot be found."""


class GitHubTimeoutError(GitHubServiceError, TimeoutError):
    """Raised when a GitHub API request times out."""
