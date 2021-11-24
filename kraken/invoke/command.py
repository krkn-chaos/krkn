import subprocess
import logging
import sys


# Invokes a given command and returns the stdout
def invoke(command, timeout=None):
    output = ""
    try:
        output = subprocess.check_output(command, shell=True, universal_newlines=True, timeout=timeout)
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (command, e))
        sys.exit(1)
    return output


# Invokes a given command and returns the stdout
def invoke_no_exit(command, timeout=None):
    output = ""
    try:
        output = subprocess.check_output(command, shell=True, universal_newlines=True, timeout=timeout)
        logging.info("output " + str(output))
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (command, e))
        return str(e)
    return output


def run(command):
    try:
        subprocess.run(command, shell=True, universal_newlines=True, timeout=45)
    except Exception:
        pass
