import subprocess
import logging


# Invokes a given command and returns the stdout
def invoke(command):
    try:
        output = subprocess.check_output(command, shell=True,
                                         universal_newlines=True)
    except Exception:
        logging.error("Failed to run %s" % (command))
    return output
