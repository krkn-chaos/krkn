#!/usr/bin/env python
import datetime
import json
import os
import sys
import yaml
import logging
import optparse
import pyfiglet
import uuid
import time

from krkn_lib.models.krkn import ChaosRunOutput, ChaosRunAlertSummary
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
import kraken.time_actions.common_time_functions as time_actions
import kraken.performance_dashboards.setup as performance_dashboards
import kraken.pod_scenarios.setup as pod_scenarios
import kraken.service_disruption.common_service_disruption_functions as service_disruption
import kraken.shut_down.common_shut_down_func as shut_down
import kraken.node_actions.run as nodeaction
import kraken.managedcluster_scenarios.run as managedcluster_scenarios
import kraken.zone_outage.actions as zone_outages
import kraken.application_outage.actions as application_outage
import kraken.pvc.pvc_scenario as pvc_scenario
import kraken.network_chaos.actions as network_chaos
import kraken.arcaflow_plugin as arcaflow_plugin
import kraken.prometheus as prometheus_plugin
import server as server
from kraken import plugins
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.elastic import KrknElastic
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.utils import SafeLogger
from krkn_lib.utils.functions import get_yaml_item_value


report_file = ""

# Main function
def main(cfg):
    # Start kraken
    print(pyfiglet.figlet_format("kraken"))
    logging.info("Starting kraken")

    # Parse and read the config
    if os.path.isfile(cfg):
        with open(cfg, "r") as f:
            config = yaml.full_load(f)
        global kubeconfig_path, wait_duration, kraken_config
        distribution = get_yaml_item_value(
            config["kraken"], "distribution", "openshift"
        )
        kubeconfig_path = os.path.expanduser(
            get_yaml_item_value(config["kraken"], "kubeconfig_path", "")
        )
        kraken_config = cfg
        chaos_scenarios = get_yaml_item_value(
            config["kraken"], "chaos_scenarios", []
        )
        publish_running_status = get_yaml_item_value(
            config["kraken"], "publish_kraken_status", False
        )
        port = get_yaml_item_value(config["kraken"], "port", 8081)
        signal_address = get_yaml_item_value(
            config["kraken"], "signal_address", "0.0.0.0")
        run_signal = get_yaml_item_value(
            config["kraken"], "signal_state", "RUN"
        )
        wait_duration = get_yaml_item_value(
            config["tunings"], "wait_duration", 60
        )
        iterations = get_yaml_item_value(config["tunings"], "iterations", 1)
        daemon_mode = get_yaml_item_value(
            config["tunings"], "daemon_mode", False
        )
        deploy_performance_dashboards = get_yaml_item_value(
            config["performance_monitoring"], "deploy_dashboards", False
        )
        dashboard_repo = get_yaml_item_value(
            config["performance_monitoring"], "repo",
            "https://github.com/cloud-bulldozer/performance-dashboards.git"
        )

        prometheus_url = config["performance_monitoring"].get("prometheus_url")
        prometheus_bearer_token = config["performance_monitoring"].get(
            "prometheus_bearer_token"
        )
        run_uuid = config["performance_monitoring"].get("uuid")
        enable_alerts = get_yaml_item_value(
            config["performance_monitoring"], "enable_alerts", False
        )
        alert_profile = config["performance_monitoring"].get("alert_profile")
        check_critical_alerts = get_yaml_item_value(
            config["performance_monitoring"], "check_critical_alerts", False
        )
        telemetry_api_url = config["telemetry"].get("api_url")
        elastic_config = get_yaml_item_value(config,"elastic",{})
        elastic_url = get_yaml_item_value(elastic_config,"elastic_url","")
        elastic_index = get_yaml_item_value(elastic_config,"elastic_index","")
        
        # Initialize clients
        if (not os.path.isfile(kubeconfig_path) and
            not os.path.isfile("/var/run/secrets/kubernetes.io/serviceaccount/token")):
            logging.error(
                "Cannot read the kubeconfig file at %s, please check" % kubeconfig_path
            )
            sys.exit(1)
        logging.info("Initializing client to talk to the Kubernetes cluster")

        # Generate uuid for the run
        if run_uuid:
            logging.info(
                "Using the uuid defined by the user for the run: %s" % run_uuid
            )
        else:
            run_uuid = str(uuid.uuid4())
            logging.info("Generated a uuid for the run: %s" % run_uuid)

        # request_id for telemetry is generated once here and used everywhere
        telemetry_request_id = f"{int(time.time())}-{run_uuid}"
        if config["telemetry"].get("run_tag"):
            telemetry_request_id = f"{telemetry_request_id}-{config['telemetry']['run_tag']}"
        telemetry_log_file = f'{config["telemetry"]["archive_path"]}/{telemetry_request_id}.log'
        safe_logger = SafeLogger(filename=telemetry_log_file)

        try:
            kubeconfig_path
            os.environ["KUBECONFIG"] = str(kubeconfig_path)
            # krkn-lib-kubernetes init
            kubecli = KrknKubernetes(kubeconfig_path=kubeconfig_path)
            ocpcli = KrknOpenshift(kubeconfig_path=kubeconfig_path)
        except:
            kubecli.initialize_clients(None)

        # find node kraken might be running on
        kubecli.find_kraken_node()

        # Set up kraken url to track signal
        if not 0 <= int(port) <= 65535:
            logging.error("%s isn't a valid port number, please check" % (port))
            sys.exit(1)
        if not signal_address:
            logging.error("Please set the signal address in the config")
            sys.exit(1)
        address = (signal_address, port)

        # If publish_running_status is False this should keep us going
        # in our loop below
        if publish_running_status:
            server_address = address[0]
            port = address[1]
            logging.info(
                "Publishing kraken status at http://%s:%s" % (server_address, port)
            )
            server.start_server(address, run_signal)

        # Cluster info
        logging.info("Fetching cluster info")
        cv = ""
        if distribution == "openshift":
            cv = ocpcli.get_clusterversion_string()
            if prometheus_url is None:
                try:
                    connection_data = ocpcli.get_prometheus_api_connection_data()
                    if connection_data:
                        prometheus_url = connection_data.endpoint
                        prometheus_bearer_token = connection_data.token
                    else: 
                        # If can't make a connection, set alerts to false
                        enable_alerts = False
                        critical_alerts = False
                except Exception:
                    logging.error("invalid distribution selected, running openshift scenarios against kubernetes cluster."
                                  "Please set 'kubernetes' in config.yaml krkn.platform and try again")
                    sys.exit(1)
        if cv != "":
            logging.info(cv)
        else:
            logging.info("Cluster version CRD not detected, skipping")

        # KrknTelemetry init
        telemetry_k8s = KrknTelemetryKubernetes(safe_logger, kubecli)
        telemetry_ocp = KrknTelemetryOpenshift(safe_logger, ocpcli)
        telemetry_elastic = KrknElastic(safe_logger,elastic_url)
        summary = ChaosRunAlertSummary()
        if enable_alerts or check_critical_alerts:
            prometheus = KrknPrometheus(prometheus_url, prometheus_bearer_token)

        logging.info("Server URL: %s" % kubecli.get_host())

        # Deploy performance dashboards
        if deploy_performance_dashboards:
            performance_dashboards.setup(dashboard_repo, distribution)



        # Initialize the start iteration to 0
        iteration = 0

        # Set the number of iterations to loop to infinity if daemon mode is
        # enabled or else set it to the provided iterations count in the config
        if daemon_mode:
            logging.info("Daemon mode enabled, kraken will cause chaos forever\n")
            logging.info("Ignoring the iterations set")
            iterations = float("inf")
        else:
            logging.info(
                "Daemon mode not enabled, will run through %s iterations\n"
                % str(iterations)
            )
            iterations = int(iterations)

        failed_post_scenarios = []

        # Capture the start time
        start_time = int(time.time())
        post_critical_alerts = 0
        chaos_output = ChaosRunOutput()
        chaos_telemetry = ChaosRunTelemetry()
        chaos_telemetry.run_uuid = run_uuid
        # Loop to run the chaos starts here
        while int(iteration) < iterations and run_signal != "STOP":
            # Inject chaos scenarios specified in the config
            logging.info("Executing scenarios for iteration " + str(iteration))
            if chaos_scenarios:
                for scenario in chaos_scenarios:
                    if publish_running_status:
                        run_signal = server.get_status(address)
                    if run_signal == "PAUSE":
                        while publish_running_status and run_signal == "PAUSE":
                            logging.info(
                                "Pausing Kraken run, waiting for %s seconds"
                                " and will re-poll signal" % str(wait_duration)
                            )
                            time.sleep(wait_duration)
                            run_signal = server.get_status(address)
                    if run_signal == "STOP":
                        logging.info("Received STOP signal; ending Kraken run")
                        break
                    scenario_type = list(scenario.keys())[0]
                    scenarios_list = scenario[scenario_type]
                    if scenarios_list:
                        # Inject pod chaos scenarios specified in the config
                        if scenario_type == "pod_scenarios":
                            logging.error(
                                "Pod scenarios have been removed, please use "
                                "plugin_scenarios with the "
                                "kill-pods configuration instead."
                            )
                            sys.exit(1)
                        elif scenario_type == "arcaflow_scenarios":
                            failed_post_scenarios, scenario_telemetries = arcaflow_plugin.run(
                                scenarios_list, kubeconfig_path, telemetry_k8s
                            )
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        elif scenario_type == "plugin_scenarios":
                            failed_post_scenarios, scenario_telemetries = plugins.run(
                                scenarios_list,
                                kubeconfig_path,
                                kraken_config,
                                failed_post_scenarios,
                                wait_duration,
                                telemetry_k8s
                            )
                            chaos_telemetry.scenarios.extend(scenario_telemetries)
                        # krkn_lib
                        elif scenario_type == "container_scenarios":
                            logging.info("Running container scenarios")
                            failed_post_scenarios, scenario_telemetries = pod_scenarios.container_run(
                                kubeconfig_path,
                                scenarios_list,
                                config,
                                failed_post_scenarios,
                                wait_duration,
                                kubecli,
                                telemetry_k8s
                            )
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        # Inject node chaos scenarios specified in the config
                        # krkn_lib
                        elif scenario_type == "node_scenarios":
                            logging.info("Running node scenarios")
                            failed_post_scenarios, scenario_telemetries = nodeaction.run(scenarios_list, config, wait_duration, kubecli, telemetry_k8s)
                            chaos_telemetry.scenarios.extend(scenario_telemetries)
                        # Inject managedcluster chaos scenarios specified in the config
                        # krkn_lib
                        elif scenario_type == "managedcluster_scenarios":
                            logging.info("Running managedcluster scenarios")
                            managedcluster_scenarios.run(
                                scenarios_list, config, wait_duration, kubecli
                            )

                        # Inject time skew chaos scenarios specified
                        # in the config
                        # krkn_lib
                        elif scenario_type == "time_scenarios":
                                logging.info("Running time skew scenarios")
                                failed_post_scenarios, scenario_telemetries = time_actions.run(scenarios_list, config, wait_duration, kubecli, telemetry_k8s)
                                chaos_telemetry.scenarios.extend(scenario_telemetries)
                        # Inject cluster shutdown scenarios
                        # krkn_lib
                        elif scenario_type == "cluster_shut_down_scenarios":
                            failed_post_scenarios, scenario_telemetries = shut_down.run(scenarios_list, config, wait_duration, kubecli, telemetry_k8s)
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        # Inject namespace chaos scenarios
                        # krkn_lib
                        elif scenario_type == "service_disruption_scenarios":
                            logging.info("Running service disruption scenarios")
                            failed_post_scenarios, scenario_telemetries = service_disruption.run(
                                scenarios_list,
                                config,
                                wait_duration,
                                failed_post_scenarios,
                                kubeconfig_path,
                                kubecli,
                                telemetry_k8s
                            )
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        # Inject zone failures
                        elif scenario_type == "zone_outages":
                            logging.info("Inject zone outages")
                            failed_post_scenarios, scenario_telemetries = zone_outages.run(scenarios_list, config, wait_duration, telemetry_k8s)
                            chaos_telemetry.scenarios.extend(scenario_telemetries)
                        # Application outages
                        elif scenario_type == "application_outages":
                            logging.info("Injecting application outage")
                            failed_post_scenarios, scenario_telemetries = application_outage.run(
                                scenarios_list, config, wait_duration, kubecli, telemetry_k8s)
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        # PVC scenarios
                        # krkn_lib
                        elif scenario_type == "pvc_scenarios":
                            logging.info("Running PVC scenario")
                            failed_post_scenarios, scenario_telemetries = pvc_scenario.run(scenarios_list, config, kubecli, telemetry_k8s)
                            chaos_telemetry.scenarios.extend(scenario_telemetries)

                        # Network scenarios
                        # krkn_lib
                        elif scenario_type == "network_chaos":
                            logging.info("Running Network Chaos")
                            failed_post_scenarios, scenario_telemetries = network_chaos.run(scenarios_list, config, wait_duration, kubecli, telemetry_k8s)

                        # Check for critical alerts when enabled
                        post_critical_alerts = 0
                        if check_critical_alerts:
                            prometheus_plugin.critical_alerts(prometheus,
                                                              summary,
                                                              run_uuid,
                                                              scenario_type,
                                                              start_time,
                                                              datetime.datetime.now())

                            chaos_output.critical_alerts = summary
                            post_critical_alerts = len(summary.post_chaos_alerts)
                            if post_critical_alerts > 0:
                                logging.error("Post chaos critical alerts firing please check, exiting")
                                break


            iteration += 1
            logging.info("")

        # telemetry
        # in order to print decoded telemetry data even if telemetry collection
        # is disabled, it's necessary to serialize the ChaosRunTelemetry object
        # to json, and recreate a new object from it.
        end_time = int(time.time())

        # if platform is openshift will be collected
        # Cloud platform and network plugins metadata
        # through OCP specific APIs
        if distribution == "openshift":
            telemetry_ocp.collect_cluster_metadata(chaos_telemetry)
        else:
            telemetry_k8s.collect_cluster_metadata(chaos_telemetry)

        decoded_chaos_run_telemetry = ChaosRunTelemetry(json.loads(chaos_telemetry.to_json()))
        chaos_output.telemetry = decoded_chaos_run_telemetry
        logging.info(f"Chaos data:\n{chaos_output.to_json()}")
        telemetry_elastic.upload_data_to_elasticsearch(decoded_chaos_run_telemetry.to_json(), elastic_index)
        if config["telemetry"]["enabled"]:
            logging.info(f'telemetry data will be stored on s3 bucket folder: {telemetry_api_url}/files/'
                         f'{(config["telemetry"]["telemetry_group"] if config["telemetry"]["telemetry_group"] else "default")}/'
                         f'{telemetry_request_id}')
            logging.info(f"telemetry upload log: {safe_logger.log_file_name}")
            try:
                telemetry_k8s.send_telemetry(config["telemetry"], telemetry_request_id, chaos_telemetry)
                telemetry_k8s.put_cluster_events(telemetry_request_id, config["telemetry"], start_time, end_time)
                telemetry_k8s.put_critical_alerts(telemetry_request_id, config["telemetry"], summary)
                # prometheus data collection is available only on Openshift
                if config["telemetry"]["prometheus_backup"]:
                    prometheus_archive_files = ''
                    if distribution == "openshift" :
                        prometheus_archive_files = telemetry_ocp.get_ocp_prometheus_data(config["telemetry"], telemetry_request_id)
                    else:
                        if (config["telemetry"]["prometheus_namespace"] and
                                config["telemetry"]["prometheus_pod_name"] and
                                config["telemetry"]["prometheus_container_name"]):
                            try:
                                prometheus_archive_files = telemetry_k8s.get_prometheus_pod_data(
                                    config["telemetry"],
                                    telemetry_request_id,
                                    config["telemetry"]["prometheus_pod_name"],
                                    config["telemetry"]["prometheus_container_name"],
                                    config["telemetry"]["prometheus_namespace"]
                                )
                            except Exception as e:
                                logging.error(f"failed to get prometheus backup with exception {str(e)}")
                        else:
                            logging.warning("impossible to backup prometheus,"
                                            "check if config contains telemetry.prometheus_namespace, "
                                            "telemetry.prometheus_pod_name and "
                                            "telemetry.prometheus_container_name")
                    if prometheus_archive_files:
                        safe_logger.info("starting prometheus archive upload:")
                        telemetry_k8s.put_prometheus_data(config["telemetry"], prometheus_archive_files, telemetry_request_id)
                if config["telemetry"]["logs_backup"] and distribution == "openshift":
                    telemetry_ocp.put_ocp_logs(telemetry_request_id, config["telemetry"], start_time, end_time)
            except Exception as e:
                logging.error(f"failed to send telemetry data: {str(e)}")
        else:
            logging.info("telemetry collection disabled, skipping.")


        # Check for the alerts specified
        if enable_alerts:
            logging.info("Alerts checking is enabled")
            if alert_profile:
                prometheus_plugin.alerts(
                    prometheus,
                    start_time,
                    end_time,
                    alert_profile,
                )
            else:
                logging.error("Alert profile is not defined")
                sys.exit(1)

        if post_critical_alerts > 0:
            logging.error("Critical alerts are firing, please check; exiting")
            sys.exit(2)

        if failed_post_scenarios:
            logging.error(
                "Post scenarios are still failing at the end of all iterations"
            )
            sys.exit(2)

        logging.info(
            "Successfully finished running Kraken. UUID for the run: "
            "%s. Report generated at %s. Exiting" % (run_uuid, report_file)
        )
    else:
        logging.error("Cannot find a config at %s, please check" % (cfg))
        sys.exit(1)


if __name__ == "__main__":
    # Initialize the parser to read the config
    parser = optparse.OptionParser()
    parser.add_option(
        "-c",
        "--config",
        dest="cfg",
        help="config location",
        default="config/config.yaml",
    )
    parser.add_option(
        "-o",
        "--output",
        dest="output",
        help="output report location",
        default="kraken.report",
    )
    
    (options, args) = parser.parse_args()
    report_file = options.output
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(report_file, mode="w"),
            logging.StreamHandler(),
        ],
    )
    if options.cfg is None:
        logging.error("Please check if you have passed the config")
        sys.exit(1)
    else:
        main(options.cfg)
