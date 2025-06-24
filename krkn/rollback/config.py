from dataclasses import dataclass

@dataclass
class RollbackConfig:
    """Configuration for the rollback scenarios."""
    auto: bool
    versions_directory: str