
import time
import logging
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
    def __init__(self, kubevirt_check_config, iterations, krkn_lib: KrknKubernetes, threads_limt=20):
        self.iterations = iterations
        self.namespace = get_yaml_item_value(kubevirt_check_config, "namespace", "")
        self.vm_list = []
        self.threads = []
        self.threads_limit = threads_limt
        if self.namespace == "":
            logging.info("kube virt checks config is not defined, skipping them")
            return
        vmi_name_match = get_yaml_item_value(kubevirt_check_config, "name", ".*")
        self.krkn_lib = krkn_lib
        self.disconnected =  get_yaml_item_value(kubevirt_check_config, "disconnected", False)
        self.only_failures =  get_yaml_item_value(kubevirt_check_config, "only_failures", False)
        self.interval = get_yaml_item_value(kubevirt_check_config, "interval", 2)
        try:
            self.kube_vm_plugin = KubevirtVmOutageScenarioPlugin()
            self.kube_vm_plugin.init_clients(k8s_client=krkn_lib)
        
        except Exception as e:
            logging.error('Virt Check init exception: ' + str(e))
            return 
        vmis = self.kube_vm_plugin.get_vmis(vmi_name_match,self.namespace)
        
        for vmi in vmis:
            node_name = vmi.get("status",{}).get("nodeName")
            vmi_name = vmi.get("metadata",{}).get("name")
            ip_address = vmi.get("status",{}).get("interfaces",[])[0].get("ipAddress")
            self.vm_list.append(VirtCheck({'vm_name':vmi_name, 'ip_address': ip_address, 'namespace':self.namespace, 'node_name':node_name}))

    def check_disconnected_access(self, ip_address: str, worker_name:str = ''):

        virtctl_vm_cmd = f"ssh core@{worker_name} 'ssh -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=no root@{ip_address} 2>&1 | grep Permission' && echo 'True' || echo 'False'"
        if 'True' in invoke_no_exit(virtctl_vm_cmd):
            return True
        else:
            return False

    def get_vm_access(self, vm_name: str = '', namespace: str = ''):
        """
        This method returns True when the VM is access and an error message when it is not, using virtctl protocol
        :param vm_name:
        :param namespace:
        :return: virtctl_status 'True' if successful, or an error message if it fails.
        """
        virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=2' root@{vm_name} -n {namespace}"
        check_virtctl_vm_cmd = f"virtctl ssh --local-ssh-opts='-o BatchMode=yes' --local-ssh-opts='-o PasswordAuthentication=no' --local-ssh-opts='-o ConnectTimeout=2' root@{vm_name} -n {namespace} 2>&1 |egrep 'denied|verification failed'  && echo 'True' || echo 'False'"
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

    def batch_list(self,  queue: queue.Queue, batch_size=20):
        # Provided prints to easily visualize how the threads are processed.    
        for i in range (0, len(self.vm_list),batch_size):
            sub_list = self.vm_list[i: i+batch_size]
            index = i
            t = threading.Thread(target=self.run_virt_check,name=str(index), args=(sub_list,queue))
            self.threads.append(t)
            t.start()

    
    def run_virt_check(self, vm_list_batch, virt_check_telemetry_queue: queue.Queue):
        
        virt_check_telemetry = []
        virt_check_tracker = {}
        while self.current_iterations < self.iterations:
            for vm in vm_list_batch:
                try: 
                    if not self.disconnected: 
                        vm_status = self.get_vm_access(vm.vm_name, vm.namespace)
                    else:
                        vm_status = self.check_disconnected_access(vm.ip_address, vm.node_name)
                except Exception:
                    vm_status = False
                
                if vm.vm_name not in virt_check_tracker:
                    start_timestamp = datetime.now()
                    virt_check_tracker[vm.vm_name] = {
                        "vm_name": vm.vm_name,
                        "ip_address": vm.ip_address,
                        "namespace": vm.namespace,
                        "node_name": vm.node_name,
                        "status": vm_status,
                        "start_timestamp": start_timestamp
                    }
                else:
                    if vm_status != virt_check_tracker[vm.vm_name]["status"]:
                        end_timestamp = datetime.now()
                        start_timestamp = virt_check_tracker[vm.vm_name]["start_timestamp"]
                        duration = (end_timestamp - start_timestamp).total_seconds()
                        virt_check_tracker[vm.vm_name]["end_timestamp"] = end_timestamp.isoformat()
                        virt_check_tracker[vm.vm_name]["duration"] = duration
                        virt_check_tracker[vm.vm_name]["start_timestamp"] = start_timestamp.isoformat()
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
        virt_check_telemetry_queue.put(virt_check_telemetry)
