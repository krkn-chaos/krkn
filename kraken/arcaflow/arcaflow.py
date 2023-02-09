import arcaflow as arcaflow_engine

def run(scenarios_list):
    for scenario in scenarios_list:
        engineArgs= arcaflow_engine.EngineArgs()
        engineArgs.context=scenario
        engineArgs.config="{}/config.yaml".format(scenario)
        engineArgs.input="{}/input.yaml".format(scenario)
        arcaflow_engine.run(engineArgs)