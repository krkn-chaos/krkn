import logging
import kraken.invoke.command as runcommand


def run(kubeconfig_path, scenario, pre_action_output=""):

    if scenario.endswith(".yaml") or scenario.endswith(".yml"):
        logging.error("Powerfulseal support has recently been removed. Please switch to using plugins instead.")
    elif scenario.endswith(".py"):
        action_output = runcommand.invoke("python3 " + scenario).strip()
        if pre_action_output:
            if pre_action_output == action_output:
                logging.info(scenario + " post action checks passed")
            else:
                logging.info(scenario + " post action response did not match pre check output")
                logging.info("Pre action output: " + str(pre_action_output) + "\n")
                logging.info("Post action output: " + str(action_output))
                return False
    elif scenario != "":
        # invoke custom bash script
        action_output = runcommand.invoke(scenario).strip()
        if pre_action_output:
            if pre_action_output == action_output:
                logging.info(scenario + " post action checks passed")
            else:
                logging.info(scenario + " post action response did not match pre check output")
                return False

    return action_output


# Perform the post scenario actions to see if components recovered
def check_recovery(kubeconfig_path, scenario, failed_post_scenarios, pre_action_output):
    if failed_post_scenarios:
        for failed_scenario in failed_post_scenarios:
            post_action_output = run(kubeconfig_path, failed_scenario[0], failed_scenario[1])
            if post_action_output is not False:
                failed_post_scenarios.remove(failed_scenario)
            else:
                logging.info("Post action scenario " + str(failed_scenario) + "is still failing")

    # check post actions
    if len(scenario) > 1:
        post_action_output = run(kubeconfig_path, scenario[1], pre_action_output)
        if post_action_output is False:
            failed_post_scenarios.append([scenario[1], pre_action_output])

    return failed_post_scenarios
