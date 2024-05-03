import json
import logging
import time

import yaml
from krkn_lib.k8s import KrknKubernetes


def run(scenarios_list: list[str], krkn_lib: KrknKubernetes):
    for scenario in scenarios_list:
        with open(scenario) as stream:
            scenario_config = yaml.safe_load(stream)

        service_name = scenario_config['service_name']
        service_namespace = scenario_config['service_namespace']
        plan = scenario_config["plan"]
        image = scenario_config["image"]
        target_port = scenario_config["service_target_port"]
        chaos_duration = scenario_config["chaos_duration"]

        logging.info(f"checking service {service_name} in namespace: {service_namespace}")
        if not krkn_lib.service_exists(service_name, service_namespace):
            logging.error(f"service: {service_name} not found in namespace: {service_namespace}, aborting...")
            return
        logging.info(f"service: {service_name} found in namespace: {service_namespace}")
        logging.info(f"creating webservice and initializing test plan...")
        if isinstance(target_port, int):
            logging.info(f"webservice will listen on port {target_port}")
            webservice = krkn_lib.deploy_service_hijacking(service_namespace, plan, image, port_number=target_port)
        else:
            logging.info(f"traffic will be redirected to named port: {target_port}")
            webservice = krkn_lib.deploy_service_hijacking(service_namespace, plan, image, port_name=target_port)
        logging.info(f"successfully deployed pod: {webservice.pod_name} "
                     f"in namespace:{service_namespace} with selector {webservice.selector}!"
                     )
        logging.info(f"patching service: {service_name} to hijack traffic towards: {webservice.pod_name}")
        original_service=krkn_lib.replace_service_selector([webservice.selector], service_name, service_namespace)
        logging.info(f"service: {service_name} successfully patched!")
        logging.info(f"original service manifest:\n\n{yaml.dump(original_service)}")
        logging.info(f"waiting {chaos_duration} before restoring the service")
        time.sleep(chaos_duration)
        selectors = ["=".join([key, original_service["spec"]["selector"][key]]) for key in original_service["spec"]["selector"].keys()]
        logging.info(f"restoring the service selectors {selectors}")
        krkn_lib.replace_service_selector(selectors, service_name, service_namespace)
        logging.info("selectors successfully restored")
        logging.info("undeploying service-hijacking resources...")
        krkn_lib.undeploy_service_hijacking(webservice)
        logging.info("success")

