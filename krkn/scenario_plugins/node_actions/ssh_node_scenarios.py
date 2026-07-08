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
import os
import time

import paramiko
from krkn.scenario_plugins.node_actions.abstract_node_scenarios import (
    abstract_node_scenarios,
)
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.models.k8s import AffectedNode, AffectedNodeStatus

try:
    from krkn_lib.utils.ssh_executor import SSHExecutor
except ImportError:

    class SSHExecutor:
        """Executes commands on remote hosts via SSH using paramiko."""

        def __init__(
            self,
            ssh_user: str = "root",
            ssh_private_key: str = "~/.ssh/id_rsa",
            ssh_port: int = 22,
            connect_timeout: int = 30,
        ):
            self.ssh_user = ssh_user
            self.ssh_private_key = os.path.expanduser(ssh_private_key)
            self.ssh_port = ssh_port
            self.connect_timeout = connect_timeout

        def execute(
            self, host: str, command: str, timeout: int = 120
        ) -> tuple[int, str, str]:
            """Execute a command on a remote host via SSH.

            :return: (exit_code, stdout, stderr)
            """
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
            try:
                ssh.connect(
                    host,
                    port=self.ssh_port,
                    username=self.ssh_user,
                    key_filename=self.ssh_private_key,
                    timeout=self.connect_timeout,
                    banner_timeout=self.connect_timeout,
                )
                stdin, stdout, stderr = ssh.exec_command(
                    command, timeout=timeout
                )
                exit_code = stdout.channel.recv_exit_status()
                return (
                    exit_code,
                    stdout.read().decode(),
                    stderr.read().decode(),
                )
            except paramiko.AuthenticationException as e:
                logging.error(
                    "SSH authentication failed for %s: %s" % (host, e)
                )
                raise
            except paramiko.SSHException as e:
                logging.error(
                    "SSH connection error to %s: %s" % (host, e)
                )
                raise
            except Exception as e:
                logging.error(
                    "Failed to execute command on %s: %s" % (host, e)
                )
                raise
            finally:
                ssh.close()

        def is_host_reachable(self, host: str, timeout: int = 10) -> bool:
            """Check if a host is reachable via SSH."""
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
            try:
                ssh.connect(
                    host,
                    port=self.ssh_port,
                    username=self.ssh_user,
                    key_filename=self.ssh_private_key,
                    timeout=timeout,
                    banner_timeout=timeout,
                )
                ssh.close()
                return True
            except Exception:
                return False

        def wait_for_host(
            self,
            host: str,
            timeout: int = 600,
            poll_interval: int = 15,
            reachable: bool = True,
        ) -> bool:
            """Wait until host becomes reachable or unreachable via SSH."""
            deadline = time.time() + timeout
            state = "reachable" if reachable else "unreachable"
            logging.info(
                "Waiting for %s to become %s (timeout: %ds)"
                % (host, state, timeout)
            )
            while time.time() < deadline:
                if self.is_host_reachable(host) == reachable:
                    logging.info("Host %s is now %s" % (host, state))
                    return True
                time.sleep(poll_interval)
            logging.error(
                "Timed out waiting for %s to become %s" % (host, state)
            )
            return False


class ssh_node_scenarios(abstract_node_scenarios):
    """Node chaos scenarios executed via SSH for standalone mode."""

    def __init__(
        self,
        kubecli: KrknKubernetes,
        node_action_kube_check: bool,
        affected_nodes_status: AffectedNodeStatus,
        ssh_config: dict,
    ):
        super().__init__(kubecli, node_action_kube_check, affected_nodes_status)
        self.ssh = SSHExecutor(
            ssh_user=ssh_config.get("ssh_user", "root"),
            ssh_private_key=ssh_config.get("ssh_private_key", "~/.ssh/id_rsa"),
            ssh_port=ssh_config.get("ssh_port", 22),
            connect_timeout=ssh_config.get("ssh_connect_timeout", 30),
        )

    def supports_standalone(self) -> bool:
        return True

    def node_reboot_scenario(
        self, instance_kill_count, node, timeout, soft_reboot=False
    ):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting SSH node_reboot_scenario on %s" % node)
                cmd = "sudo reboot" if soft_reboot else "sudo sh -c 'echo b > /proc/sysrq-trigger'"
                try:
                    self.ssh.execute(node, cmd, timeout=10)
                except Exception:
                    pass  # connection drops on reboot
                start_time = time.time()
                self.ssh.wait_for_host(node, timeout=timeout, reachable=False)
                self.ssh.wait_for_host(node, timeout=timeout, reachable=True)
                recovery_time = time.time() - start_time
                affected_node.set_affected_node_status("running", recovery_time)
                logging.info(
                    "SSH node_reboot_scenario on %s completed (recovery: %.1fs)"
                    % (node, recovery_time)
                )
            except Exception as e:
                logging.error(
                    "SSH node_reboot_scenario failed on %s: %s" % (node, e)
                )
                raise RuntimeError(
                    "SSH node_reboot_scenario failed on %s" % node
                )
            self.affected_nodes_status.affected_nodes.append(affected_node)

    def node_stop_scenario(self, instance_kill_count, node, timeout, poll_interval):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting SSH node_stop_scenario (shutdown) on %s" % node)
                try:
                    self.ssh.execute(node, "sudo shutdown -h now", timeout=10)
                except Exception:
                    pass  # connection drops on shutdown
                start_time = time.time()
                self.ssh.wait_for_host(
                    node, timeout=timeout, reachable=False
                )
                affected_node.set_affected_node_status(
                    "stopped", time.time() - start_time
                )
                logging.info(
                    "SSH node_stop_scenario on %s completed" % node
                )
            except Exception as e:
                logging.error(
                    "SSH node_stop_scenario failed on %s: %s" % (node, e)
                )
                raise RuntimeError(
                    "SSH node_stop_scenario failed on %s" % node
                )
            self.affected_nodes_status.affected_nodes.append(affected_node)

    def node_start_scenario(self, instance_kill_count, node, timeout, poll_interval):
        logging.warning(
            "node_start_scenario is not supported via SSH "
            "(cannot power on a shutdown host remotely). "
            "Use a cloud provider cloud_type for power management."
        )

    def node_termination_scenario(
        self, instance_kill_count, node, timeout, poll_interval
    ):
        logging.warning(
            "node_termination_scenario is not supported via SSH. "
            "Use a cloud provider cloud_type for instance termination."
        )

    def node_crash_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting SSH node_crash_scenario on %s" % node)
                try:
                    self.ssh.execute(
                        node,
                        "sudo sh -c 'echo c > /proc/sysrq-trigger'",
                        timeout=10,
                    )
                except Exception:
                    pass  # connection drops on crash
                logging.info(
                    "SSH node_crash_scenario on %s injected" % node
                )
            except Exception as e:
                logging.error(
                    "SSH node_crash_scenario failed on %s: %s" % (node, e)
                )
                return 1

    def stop_kubelet_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info("Starting SSH stop_kubelet_scenario on %s" % node)
                exit_code, _, stderr = self.ssh.execute(
                    node, "sudo systemctl stop kubelet", timeout=60
                )
                if exit_code != 0:
                    raise Exception("Failed to stop kubelet: %s" % stderr)
                logging.info("Kubelet stopped on %s via SSH" % node)
            except Exception as e:
                logging.error(
                    "SSH stop_kubelet_scenario failed: %s" % e
                )
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)

    def restart_kubelet_scenario(self, instance_kill_count, node, timeout):
        for _ in range(instance_kill_count):
            affected_node = AffectedNode(node)
            try:
                logging.info(
                    "Starting SSH restart_kubelet_scenario on %s" % node
                )
                exit_code, _, stderr = self.ssh.execute(
                    node, "sudo systemctl restart kubelet", timeout=60
                )
                if exit_code != 0:
                    raise Exception("Failed to restart kubelet: %s" % stderr)
                logging.info("Kubelet restarted on %s via SSH" % node)
            except Exception as e:
                logging.error(
                    "SSH restart_kubelet_scenario failed: %s" % e
                )
                raise e
            self.affected_nodes_status.affected_nodes.append(affected_node)
