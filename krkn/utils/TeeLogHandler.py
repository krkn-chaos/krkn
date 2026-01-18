import logging

class TeeLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs: list[str] = []
        self.name = "TeeLogHandler"

    def get_output(self) -> str:
        return "\n".join(self.logs)

    def emit(self, record):
        if self.formatter:
            self.logs.append(self.formatter.format(record))
        else:
            self.logs.append(self.format(record))
