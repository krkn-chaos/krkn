#!/usr/bin/env python
#
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import random
import logging
from krkn_lib.k8s import KrknKubernetes


# krkn_lib
# Pick a random managedcluster with specified label selector
def get_managedcluster(
    managedcluster_name, label_selector, instance_kill_count, kubecli: KrknKubernetes
):

    if managedcluster_name in kubecli.list_killable_managedclusters():
        return [managedcluster_name]
    elif managedcluster_name:
        logging.info(
            "managedcluster with provided managedcluster_name does not exist or the managedcluster might "
            "be in unavailable state."
        )
    managedclusters = kubecli.list_killable_managedclusters(label_selector)
    if not managedclusters:
        raise Exception(
            "Available managedclusters with the provided label selector do not exist"
        )
    logging.info(
        "Available managedclusters with the label selector %s: %s"
        % (label_selector, managedclusters)
    )
    number_of_managedclusters = len(managedclusters)
    if instance_kill_count == number_of_managedclusters:
        return managedclusters
    managedclusters_to_return = []
    for i in range(instance_kill_count):
        managedcluster_to_add = managedclusters[
            random.randint(0, len(managedclusters) - 1)
        ]
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
