import kraken.invoke.command as runcommand
import logging
import time
import sys
import requests
import yaml
import kraken.cerberus.setup as cerberus


# Inject litmus scenarios defined in the config
def run(scenarios_list, config, litmus_namespaces, litmus_uninstall, wait_duration):
    # Loop to run the scenarios starts here
    for l_scenario in scenarios_list:
        try:
            for item in l_scenario:
                runcommand.invoke("kubectl apply -f %s" % item)
                if "http" in item:
                    f = requests.get(item)
                    yaml_item = list(yaml.safe_load_all(f.content))[0]
                else:
                    with open(item, "r") as f:
                        logging.info("opened yaml" + str(item))
                        yaml_item = list(yaml.safe_load_all(f))[0]

                if yaml_item["kind"] == "ChaosEngine":
                    engine_name = yaml_item["metadata"]["name"]
                    namespace = yaml_item["metadata"]["namespace"]
                    litmus_namespaces.append(namespace)
                    experiment_names = yaml_item["spec"]["experiments"]
                    for expr in experiment_names:
                        expr_name = expr["name"]
                        experiment_result = check_experiment(engine_name, expr_name, namespace)
                        if experiment_result:
                            logging.info("Scenario: %s has been successfully injected!" % item)
                        else:
                            logging.info("Scenario: %s was not successfully injected, please check" % item)
                            if litmus_uninstall:
                                for l_item in l_scenario:
                                    logging.info("item " + str(l_item))
                                    runcommand.invoke("kubectl delete -f %s" % l_item)
                            sys.exit(1)
            if litmus_uninstall:
                for item in l_scenario:
                    logging.info("item " + str(item))
                    runcommand.invoke("kubectl delete -f %s" % item)
            logging.info("Waiting for the specified duration: %s" % wait_duration)
            time.sleep(wait_duration)
            cerberus.get_status(config)
        except Exception as e:
            logging.error("Failed to run litmus scenario: %s. Encountered " "the following exception: %s" % (item, e))
            sys.exit(1)
    return litmus_namespaces


# Install litmus and wait until pod is running
def install_litmus(version):
    runcommand.invoke("kubectl apply -f " "https://litmuschaos.github.io/litmus/litmus-operator-%s.yaml" % version)

    runcommand.invoke(
        "oc patch -n litmus deployment.apps/chaos-operator-ce --type=json --patch ' "
        '[ { "op": "add", "path": "/spec/template/spec/containers/0/env/-", '
        '"value": { "name": "ANALYTICS", "value": "FALSE" } } ]\''
    )

    runcommand.invoke("oc wait deploy -n litmus chaos-operator-ce --for=condition=Available")


def deploy_all_experiments(version_string):

    if not version_string.startswith("v"):
        logging.error("Incorrect version string for litmus, needs to start with 'v' " "followed by a number")
        sys.exit(1)
    version = version_string[1:]

    runcommand.invoke(
        "kubectl apply -f " "https://hub.litmuschaos.io/api/chaos/%s?file=charts/generic/experiments.yaml" % version
    )


def delete_experiments():
    runcommand.invoke("kubectl delete chaosengine --all")


# Check status of experiment
def check_experiment(engine_name, experiment_name, namespace):
    chaos_engine = runcommand.invoke(
        "kubectl get chaosengines/%s -n %s -o jsonpath=" "'{.status.engineStatus}'" % (engine_name, namespace)
    )
    engine_status = chaos_engine.strip()
    max_tries = 30
    engine_counter = 0
    while engine_status.lower() != "running" and engine_status.lower() != "completed":
        time.sleep(10)
        logging.info("Waiting for engine to start running.")
        chaos_engine = runcommand.invoke(
            "kubectl get chaosengines/%s -n %s -o jsonpath=" "'{.status.engineStatus}'" % (engine_name, namespace)
        )
        engine_status = chaos_engine.strip()
        if engine_counter >= max_tries:
            logging.error("Chaos engine took longer than 5 minutes to be running or complete")
            return False
        engine_counter += 1
        # need to see if error in run
        if "notfound" in engine_status.lower():
            logging.info("Chaos engine was not found")
            return False

    if not chaos_engine:
        return False
    chaos_result = runcommand.invoke(
        "kubectl get chaosresult %s"
        "-%s -n %s -o "
        "jsonpath='{.status.experimentstatus.verdict}'" % (engine_name, experiment_name, namespace)
    )
    result_counter = 0
    status = chaos_result.strip()
    while status == "Awaited":
        logging.info("Waiting for chaos result to finish, sleeping 10 seconds")
        time.sleep(10)
        chaos_result = runcommand.invoke(
            "kubectl get chaosresult %s"
            "-%s -n %s -o "
            "jsonpath='{.status.experimentstatus.verdict}'" % (engine_name, experiment_name, namespace)
        )
        status = chaos_result.strip()
        if result_counter >= max_tries:
            logging.error("Chaos results took longer than 5 minutes to get a final result")
            return False
        result_counter += 1
        if "notfound" in status.lower():
            logging.info("Chaos result was not found")
            return False

    if status == "Pass":
        return True
    else:
        chaos_result = runcommand.invoke(
            "kubectl get chaosresult %s"
            "-%s -n %s -o jsonpath="
            "'{.status.experimentstatus.failStep}'" % (engine_name, experiment_name, namespace)
        )
        logging.info("Chaos result failed information: " + str(chaos_result))
        return False


# Delete all chaos engines in a given namespace
def delete_chaos(namespace):
    runcommand.invoke("kubectl delete chaosengine --all -n " + str(namespace))
    runcommand.invoke("kubectl delete chaosexperiment --all -n " + str(namespace))
    runcommand.invoke("kubectl delete chaosresult --all -n " + str(namespace))


# Uninstall litmus operator
def uninstall_litmus(version):
    runcommand.invoke("kubectl delete -f " "https://litmuschaos.github.io/litmus/litmus-operator-%s.yaml" % version)
