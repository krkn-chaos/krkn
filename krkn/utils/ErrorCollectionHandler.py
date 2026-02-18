import logging
import threading
from datetime import datetime, timezone
from krkn.utils.ErrorLog import ErrorLog


class ErrorCollectionHandler(logging.Handler):
    """
    Custom logging handler that captures ERROR and CRITICAL level logs
    in structured format for telemetry collection.

    Stores logs in memory as ErrorLog objects for later retrieval.
    Thread-safe for concurrent logging operations.
    """

    def __init__(self, level=logging.ERROR):
        """
        Initialize the error collection handler.

        Args:
            level: Minimum log level to capture (default: ERROR)
        """
        super().__init__(level)
        self.error_logs: list[ErrorLog] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        """
        Capture ERROR and CRITICAL logs and store as ErrorLog objects.

        Args:
            record: LogRecord from Python logging framework
        """
        try:
            # Only capture ERROR (40) and CRITICAL (50) levels
            if record.levelno < logging.ERROR:
                return

            # Format timestamp as ISO 8601 UTC
            timestamp = datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

            # Create ErrorLog object
            error_log = ErrorLog(
                timestamp=timestamp,
                message=record.getMessage()
            )

            # Thread-safe append
            with self._lock:
                self.error_logs.append(error_log)

        except Exception:
            # Handler should never raise exceptions (logging best practice)
            self.handleError(record)

    def get_error_logs(self) -> list[dict]:
        """
        Retrieve all collected error logs as list of dictionaries.

        Returns:
            List of error log dictionaries with timestamp and message
        """
        with self._lock:
            return [log.to_dict() for log in self.error_logs]

    def clear(self):
        """Clear all collected error logs (useful for testing)"""
        with self._lock:
            self.error_logs.clear()
