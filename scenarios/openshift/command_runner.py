import subprocess
import shlex
import logging

class CommandRunner:
    @staticmethod
    #runs shell commands supporting piping without using shell=True
    def run(cmd):
        if "|" in cmd:
            commands_list = cmd.split('|')
        else:
            commands_list = []
            commands_list.append(cmd)
        i = 0
        process_handlers = {}
        try:
            for command in commands_list:
                command = command.strip()
                if i == 0:
                    process_handlers[i] = subprocess.Popen(shlex.split(command.strip(
                    )), shell=False, stdin=None, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                else:
                    process_handlers[i] = subprocess.Popen(shlex.split(command.strip(
                    )), shell=False, stdin=process_handlers[i-1].stdout, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                i = i + 1
            (output, _) = process_handlers[i-1].communicate()
            process_handlers[0].wait()
        except Exception as e:
            logging.error("Failed to run %s, error: %s" % (cmd, e))
        return output