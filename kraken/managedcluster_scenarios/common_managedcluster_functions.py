import random
import logging
from krkn_lib.k8s import KrknKubernetes

# krkn_lib
# Pick a random managedcluster with specified label selector
def get_managedcluster(
        managedcluster_name,
        label_selector,
        instance_kill_count,
        kubecli: KrknKubernetes):

    if managedcluster_name in kubecli.list_killable_managedclusters():
        return [managedcluster_name]
    elif managedcluster_name:
        logging.info("managedcluster with provided managedcluster_name does not exist or the managedcluster might " "be in unavailable state.")
    managedclusters = kubecli.list_killable_managedclusters(label_selector)
    if not managedclusters:
        raise Exception("Available managedclusters with the provided label selector do not exist")
    logging.info("Available managedclusters with the label selector %s: %s" % (label_selector, managedclusters))
    number_of_managedclusters = len(managedclusters)
    if instance_kill_count == number_of_managedclusters:
        return managedclusters
    managedclusters_to_return = []
    for i in range(instance_kill_count):
        managedcluster_to_add = managedclusters[random.randint(0, len(managedclusters) - 1)]
        managedclusters_to_return.append(managedcluster_to_add)
        managedclusters.remove(managedcluster_to_add)
    return managedclusters_to_return


# Wait until the managedcluster status becomes Available
# krkn_lib
def wait_for_available_status(managedcluster, timeout, kubecli: KrknKubernetes):
    kubecli.watch_managedcluster_status(managedcluster, "True", timeout)


# Wait until the managedcluster status becomes Not Available
# krkn_lib
def wait_for_unavailable_status(managedcluster, timeout, kubecli: KrknKubernetes):
    kubecli.watch_managedcluster_status(managedcluster, "Unknown", timeout)
