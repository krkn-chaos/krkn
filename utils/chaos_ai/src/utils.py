import re


def get_load(fault):
    params = re.findall(r'\(.*?\)', fault)
    load = 100
    if len(params) > 0:
        load = params[0].strip('()')
        fault = fault.strip(params[0])
    return fault, load
