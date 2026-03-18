#!/usr/bin/env python
#
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