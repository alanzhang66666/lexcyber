class ModelError(Exception):
    code = "MODEL_FAILED"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class ModelNotConfiguredError(ModelError):
    code = "MODEL_NOT_CONFIGURED"


class ModelTimeoutError(ModelError):
    code = "MODEL_TIMEOUT"


class ModelFailedError(ModelError):
    code = "MODEL_FAILED"
