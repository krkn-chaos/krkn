import kraken.invoke.command as runcommand
import logging
import time
import sys
import requests
import yaml
import kraken.cerberus.setup as cerberus


# Inject litmus scenarios defined in the config
def run(scenarios_list, config, litmus_uninstall, wait_duration, litmus_namespace):
    # Loop to run the scenarios starts here
    for l_scenario in scenarios_list:
        start_time = int(time.time())
        try:
            for item in l_scenario:
                runcommand.invoke("kubectl apply -f %s -n %s" % (item, litmus_namespace))
                if "http" in item:
                    f = requests.get(item)
                    yaml_item = list(yaml.safe_load_all(f.content))[0]
                else:
                    with open(item, "r") as f:
                        yaml_item = list(yaml.safe_load_all(f))[0]

                if yaml_item["kind"] == "ChaosEngine":
                    engine_name = yaml_item["metadata"]["name"]
                    experiment_names = yaml_item["spec"]["experiments"]
                    experiment_namespace = yaml_item["metadata"]["namespace"]
                    if experiment_namespace != "litmus":
                        logging.error(
                            "Specified namespace: %s in the scenario: %s is not supported, please switch it to litmus"
                            % (experiment_namespace, l_scenario)
                        )
                        sys.exit(1)
                    for expr in experiment_names:
                        expr_name = expr["name"]
                        experiment_result = check_experiment(engine_name, expr_name, litmus_namespace)
                        if experiment_result:
                            logging.info("Scenario: %s has been successfully injected!" % item)
                        else:
                            logging.info("Scenario: %s was not successfully injected, please check" % item)
                            if litmus_uninstall:
                                delete_chaos(litmus_namespace)
                            sys.exit(1)
            if litmus_uninstall:
                delete_chaos(litmus_namespace)
            logging.info("Waiting for the specified duration: %s" % wait_duration)
            time.sleep(wait_duration)
            end_time = int(time.time())
            cerberus.get_status(config, start_time, end_time)
        except Exception as e:
            logging.error("Failed to run litmus scenario: %s. Encountered " "the following exception: %s" % (item, e))
            sys.exit(1)


# Install litmus and wait until pod is running
def install_litmus(version, namespace):
    logging.info("Installing version %s of litmus in namespace %s" % (version, namespace))
    litmus_install = runcommand.invoke(
        "kubectl -n %s apply -f " "https://litmuschaos.github.io/litmus/litmus-operator-%s.yaml" % (namespace, version)
    )
    if "unable" in litmus_install:
        logging.info("Unable to install litmus because " + str(litmus_install))
        sys.exit(1)

    runcommand.invoke(
        "oc patch -n %s deployment.apps/chaos-operator-ce --type=json --patch ' "
        '[ { "op": "add", "path": "/spec/template/spec/containers/0/env/-", '
        '"value": { "name": "ANALYTICS", "value": "FALSE" } } ]\'' % namespace
    )
    logging.info("Waiting for litmus operator to become available")
    runcommand.invoke("oc wait deploy -n %s chaos-operator-ce --for=condition=Available" % namespace)


def deploy_all_experiments(version_string, namespace):

    if not version_string.startswith("v"):
        logging.error("Incorrect version string for litmus, needs to start with 'v' " "followed by a number")
        sys.exit(1)
    version = version_string[1:]
    logging.info("Installing all litmus experiments")
    runcommand.invoke(
        "kubectl -n %s apply -f "
        "https://hub.litmuschaos.io/api/chaos/%s?file=charts/generic/experiments.yaml" % (namespace, version)
    )


def wait_for_initialized(engine_name, experiment_name, namespace):
    chaos_engine = runcommand.invoke(
        "kubectl get chaosengines/%s -n %s -o jsonpath='{.status.engineStatus}'" % (engine_name, namespace)
    )
    engine_status = chaos_engine.strip()
    max_tries = 30
    engine_counter = 0
    while engine_status.lower() != "initialized":
        time.sleep(10)
        logging.info("Waiting for " + experiment_name + " to be initialized")
        chaos_engine = runcommand.invoke(
            "kubectl get chaosengines/%s -n %s -o jsonpath='{.status.engineStatus}'" % (engine_name, namespace)
        )
        engine_status = chaos_engine.strip()
        if engine_counter >= max_tries:
            logging.error("Chaos engine " + experiment_name + " took longer than 5 minutes to be initialized")
            return False
        engine_counter += 1
        # need to see if error in run
        if "notfound" in engine_status.lower():
            logging.info("Chaos engine was not found")
            return False
    return True


def wait_for_status(engine_name, expected_status, experiment_name, namespace):

    if expected_status == "running":
        response = wait_for_initialized(engine_name, experiment_name, namespace)
        if not response:
            logging.info("Chaos engine never initialized, exiting")
            return False
    chaos_engine = runcommand.invoke(
        "kubectl get chaosengines/%s -n %s -o jsonpath='{.status.experiments[0].status}'" % (engine_name, namespace)
    )
    engine_status = chaos_engine.strip()
    max_tries = 30
    engine_counter = 0
    while engine_status.lower() != expected_status:
        time.sleep(10)
        logging.info("Waiting for " + experiment_name + " to be " + expected_status)
        chaos_engine = runcommand.invoke(
            "kubectl get chaosengines/%s -n %s -o jsonpath='{.status.experiments[0].status}'" % (engine_name, namespace)
        )
        engine_status = chaos_engine.strip()
        if engine_counter >= max_tries:
            logging.error("Chaos engine " + experiment_name + " took longer than 5 minutes to be " + expected_status)
            return False
        engine_counter += 1
        # need to see if error in run
        if "notfound" in engine_status.lower():
            logging.info("Chaos engine was not found")
            return False
    return True


# Check status of experiment
def check_experiment(engine_name, experiment_name, namespace):

    wait_response = wait_for_status(engine_name, "running", experiment_name, namespace)

    if wait_response:
        wait_for_status(engine_name, "completed", experiment_name, namespace)
    else:
        sys.exit(1)

    chaos_result = runcommand.invoke(
        "kubectl get chaosresult %s"
        "-%s -n %s -o "
        "jsonpath='{.status.experimentStatus.verdict}'" % (engine_name, experiment_name, namespace)
    )
    if chaos_result == "Pass":
        logging.info("Engine " + str(engine_name) + " finished with status " + str(chaos_result))
        return True
    else:
        chaos_result = runcommand.invoke(
            "kubectl get chaosresult %s"
            "-%s -n %s -o jsonpath="
            "'{.status.experimentStatus.failStep}'" % (engine_name, experiment_name, namespace)
        )
        logging.info("Chaos scenario:" + engine_name + " failed with error: " + str(chaos_result))
        logging.info(
            "See 'kubectl get chaosresult %s"
            "-%s -n %s -o yaml' for full results" % (engine_name, experiment_name, namespace)
        )
        return False


# Delete all chaos engines in a given namespace
def delete_chaos_experiments(namespace):

    namespace_exists = runcommand.invoke("oc get project -o name | grep -c " + namespace + " | xargs")
    if namespace_exists.strip() != "0":
        chaos_exp_exists = runcommand.invoke_no_exit("kubectl get chaosexperiment")
        if "returned non-zero exit status 1" not in chaos_exp_exists:
            logging.info("Deleting all litmus experiments")
            runcommand.invoke("kubectl delete chaosexperiment --all -n " + str(namespace))


# Delete all chaos engines in a given namespace
def delete_chaos(namespace):

    namespace_exists = runcommand.invoke("oc get project -o name | grep -c " + namespace + " | xargs")
    if namespace_exists.strip() != "0":
        logging.info("Deleting all litmus run objects")
        chaos_engine_exists = runcommand.invoke_no_exit("kubectl get chaosengine")
        if "returned non-zero exit status 1" not in chaos_engine_exists:
            runcommand.invoke("kubectl delete chaosengine --all -n " + str(namespace))
        chaos_result_exists = runcommand.invoke_no_exit("kubectl get chaosresult")
        if "returned non-zero exit status 1" not in chaos_result_exists:
            runcommand.invoke("kubectl delete chaosresult --all -n " + str(namespace))
    else:
        logging.info(namespace + " namespace doesn't exist")


def uninstall_litmus(version, litmus_namespace):
    namespace_exists = runcommand.invoke("oc get project -o name | grep -c " + litmus_namespace + " | xargs")
    if namespace_exists.strip() != "0":
        logging.info("Uninstalling Litmus operator")
        runcommand.invoke_no_exit(
            "kubectl delete -n %s -f "
            "https://litmuschaos.github.io/litmus/litmus-operator-%s.yaml" % (litmus_namespace, version)
        )
        logging.info("Deleting litmus crd")
        runcommand.invoke_no_exit("kubectl get crds | grep litmus | awk '{print $1}' | xargs -I {} oc delete crd/{}")
