import arcaflowengine

def run(scenarios_list):
    for scenario in scenarios_list:
        engineArgs= arcaflowengine.EngineArgs()
        engineArgs.context=scenario
        engineArgs.config="{}/config.yaml".format(scenario)
        engineArgs.input="{}/input.yaml".format(scenario)
        arcaflowengine.run(engineArgs)