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
import queue
import threading

from krkn_lib.elastic.krkn_elastic import KrknElastic
from krkn_lib.models.elastic import ElasticChaosRunTelemetry
from krkn_lib.models.krkn import ChaosRunOutput, ChaosRunAlertSummary
from krkn_lib.prometheus.krkn_prometheus import KrknPrometheus
import krkn.performance_dashboards.setup as performance_dashboards
import krkn.prometheus as prometheus_plugin
import server as server
from krkn_lib.k8s import KrknKubernetes
from krkn_lib.ocp import KrknOpenshift
from krkn_lib.telemetry.k8s import KrknTelemetryKubernetes
from krkn_lib.telemetry.ocp import KrknTelemetryOpenshift
from krkn_lib.models.telemetry import ChaosRunTelemetry
from krkn_lib.utils import SafeLogger
from krkn_lib.utils.functions import get_yaml_item_value, get_junit_test_case

from krkn.utils import TeeLogHandler
from krkn.utils.HealthChecker import HealthChecker
from krkn.scenario_plugins.scenario_plugin_factory import (
    ScenarioPluginFactory,
    ScenarioPluginNotFound,
)

# removes TripleDES warning
import warnings
warnings.filterwarnings(action='ignore', module='.*paramiko.*')

report_file = ""


# Main function
def main(cfg) -> int:
    # Start kraken
    print(pyfiglet.figlet_format("kraken"))
    logging.info("Starting kraken")

    # Parse and read the config
    if os.path.isfile(cfg):
        with open(cfg, "r") as f:
            config = yaml.full_load(f)
        global kubeconfig_path, wait_duration, kraken_config

        kubeconfig_path = os.path.expanduser(
            get_yaml_item_value(config["kraken"], "kubeconfig_path", "")
        )
        kraken_config = cfg
        chaos_scenarios = get_yaml_item_value(config["kraken"], "chaos_scenarios", [])
        publish_running_status = get_yaml_item_value(
            config["kraken"], "publish_kraken_status", False
        )
        port = get_yaml_item_value(config["kraken"], "port", 8081)
        signal_address = get_yaml_item_value(
            config["kraken"], "signal_address", "0.0.0.0"
        )
        run_signal = get_yaml_item_value(config["kraken"], "signal_state", "RUN")
        wait_duration = get_yaml_item_value(config["tunings"], "wait_duration", 60)
        iterations = get_yaml_item_value(config["tunings"], "iterations", 1)
        daemon_mode = get_yaml_item_value(config["tunings"], "daemon_mode", False)
        deploy_performance_dashboards = get_yaml_item_value(
            config["performance_monitoring"], "deploy_dashboards", False
        )
        dashboard_repo = get_yaml_item_value(
            config["performance_monitoring"],
            "repo",
            "https://github.com/cloud-bulldozer/performance-dashboards.git",
        )

        prometheus_url = config["performance_monitoring"].get("prometheus_url")
        prometheus_bearer_token = config["performance_monitoring"].get(
            "prometheus_bearer_token"
        )
        run_uuid = config["performance_monitoring"].get("uuid")
        enable_alerts = get_yaml_item_value(
            config["performance_monitoring"], "enable_alerts", False
        )
        enable_metrics = get_yaml_item_value(
            config["performance_monitoring"], "enable_metrics", False
        )
        # elastic search
        enable_elastic = get_yaml_item_value(config["elastic"], "enable_elastic", False)

        elastic_url = get_yaml_item_value(config["elastic"], "elastic_url", "")

        elastic_verify_certs = get_yaml_item_value(
            config["elastic"], "verify_certs", False
        )

        elastic_port = get_yaml_item_value(config["elastic"], "elastic_port", 32766)

        elastic_username = get_yaml_item_value(config["elastic"], "username", "")
        elastic_password = get_yaml_item_value(config["elastic"], "password", "")

        elastic_metrics_index = get_yaml_item_value(
            config["elastic"], "metrics_index", "krkn-metrics"
        )

        elastic_alerts_index = get_yaml_item_value(
            config["elastic"], "alerts_index", "krkn-alerts"
        )

        elastic_telemetry_index = get_yaml_item_value(
            config["elastic"], "telemetry_index", "krkn-telemetry"
        )

        alert_profile = config["performance_monitoring"].get("alert_profile")
        metrics_profile = config["performance_monitoring"].get("metrics_profile")
        check_critical_alerts = get_yaml_item_value(
            config["performance_monitoring"], "check_critical_alerts", False
        )
        telemetry_api_url = config["telemetry"].get("api_url")
        health_check_config = config["health_checks"]

        # Initialize clients
        if not os.path.isfile(kubeconfig_path) and not os.path.isfile(
                "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ):
            logging.error(
                "Cannot read the kubeconfig file at %s, please check" % kubeconfig_path
            )
            return 1
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
            telemetry_request_id = (
                f"{telemetry_request_id}-{config['telemetry']['run_tag']}"
            )
        telemetry_log_file = (
            f'{config["telemetry"]["archive_path"]}/{telemetry_request_id}.log'
        )
        safe_logger = SafeLogger(filename=telemetry_log_file)

        try:
            kubeconfig_path
            os.environ["KUBECONFIG"] = str(kubeconfig_path)
            # krkn-lib-kubernetes init
            kubecli = KrknKubernetes(kubeconfig_path=kubeconfig_path)
            ocpcli = KrknOpenshift(kubeconfig_path=kubeconfig_path)
        except:
            kubecli.initialize_clients(None)

        distribution = "kubernetes"
        if ocpcli.is_openshift():
            distribution = "openshift"
        logging.info("Detected distribution %s" % (distribution))

        # find node kraken might be running on
        kubecli.find_kraken_node()

        # Set up kraken url to track signal
        if not 0 <= int(port) <= 65535:
            logging.error("%s isn't a valid port number, please check" % (port))
            return 1
        if not signal_address:
            logging.error("Please set the signal address in the config")
            return 1
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
            if not prometheus_url:
                try:
                    connection_data = ocpcli.get_prometheus_api_connection_data()
                    if connection_data:
                        prometheus_url = connection_data.endpoint
                        prometheus_bearer_token = connection_data.token
                    else:
                        # If can't make a connection, set alerts to false
                        enable_alerts = False
                        check_critical_alerts = False
                except Exception:
                    logging.error(
                        "invalid distribution selected, running openshift scenarios against kubernetes cluster."
                        "Please set 'kubernetes' in config.yaml krkn.platform and try again"
                    )
                    return 1
        if cv != "":
            logging.info(cv)
        else:
            logging.info("Cluster version CRD not detected, skipping")

        # KrknTelemetry init
        telemetry_k8s = KrknTelemetryKubernetes(
            safe_logger, kubecli, config["telemetry"]
        )
        telemetry_ocp = KrknTelemetryOpenshift(
            safe_logger, ocpcli, telemetry_request_id, config["telemetry"]
        )
        if enable_elastic:
            logging.info(f"Elastic collection enabled at: {elastic_url}:{elastic_port}")
            elastic_search = KrknElastic(
                safe_logger,
                elastic_url,
                elastic_port,
                elastic_verify_certs,
                elastic_username,
                elastic_password,
            )
        else:
            elastic_search = None
        summary = ChaosRunAlertSummary()
        if enable_metrics or enable_alerts or check_critical_alerts:
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
        scenario_plugin_factory = ScenarioPluginFactory()
        classes_and_types: dict[str, list[str]] = {}
        for loaded in scenario_plugin_factory.loaded_plugins.keys():
            if (
                    scenario_plugin_factory.loaded_plugins[loaded].__name__
                    not in classes_and_types.keys()
            ):
                classes_and_types[
                    scenario_plugin_factory.loaded_plugins[loaded].__name__
                ] = []
            classes_and_types[
                scenario_plugin_factory.loaded_plugins[loaded].__name__
            ].append(loaded)
        logging.info(
            "📣 `ScenarioPluginFactory`: types from config.yaml mapped to respective classes for execution:"
        )
        for class_loaded in classes_and_types.keys():
            if len(classes_and_types[class_loaded]) <= 1:
                logging.info(
                    f"  ✅ type: {classes_and_types[class_loaded][0]} ➡️ `{class_loaded}` "
                )
            else:
                logging.info(
                    f"  ✅ types: [{', '.join(classes_and_types[class_loaded])}] ➡️ `{class_loaded}` "
                )
        logging.info("\n")
        if len(scenario_plugin_factory.failed_plugins) > 0:
            logging.info("Failed to load Scenario Plugins:\n")
            for failed in scenario_plugin_factory.failed_plugins:
                module_name, class_name, error = failed
                logging.error(f"⛔ Class: {class_name} Module: {module_name}")
                logging.error(f"⚠️ {error}\n")
        health_check_telemetry_queue = queue.Queue()
        health_checker = HealthChecker(iterations)
        health_check_worker = threading.Thread(target=health_checker.run_health_check,
                                               args=(health_check_config, health_check_telemetry_queue))
        health_check_worker.start()

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
                        try:
                            scenario_plugin = scenario_plugin_factory.create_plugin(
                                scenario_type
                            )
                        except ScenarioPluginNotFound:
                            logging.error(
                                f"impossible to find scenario {scenario_type}, plugin not found. Exiting"
                            )
                            sys.exit(1)

                        failed_post_scenarios, scenario_telemetries = (
                            scenario_plugin.run_scenarios(
                                run_uuid, scenarios_list, config, telemetry_ocp
                            )
                        )
                        chaos_telemetry.scenarios.extend(scenario_telemetries)

                        post_critical_alerts = 0
                        if check_critical_alerts:
                            prometheus_plugin.critical_alerts(
                                prometheus,
                                summary,
                                run_uuid,
                                scenario_type,
                                start_time,
                                datetime.datetime.now(),
                            )

                            chaos_output.critical_alerts = summary
                            post_critical_alerts = len(summary.post_chaos_alerts)
                            if post_critical_alerts > 0:
                                logging.error(
                                    "Post chaos critical alerts firing please check, exiting"
                                )
                                break

            iteration += 1
            health_checker.current_iterations += 1

        # telemetry
        # in order to print decoded telemetry data even if telemetry collection
        # is disabled, it's necessary to serialize the ChaosRunTelemetry object
        # to json, and recreate a new object from it.
        end_time = int(time.time())
        health_check_worker.join()
        try:
            chaos_telemetry.health_checks = health_check_telemetry_queue.get_nowait()
        except queue.Empty:
            chaos_telemetry.health_checks = None

        # if platform is openshift will be collected
        # Cloud platform and network plugins metadata
        # through OCP specific APIs
        if distribution == "openshift":
            logging.info(
                "collecting OCP cluster metadata, this may take few minutes...."
            )
            telemetry_ocp.collect_cluster_metadata(chaos_telemetry)
        else:
            logging.info("collecting Kubernetes cluster metadata....")
            telemetry_k8s.collect_cluster_metadata(chaos_telemetry)

        telemetry_json = chaos_telemetry.to_json()
        decoded_chaos_run_telemetry = ChaosRunTelemetry(json.loads(telemetry_json))
        chaos_output.telemetry = decoded_chaos_run_telemetry
        logging.info(f"Chaos data:\n{chaos_output.to_json()}")
        if enable_elastic:
            elastic_telemetry = ElasticChaosRunTelemetry(
                chaos_run_telemetry=decoded_chaos_run_telemetry
            )
            result = elastic_search.push_telemetry(
                elastic_telemetry, elastic_telemetry_index
            )
            if result == -1:
                safe_logger.error(
                    f"failed to save telemetry on elastic search: {chaos_output.to_json()}"
                )

        if config["telemetry"]["enabled"]:
            logging.info(
                f"telemetry data will be stored on s3 bucket folder: {telemetry_api_url}/files/"
                f'{(config["telemetry"]["telemetry_group"] if config["telemetry"]["telemetry_group"] else "default")}/'
                f"{telemetry_request_id}"
            )
            logging.info(f"telemetry upload log: {safe_logger.log_file_name}")
            try:
                telemetry_k8s.send_telemetry(
                    config["telemetry"], telemetry_request_id, chaos_telemetry
                )
                telemetry_k8s.put_critical_alerts(
                    telemetry_request_id, config["telemetry"], summary
                )
                # prometheus data collection is available only on Openshift
                if config["telemetry"]["prometheus_backup"]:
                    prometheus_archive_files = ""
                    if distribution == "openshift":
                        prometheus_archive_files = (
                            telemetry_ocp.get_ocp_prometheus_data(
                                config["telemetry"], telemetry_request_id
                            )
                        )
                    else:
                        if (
                                config["telemetry"]["prometheus_namespace"]
                                and config["telemetry"]["prometheus_pod_name"]
                                and config["telemetry"]["prometheus_container_name"]
                        ):
                            try:
                                prometheus_archive_files = (
                                    telemetry_k8s.get_prometheus_pod_data(
                                        config["telemetry"],
                                        telemetry_request_id,
                                        config["telemetry"]["prometheus_pod_name"],
                                        config["telemetry"][
                                            "prometheus_container_name"
                                        ],
                                        config["telemetry"]["prometheus_namespace"],
                                    )
                                )
                            except Exception as e:
                                logging.error(
                                    f"failed to get prometheus backup with exception {str(e)}"
                                )
                        else:
                            logging.warning(
                                "impossible to backup prometheus,"
                                "check if config contains telemetry.prometheus_namespace, "
                                "telemetry.prometheus_pod_name and "
                                "telemetry.prometheus_container_name"
                            )
                    if prometheus_archive_files:
                        safe_logger.info("starting prometheus archive upload:")
                        telemetry_k8s.put_prometheus_data(
                            config["telemetry"],
                            prometheus_archive_files,
                            telemetry_request_id,
                        )

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
                    elastic_search,
                    run_uuid,
                    start_time,
                    end_time,
                    alert_profile,
                    elastic_alerts_index
                )

            else:
                logging.error("Alert profile is not defined")
                return 1
                # sys.exit(1)
        if enable_metrics:
            logging.info(f'Capturing metrics using file {metrics_profile}')
            prometheus_plugin.metrics(
                prometheus,
                elastic_search,
                run_uuid,
                start_time,
                end_time,
                metrics_profile,
                elastic_metrics_index
            )

        if post_critical_alerts > 0:
            logging.error("Critical alerts are firing, please check; exiting")
            # sys.exit(2)
            return 2

        if failed_post_scenarios:
            logging.error(
                "Post scenarios are still failing at the end of all iterations"
            )
            # sys.exit(2)
            return 2
        if health_checker.ret_value != 0:
            logging.error("Health check failed for the applications, Please check; exiting")
            return health_checker.ret_value

        logging.info(
            "Successfully finished running Kraken. UUID for the run: "
            "%s. Report generated at %s. Exiting" % (run_uuid, report_file)
        )
    else:
        logging.error("Cannot find a config at %s, please check" % (cfg))
        # sys.exit(1)
        return 2

    return 0


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

    parser.add_option(
        "--junit-testcase",
        dest="junit_testcase",
        help="junit test case description",
        default=None,
    )

    parser.add_option(
        "--junit-testcase-path",
        dest="junit_testcase_path",
        help="junit test case path",
        default=None,
    )

    parser.add_option(
        "--junit-testcase-version",
        dest="junit_testcase_version",
        help="junit test case version",
        default=None,
    )

    (options, args) = parser.parse_args()
    report_file = options.output
    tee_handler = TeeLogHandler()
    handlers = [
        logging.FileHandler(report_file, mode="w"),
        logging.StreamHandler(),
        tee_handler,
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )
    option_error = False

    # used to check if there is any missing or wrong parameter that prevents
    # the creation of the junit file
    junit_error = False
    junit_normalized_path = None
    retval = 0
    junit_start_time = time.time()
    # checks if both mandatory options for junit are set
    if options.junit_testcase_path and not options.junit_testcase:
        logging.error(
            "please set junit test case description with --junit-testcase [description] option"
        )
        option_error = True
        junit_error = True

    if options.junit_testcase and not options.junit_testcase_path:
        logging.error(
            "please set junit test case path with --junit-testcase-path [path] option"
        )
        option_error = True
        junit_error = True

    # normalized path
    if options.junit_testcase:
        junit_normalized_path = os.path.normpath(options.junit_testcase_path)

        if not os.path.exists(junit_normalized_path):
            logging.error(
                f"{junit_normalized_path} do not exists, please select a valid path"
            )
            option_error = True
            junit_error = True

        if not os.path.isdir(junit_normalized_path):
            logging.error(
                f"{junit_normalized_path} is a file, please select a valid folder path"
            )
            option_error = True
            junit_error = True

        if not os.access(junit_normalized_path, os.W_OK):
            logging.error(
                f"{junit_normalized_path} is not writable, please select a valid path"
            )
            option_error = True
            junit_error = True

    if options.cfg is None:
        logging.error("Please check if you have passed the config")
        option_error = True

    if option_error:
        retval = 1
    else:
        retval = main(options.cfg)

    junit_endtime = time.time()

    # checks the minimum required parameters to write the junit file
    if junit_normalized_path and not junit_error:
        junit_testcase_xml = get_junit_test_case(
            success=True if retval == 0 else False,
            time=int(junit_endtime - junit_start_time),
            test_suite_name="chaos-krkn",
            test_case_description=options.junit_testcase,
            test_stdout=tee_handler.get_output(),
            test_version=options.junit_testcase_version,
        )
        junit_testcase_file_path = (
            f"{junit_normalized_path}/junit_krkn_{int(time.time())}.xml"
        )
        logging.info(f"writing junit XML testcase in {junit_testcase_file_path}")
        with open(junit_testcase_file_path, "w") as stream:
            stream.write(junit_testcase_xml)

    sys.exit(retval)