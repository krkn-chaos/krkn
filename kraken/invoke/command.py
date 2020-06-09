import subprocess
import logging


# Invokes a given command and returns the stdout
def invoke(command):
    logging.info('Try invoking ' + command)
    try:
        output = subprocess.Popen(command, shell=True,
                                  universal_newlines=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        (out, err) = output.communicate()
        logging.info( "Output " + str(out) + "\n\n\nError " + str(err))
    except Exception as e:
        logging.error("Failed to run %s" % (e))
    return output


# Invoke oc debug with command
def invoke_debug_helper(node_name, command):

    return invoke("oc debug node/" + node_name + ' -- chroot /host ' + command)

