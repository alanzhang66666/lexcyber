class SkillRuntimeError(Exception):
    code = "SKILL_RUNTIME_ERROR"
    status = "failed"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        if code:
            self.code = code


class SkillNotFoundError(SkillRuntimeError, LookupError):
    code = "SKILL_NOT_FOUND"


class SkillDisabledError(SkillRuntimeError):
    code = "SKILL_DISABLED"
    status = "denied"


class SkillValidationError(SkillRuntimeError, ValueError):
    code = "SKILL_VALIDATION_ERROR"


class SkillPermissionError(SkillRuntimeError):
    code = "SKILL_PERMISSION_DENIED"
    status = "denied"


class SkillTimeoutError(SkillRuntimeError, TimeoutError):
    code = "SKILL_TIMEOUT"
    status = "timeout"


class SkillHandlerError(SkillRuntimeError):
    code = "SKILL_HANDLER_ERROR"


class SkillOutputInvalidError(SkillRuntimeError, ValueError):
    code = "SKILL_OUTPUT_INVALID"


class SkillProhibitedError(SkillRuntimeError):
    code = "SKILL_PROHIBITED"
    status = "denied"


class SkillNeedHumanError(SkillRuntimeError):
    code = "SKILL_NEED_HUMAN"
    status = "need_human"


class SkillEntrypointError(SkillRuntimeError):
    code = "SKILL_ENTRYPOINT_INVALID"
