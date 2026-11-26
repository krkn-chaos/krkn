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


def wait_or_fail(reached, what: str) -> None:
    """Fail the scenario unless a wait reported that it reached its state.

    Waits return True once the state is reached and False on a timeout or
    error. Anything other than True means the chaos did not happen as
    planned, so the scenario must not pass.

    :param reached: the value the wait returned
    :param what: what was awaited, for the error message
    :raises RuntimeError: if ``reached`` is not True
    """
    if reached is not True:
        raise RuntimeError(f"Timed out or failed waiting for {what}")
