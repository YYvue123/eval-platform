from __future__ import annotations


class McpError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.public_message = message

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
