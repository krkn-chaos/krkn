import logging
import kraken.invoke.command as runcommand
import kraken.cerberus.setup as cerberus
import kraken.post_actions.actions as post_actions
import time


# Run pod based scenarios
def run(kubeconfig_path, scenarios_list, config, failed_post_scenarios, wait_duration):
    try:
        # Loop to run the scenarios starts here
        for pod_scenario in scenarios_list:
            if len(pod_scenario) > 1:
                pre_action_output = post_actions.run(kubeconfig_path, pod_scenario[1])
            else:
                pre_action_output = ""
            scenario_logs = runcommand.invoke(
                "powerfulseal autonomous --use-pod-delete-instead-"
                "of-ssh-kill --policy-file %s --kubeconfig %s "
                "--no-cloud --inventory-kubernetes --headless" % (pod_scenario[0], kubeconfig_path)
            )

            # Display pod scenario logs/actions
            print(scenario_logs)

            logging.info("Scenario: %s has been successfully injected!" % (pod_scenario[0]))
            logging.info("Waiting for the specified duration: %s" % (wait_duration))
            time.sleep(wait_duration)

            failed_post_scenarios = post_actions.check_recovery(
                kubeconfig_path, pod_scenario, failed_post_scenarios, pre_action_output
            )
            cerberus.publish_kraken_status(config, failed_post_scenarios)
    except Exception as e:
        logging.error("Failed to run scenario: %s. Encountered the following " "exception: %s" % (pod_scenario[0], e))
    return failed_post_scenarios
