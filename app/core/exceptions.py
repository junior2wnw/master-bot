"""Domain exceptions. Each carries a user-friendly message for bot/API responses."""


class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str = "Внутренняя ошибка", code: str = "INTERNAL"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, entity: str = "Объект", message: str | None = None):
        super().__init__(message or f"{entity} не найден", "NOT_FOUND")


class PermissionDenied(AppError):
    def __init__(self, message: str = "Недостаточно прав"):
        super().__init__(message, "PERMISSION_DENIED")


class ValidationError(AppError):
    def __init__(self, message: str = "Ошибка валидации"):
        super().__init__(message, "VALIDATION_ERROR")


class ConflictError(AppError):
    def __init__(self, message: str = "Конфликт данных"):
        super().__init__(message, "CONFLICT")


class ModuleDisabledError(AppError):
    def __init__(self, module: str):
        super().__init__(f"Модуль '{module}' отключён", "MODULE_DISABLED")


class RateLimitError(AppError):
    def __init__(self):
        super().__init__("Слишком много запросов, подождите", "RATE_LIMIT")
