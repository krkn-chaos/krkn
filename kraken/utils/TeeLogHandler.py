import logging
class TeeLogHandler(logging.Handler):
    logs: list[str] = []
    name = "TeeLogHandler"

    def get_output(self) -> str:
        return "\n".join(self.logs)

    def emit(self, record):
        self.logs.append(self.formatter.format(record))
    def __del__(self):
        pass