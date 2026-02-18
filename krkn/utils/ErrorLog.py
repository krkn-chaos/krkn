from dataclasses import dataclass, asdict


@dataclass
class ErrorLog:
    """
    Represents a single error log entry for telemetry collection.

    Attributes:
        timestamp: ISO 8601 formatted timestamp (UTC)
        message: Full error message text
    """
    timestamp: str
    message: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
