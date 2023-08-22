from jinja2 import Environment, FileSystemLoader
import os
import time
import logging
import sys
import yaml
import kraken.managedcluster_scenarios.common_managedcluster_functions as common_managedcluster_functions
from krkn_lib.k8s import KrknKubernetes

class GENERAL:
    def __init__(self):
        pass

# krkn_lib
class managedcluster_scenarios():
    kubecli: KrknKubernetes
    def __init__(self, kubecli: KrknKubernetes):
        self.kubecli = kubecli
        self.general = GENERAL()

    # managedcluster scenario to start the managedcluster
    def managedcluster_start_scenario(self, instance_kill_count, managedcluster, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting managedcluster_start_scenario injection")
                file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
                env = Environment(loader=file_loader, autoescape=False)
                template = env.get_template("manifestwork.j2")
                body = yaml.safe_load(
                    template.render(managedcluster_name=managedcluster,
                        args="""kubectl scale deployment.apps/klusterlet --replicas 3 &
                                kubectl scale deployment.apps/klusterlet-registration-agent --replicas 1 -n open-cluster-management-agent""")
                )
                self.kubecli.create_manifestwork(body, managedcluster)
                logging.info("managedcluster_start_scenario has been successfully injected!")
                logging.info("Waiting for the specified timeout: %s" % timeout)
                common_managedcluster_functions.wait_for_available_status(managedcluster, timeout, self.kubecli)
            except Exception as e:
                logging.error("managedcluster scenario exiting due to Exception %s" % e)
                sys.exit(1)
            finally:
                logging.info("Deleting manifestworks")
                self.kubecli.delete_manifestwork(managedcluster)

    # managedcluster scenario to stop the managedcluster
    def managedcluster_stop_scenario(self, instance_kill_count, managedcluster, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting managedcluster_stop_scenario injection")
                file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)),encoding='utf-8')
                env = Environment(loader=file_loader, autoescape=False)
                template = env.get_template("manifestwork.j2")
                body = yaml.safe_load(
                    template.render(managedcluster_name=managedcluster,
                        args="""kubectl scale deployment.apps/klusterlet --replicas 0 &&
                                kubectl scale deployment.apps/klusterlet-registration-agent --replicas 0 -n open-cluster-management-agent""")
                )
                self.kubecli.create_manifestwork(body, managedcluster)
                logging.info("managedcluster_stop_scenario has been successfully injected!")
                logging.info("Waiting for the specified timeout: %s" % timeout)
                common_managedcluster_functions.wait_for_unavailable_status(managedcluster, timeout, self.kubecli)
            except Exception as e:
                logging.error("managedcluster scenario exiting due to Exception %s" % e)
                sys.exit(1)
            finally:
                logging.info("Deleting manifestworks")
                self.kubecli.delete_manifestwork(managedcluster)

    # managedcluster scenario to stop and then start the managedcluster
    def managedcluster_stop_start_scenario(self, instance_kill_count, managedcluster, timeout):
        logging.info("Starting managedcluster_stop_start_scenario injection")
        self.managedcluster_stop_scenario(instance_kill_count, managedcluster, timeout)
        time.sleep(10)
        self.managedcluster_start_scenario(instance_kill_count, managedcluster, timeout)
        logging.info("managedcluster_stop_start_scenario has been successfully injected!")

    # managedcluster scenario to terminate the managedcluster
    def managedcluster_termination_scenario(self, instance_kill_count, managedcluster, timeout):
        logging.info("managedcluster termination is not implemented, " "no action is going to be taken")

    # managedcluster scenario to reboot the managedcluster
    def managedcluster_reboot_scenario(self, instance_kill_count, managedcluster, timeout):
        logging.info("managedcluster reboot is not implemented," " no action is going to be taken")

    # managedcluster scenario to start the klusterlet
    def start_klusterlet_scenario(self, instance_kill_count, managedcluster, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting start_klusterlet_scenario injection")
                file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
                env = Environment(loader=file_loader, autoescape=False)
                template = env.get_template("manifestwork.j2")
                body = yaml.safe_load(
                    template.render(managedcluster_name=managedcluster,
                        args="""kubectl scale deployment.apps/klusterlet --replicas 3""")
                )
                self.kubecli.create_manifestwork(body, managedcluster)
                logging.info("start_klusterlet_scenario has been successfully injected!")
                time.sleep(30)                              # until https://github.com/open-cluster-management-io/OCM/issues/118 gets solved
            except Exception as e:
                logging.error("managedcluster scenario exiting due to Exception %s" % e)
                sys.exit(1)
            finally:
                logging.info("Deleting manifestworks")
                self.kubecli.delete_manifestwork(managedcluster)

    # managedcluster scenario to stop the klusterlet
    def stop_klusterlet_scenario(self, instance_kill_count, managedcluster, timeout):
        for _ in range(instance_kill_count):
            try:
                logging.info("Starting stop_klusterlet_scenario injection")
                file_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
                env = Environment(loader=file_loader, autoescape=False)
                template = env.get_template("manifestwork.j2")
                body = yaml.safe_load(
                    template.render(managedcluster_name=managedcluster,
                        args="""kubectl scale deployment.apps/klusterlet --replicas 0""")
                )
                self.kubecli.create_manifestwork(body, managedcluster)
                logging.info("stop_klusterlet_scenario has been successfully injected!")
                time.sleep(30)                              # until https://github.com/open-cluster-management-io/OCM/issues/118 gets solved
            except Exception as e:
                logging.error("managedcluster scenario exiting due to Exception %s" % e)
                sys.exit(1)
            finally:
                logging.info("Deleting manifestworks")
                self.kubecli.delete_manifestwork(managedcluster)

    # managedcluster scenario to stop and start the klusterlet
    def stop_start_klusterlet_scenario(self, instance_kill_count, managedcluster, timeout):
        logging.info("Starting stop_start_klusterlet_scenario injection")
        self.stop_klusterlet_scenario(instance_kill_count, managedcluster, timeout)
        time.sleep(10)
        self.start_klusterlet_scenario(instance_kill_count, managedcluster, timeout)
        logging.info("stop_start_klusterlet_scenario has been successfully injected!")

    # managedcluster scenario to crash the managedcluster
    def managedcluster_crash_scenario(self, instance_kill_count, managedcluster, timeout):
        logging.info("managedcluster crash scenario is not implemented, " "no action is going to be taken")

