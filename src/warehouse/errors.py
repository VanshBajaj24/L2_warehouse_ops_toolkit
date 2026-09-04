class ToolError(Exception):
    def __init__(self, code: str, message: str, hint: str):
        self.code = code
        self.message = message
        self.hint = hint
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
        }
