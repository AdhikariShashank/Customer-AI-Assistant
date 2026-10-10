
class AppException(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int = 400,
        details: list | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []

        super().__init__(message)

class NotFoundException(AppException):
    def __init__(
        self,
        message: str = "Resource not found",
        code: str = "RESOURCE_NOT_FOUND",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=404,
        )


class ConflictException(AppException):
    def __init__(
        self,
        message: str = "Resource conflict",
        code: str = "RESOURCE_CONFLICT",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=409,
        )


class BadRequestException(AppException):
    def __init__(
        self,
        message: str = "Invalid request",
        code: str = "BAD_REQUEST",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=400,
        )


class UnauthorizedException(AppException):
    def __init__(
        self,
        message: str = "Authentication required",
        code: str = "UNAUTHORIZED",
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=401,
        )