class MavunoApiError(Exception):
    """Base exception class for Mavuno API errors."""

    def __init__(self, message:str,status_code:int =500,detail:str =""):
        super().__init__(message)
        self.status_code=status_code
        self.detail=detail

class AuthenticationError(MavunoApiError):
    """Exception raised for 401 errors."""
    pass

class ValidationError(MavunoApiError):
    """Exception raised for 422 Unprocessed responses (Validation errors)"""
    pass

class ResourceNotFoundError(MavunoApiError):
    """Exception raised for 404 Not Found errors."""
    pass