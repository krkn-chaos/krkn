import subprocess
import logging


# Invokes a given command and returns the stdout
def invoke(command):
    try:
        output = subprocess.Popen(
            command, shell=True, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        (out, err) = output.communicate()
    except Exception as e:
        logging.error("Failed to run %s, error: %s" % (command, e))
    return out


def run(command):
    try:
        subprocess.run(command, shell=True, universal_newlines=True, timeout=45)
    except Exception:
        pass
