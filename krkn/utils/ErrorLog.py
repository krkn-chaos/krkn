# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
