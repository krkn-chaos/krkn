# How to Test Your Changes/Additions

## Current list of Scenario Types

Scenario Types:
* pod-scenarios
* node-scenarios
* zone-outages
* time-scenarios
* cluster-shutdown
* container-scenarios
* node-cpu-hog
* node-io-hog
* node-memory-hog
* application-outages

## Adding a New Scenario
1. Create folder under [kraken/kraken](../kraken) with name pertinent to your scenario name.

2. Create a python file that will have a generic run function to be the base of your scenario.

    a. See [shut_down.py](../kraken/shut_down/common_shut_down_func.py) for example.

3. Add in a scenario yaml file to run your specific scenario under [scenarios](../scenarios).

    a. Try to add as many parameters as possible and be sure to give them default values in your run function.

4. Add all functionality and helper functions in file you made above (Step 2).

5. Add in caller to new scenario type in [run_kraken.py](../run_kraken.py) (around line 154).

    a. This will also require you to add the new scenario python script to your imports.

6. Add scenario type and scenario yaml to the scenario list in [config](../config/config.yaml) and [config_performance](../config/config_performance.yaml).

7. Update this doc and main README with new scenario type.

8. Add CI test for new scenario.

    a. Refer to test [Readme](../CI/README.md#adding-a-test-case) for more details.

## Follow Contribute guide

Once all you are happy with your changes, follow the [contribution](#docs/contribute.md) guide on how to create your own branch and squash your commits.
