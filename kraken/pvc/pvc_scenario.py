import sys
import yaml
import logging
import time
import kraken.cerberus.setup as cerberus
import kraken.kubernetes.client as kubecli

# Reads the scenario config and creates a temp file to fill up the PVC
def run(scenarios_list, config):
    failed_post_scenarios = ""
    for app_config in scenarios_list:
        if len(app_config) > 1:
            with open(app_config, "r") as f:
                config_yaml = yaml.full_load(f)
                scenario_config = config_yaml["pvc_scenario"]
                pod_name = scenario_config.get("pod_name", "")
                namespace = scenario_config.get("namespace", "")
                mount_path = scenario_config.get("mount_path", "")
                file_size = scenario_config.get("file_size", "1024")
                duration = scenario_config.get("duration", 60)

                start_time = int(time.time())

                file_name = "kraken.tmp"
                logging.info("Creating %s file, %sK size, in pod %s at %s (ns %s)" 
                % (str(file_name), str(file_size), str(pod_name), str(mount_path), str(namespace)))

                # Create temp file in the pvc
                full_path = "%s/%s" % (str(mount_path), str(file_name))
                command = "dd bs=1024 count=%s </dev/urandom >%s" % (str(file_size), str(full_path))
                response = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                if "copied" in response.lower():
                  logging.info("%s file successfully created" % (str(full_path)))
                else:
                  logging.error("Failed to create tmp file with %s size" % (str(file_size)))
                  sys.exit(1)
                logging.info("\n"+str(response))

                # Wait for the specified duration
                logging.info("Waiting for the specified duration in the config: %ss" % (duration))
                time.sleep(duration)
                logging.info("Finish waiting")

                # Remove the temp file from the pvc
                command = "rm %s" % (str(full_path))
                kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                command = "ls %s" % (str(mount_path))
                response = kubecli.exec_cmd_in_pod(command, pod_name, namespace)
                if not file_name in response.lower():
                  logging.info("Temp file successfully removed")
                else:
                  logging.error("Failed to delete tmp file with %s size" % (str(file_size)))
                  sys.exit(1)
                logging.info("\n"+str(response))

                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
