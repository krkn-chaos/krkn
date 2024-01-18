## CI Tests

### First steps
Edit [functional_tests](tests/functional_tests) with tests you want to run

### How to run
```./CI/run.sh```

This will run kraken using python, make sure python3 is set up and configured properly with all requirements


### Adding a test case

1. Add in simple scenario yaml file to execute under [../CI/scenarios/](legacy)

2. Copy [test_application_outages.sh](tests/test_app_outages.sh) for example on how to get started

3. Lines to change for bash script

    a. 11: Set scenario type to be your new scenario name

    b. 12: Add pointer to scenario file for the test

    c. 13: If a post action file is needed; add in pointer

    d. 14: Set filled in config yaml file name specific to your scenario

    e. 15: Make sure name of config in line 14 matches what you pass on this line

4. Add test name to [functional_tests](../CI/tests/functional_tests) file

    a. This will be the name of the file without ".sh"

5. If any changes to the main config (other than the scenario list), please be sure to add them into the [common_config](config/common_test_config.yaml)
