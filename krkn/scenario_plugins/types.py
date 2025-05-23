from enum import Enum
from typing import List, Optional

class classproperty(property):
    """
    A decorator for class-level properties.

    """
    def __get__(self, instance, owner):
        return self.fget(owner)


class BaseType(Enum):
    """
    Base class for all enumeration types in scenario plugins.
    
    Provides common utility methods for all type enums.
    """
    
    @classproperty
    def available_options(cls) -> List[str]:
        """
        Returns a list of all available values for this enum.
        
        Returns:
            List[str]: List of string values for all enum options
        """
        return [option.value for option in cls]
    
    @classmethod
    def from_string(cls, value: str) -> Optional['BaseType']:
        """
        Convert a string value to the corresponding enum member.
        
        Args:
            value: String representation of the enum value
            
        Returns:
            The enum member if found, None otherwise
        """
        for item in cls:
            if item.value == value:
                return item
        return None

    @classmethod
    def validate(cls, value: str) -> bool:
        """
        Validates if the provided string is a valid enum value.
        
        Args:
            value: String value to validate
            
        Returns:
            bool: True if value is valid, False otherwise
        """
        return cls.from_string(value) is not None


class ExecutionType(BaseType):
    """
    Defines how scenario operations should be executed.
    
    PARALLEL: Run operations concurrently
    SERIAL: Run operations sequentially
    """
    PARALLEL = "parallel"
    SERIAL = "serial"