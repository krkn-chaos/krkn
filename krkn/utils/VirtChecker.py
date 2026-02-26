
import time
import logging
import math
import queue
from datetime import datetime
from krkn_lib.models.telemetry.models import VirtCheck
from krkn.invoke.command import invoke_no_exit
from krkn.scenario_plugins.kubevirt_vm_outage.kubevirt_vm_outage_scenario_plugin import KubevirtVmOutageScenarioPlugin
from krkn_lib.k8s import KrknKubernetes
import threading
from krkn_lib.utils.functions import get_yaml_item_value


class VirtChecker:
    current_iterations: int = 0
    ret_value = 0
    def __init__(self, kubevirt_check_config, iterations, krkn_lib: KrknKubernetes, threads_limit=20):
        self.iterations = iterations
        self.namespace = get_yaml_item_value(kubevirt_check_config, "namespace", "")
        self.vm_list = []
        self.threads = []
        self.iteration_lock = threading.Lock()  # Lock to protect current_iterations
        self.threads_limit = threads_limit
        # setting to 0 in case no variables are set, so no threads later get made
        self.batch_size = 0
        self.ret_value = 0
        vmi_name_match = get_yaml_item_value(kubevirt_check_config, "name", ".*")
        self.krkn_lib = krkn_lib
        self.disconnected =  get_yaml_item_value(kubevirt_check_config, "disconnected", False)
        self.only_failures =  get_yaml_item_value(kubevirt_check_config, "only_failures", False)
        self.interval = get_yaml_item_value(kubevirt_check_config, "interval", 2)
        self.ssh_node = get_yaml_item_value(kubevirt_check_config, "ssh_node", "")
        self.node_names = get_yaml_item_value(kubevirt_check_config, "node_names", "")
        self.exit_on_failure = get_yaml_item_value(kubevirt_check_config, "exit_on_failure", False)
        if self.namespace == "":
            logging.info("kube virt checks config is not defined, skipping them")
            return
        try:
            self.kube_vm_plugin = KubevirtVmOutageScenarioPlugin()
            self.kube_vm_plugin.init_clients(k8s_client=krkn_lib)

            self.kube_vm_plugin.get_vmis(vmi_name_match,self.namespace)
        except Exception as e:
            logging.error('Virt Check init exception: ' + str(e))
            return
        # See if multiple node names exist
        node_name_list = [node_name for node_name in self.node_names.split(',') if node_name]
        for vmi in self.kube_vm_plugin.vmis_list:
            node_name = vmi.get("status",{}).get("nodeName")
            vmi_name = vmi.get("metadata",{}).get("name")
            interfaces = vmi.get("status",{}).get("interfaces",[])
            if not interfaces:
                logging.warning(f"VMI {vmi_name} has no network interfaces, skipping")
                continue
            ip_address = interfaces[0].get("ipAddress")
            namespace = vmi.get("metadata",{}).get("namespace")
            # If node_name_list exists, only add if node name is in list

            if len(node_name_list) > 0 and node_name in node_name_list:
                self.vm_list.append(VirtCheck({'vm_name':vmi_name, 'ip_address': ip_address, 'namespace':namespace, 'node_name':node_name, "new_ip_address":""}))
            elif len(node_name_list) == 0:
                # If node_name_list is blank, add all vms
                self.vm_list.append(VirtCheck({'vm_name':vmi_name, 'ip_address': ip_address, 'namespace':namespace, 'node_name':node_name, "new_ip_address":""}))
        self.batch_size = math.ceil(len(self.vm_list)/self.threads_limit)

    def check_disconnected_access(self, ip_address: str, worker_name:str = '', vmi_name: str = ''):
        
        virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{ip_address}'"
        
        all_out = invoke_no_exit(virtctl_vm_cmd)
        logging.debug(f"Checking disconnected access for {ip_address} on {worker_name} output: {all_out}")
        virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
        output = invoke_no_exit(virtctl_vm_cmd)
        if 'True' in output:
            logging.debug(f"Disconnected access for {ip_address} on {worker_name} is successful: {output}")
            return True, None, None
        else:
            logging.debug(f"Disconnected access for {ip_address} on {worker_name} is failed: {output}")
            vmi = self.kube_vm_plugin.get_vmi(vmi_name,self.namespace)
            interfaces = vmi.get("status",{}).get("interfaces",[])
            new_ip_address = interfaces[0].get("ipAddress") if interfaces else None
            new_node_name = vmi.get("status",{}).get("nodeName")
            # if vm gets deleted, it'll start up with a new ip address
            if new_ip_address != ip_address:
                virtctl_vm_cmd = f"ssh core@{worker_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(f"Disconnected access for {ip_address} on {worker_name}: {new_output}")
                if 'True' in new_output:
                    return True, new_ip_address, None
            # if node gets stopped, vmis will start up with a new node (and with new ip)
            if new_node_name != worker_name:
                virtctl_vm_cmd = f"ssh core@{new_node_name} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(f"Disconnected access for {ip_address} on {new_node_name}: {new_output}")
                if 'True' in new_output:
                    return True, new_ip_address, new_node_name
            # try to connect with a common "up" node as last resort
            if self.ssh_node:
                # using new_ip_address here since if it hasn't changed it'll match ip_address
                virtctl_vm_cmd = f"ssh core@{self.ssh_node} -o ConnectTimeout=5 'ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@{new_ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
                new_output = invoke_no_exit(virtctl_vm_cmd)
                logging.debug(f"Disconnected access for {new_ip_address} on {self.ssh_node}: {new_output}")
                if 'True' in new_output:
                    return True, new_ip_address, None
        return False, None, None

    def get_vm_access(self, vm_name: str = '', namespace: str = ''):
        """
        This method returns True when the VM is accessible and an error message when it is not, using virtctl protocol
        :param vm_name:
        :param namespace:
        :return: virtctl_status 'True' if successful, or an error message if it fails.
        """
        virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=5' root@vmi/{vm_name} -n {namespace} 2>&1 |egrep 'denied|verification failed'  && echo 'True' || echo 'False'"
        check_virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=5' root@{vm_name} -n {namespace} 2>&1 |egrep 'denied|verification failed'  && echo 'True' || echo 'False'"
        if 'True' in invoke_no_exit(check_virtctl_vm_cmd):
            return True
        else:
            second_invoke = invoke_no_exit(virtctl_vm_cmd)
            if 'True' in second_invoke:
                return True
            return False
    
    def thread_join(self):
        for thread in self.threads:
            thread.join()

    def batch_list(self, queue: queue.SimpleQueue = None):
        if self.batch_size > 0:
            # Provided prints to easily visualize how the threads are processed.    
            for i in range (0, len(self.vm_list),self.batch_size):
                if i+self.batch_size > len(self.vm_list):
                    sub_list = self.vm_list[i:]
                else:
                    sub_list = self.vm_list[i: i+self.batch_size]
                index = i
                t = threading.Thread(target=self.run_virt_check,name=str(index), args=(sub_list,queue))
                self.threads.append(t)
                t.start()

    def increment_iterations(self):
        """Thread-safe method to increment current_iterations"""
        with self.iteration_lock:
            self.current_iterations += 1

    def run_virt_check(self, vm_list_batch, virt_check_telemetry_queue: queue.SimpleQueue):
        
        virt_check_telemetry = []
        virt_check_tracker = {}
        while True:
            # Thread-safe read of current_iterations
            with self.iteration_lock:
                current = self.current_iterations
            if current >= self.iterations:
                break
            for vm in vm_list_batch:
                start_time= datetime.now()
                try: 
                    if not self.disconnected: 
                        vm_status = self.get_vm_access(vm.vm_name, vm.namespace)
                    else:
                        # if new ip address exists use it 
                        if vm.new_ip_address: 
                            vm_status, new_ip_address, new_node_name = self.check_disconnected_access(vm.new_ip_address, vm.node_name, vm.vm_name)
                            # since we already set the new ip address, we don't want to reset to none each time
                        else: 
                            vm_status, new_ip_address, new_node_name = self.check_disconnected_access(vm.ip_address, vm.node_name, vm.vm_name)
                            if new_ip_address and vm.ip_address != new_ip_address:
                                vm.new_ip_address = new_ip_address
                            if new_node_name and vm.node_name != new_node_name:
                                vm.node_name = new_node_name
                except Exception:
                    logging.info('Exception in get vm status')
                    vm_status = False

                if vm.vm_name not in virt_check_tracker:
                    start_timestamp = datetime.now()
                    virt_check_tracker[vm.vm_name] = {
                        "vm_name": vm.vm_name,
                        "ip_address": vm.ip_address,
                        "namespace": vm.namespace,
                        "node_name": vm.node_name,
                        "status": vm_status,
                        "start_timestamp": start_timestamp,
                        "new_ip_address": vm.new_ip_address
                    }
                else:
                    
                    if vm_status != virt_check_tracker[vm.vm_name]["status"]:
                        end_timestamp = datetime.now()
                        start_timestamp = virt_check_tracker[vm.vm_name]["start_timestamp"]
                        duration = (end_timestamp - start_timestamp).total_seconds()
                        virt_check_tracker[vm.vm_name]["end_timestamp"] = end_timestamp.isoformat()
                        virt_check_tracker[vm.vm_name]["duration"] = duration
                        virt_check_tracker[vm.vm_name]["start_timestamp"] = start_timestamp.isoformat()
                        if vm.new_ip_address:
                            virt_check_tracker[vm.vm_name]["new_ip_address"] = vm.new_ip_address
                        if self.only_failures: 
                            if not virt_check_tracker[vm.vm_name]["status"]:
                                virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm.vm_name]))
                        else:
                            virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm.vm_name]))
                        del virt_check_tracker[vm.vm_name]
            time.sleep(self.interval)
        virt_check_end_time_stamp = datetime.now()
        for vm in virt_check_tracker.keys():
            final_start_timestamp = virt_check_tracker[vm]["start_timestamp"]
            final_duration = (virt_check_end_time_stamp - final_start_timestamp).total_seconds()
            virt_check_tracker[vm]["end_timestamp"] = virt_check_end_time_stamp.isoformat()
            virt_check_tracker[vm]["duration"] = final_duration
            virt_check_tracker[vm]["start_timestamp"] = final_start_timestamp.isoformat()
            if self.only_failures:
                if not virt_check_tracker[vm]["status"]:
                    virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm]))
            else:
                virt_check_telemetry.append(VirtCheck(virt_check_tracker[vm]))
        try:
            virt_check_telemetry_queue.put(virt_check_telemetry)
        except Exception as e:
            logging.error('Put queue error ' + str(e))
    def run_post_virt_check(self, vm_list_batch, virt_check_telemetry, post_virt_check_queue: queue.SimpleQueue):
        
        virt_check_telemetry = []
        virt_check_tracker = {}
        start_timestamp = datetime.now()
        for vm in vm_list_batch:
            
            try: 
                if not self.disconnected: 
                    vm_status = self.get_vm_access(vm.vm_name, vm.namespace)
                else:
                    vm_status, new_ip_address, new_node_name = self.check_disconnected_access(vm.ip_address, vm.node_name, vm.vm_name)
                    if new_ip_address and vm.ip_address != new_ip_address:
                        vm.new_ip_address = new_ip_address
                    if new_node_name and vm.node_name != new_node_name:
                        vm.node_name = new_node_name
            except Exception:
                vm_status = False
            
            if not vm_status:

                virt_check_tracker= {
                    "vm_name": vm.vm_name,
                    "ip_address": vm.ip_address,
                    "namespace": vm.namespace,
                    "node_name": vm.node_name,
                    "status": vm_status,
                    "start_timestamp": start_timestamp.isoformat(),
                    "new_ip_address": vm.new_ip_address,
                    "duration": 0,
                    "end_timestamp": start_timestamp.isoformat()
                }
                
                virt_check_telemetry.append(VirtCheck(virt_check_tracker))
        post_virt_check_queue.put(virt_check_telemetry)
    

    def gather_post_virt_checks(self, kubevirt_check_telem):

        post_kubevirt_check_queue = queue.SimpleQueue()
        post_threads = []

        if self.batch_size > 0:
            for i in range (0, len(self.vm_list),self.batch_size):
                sub_list = self.vm_list[i: i+self.batch_size]
                index = i
                t = threading.Thread(target=self.run_post_virt_check,name=str(index), args=(sub_list,kubevirt_check_telem, post_kubevirt_check_queue))
                post_threads.append(t)
                t.start()

            kubevirt_check_telem = []
            for thread in post_threads:
                thread.join()
                if not post_kubevirt_check_queue.empty():
                    kubevirt_check_telem.extend(post_kubevirt_check_queue.get_nowait())
        
        if self.exit_on_failure and len(kubevirt_check_telem) > 0:
            self.ret_value = 2
        return kubevirt_check_telem
