import yaml
import sys
import logging
import time
from kraken.node_actions.aws_node_scenarios import AWS
import kraken.cerberus.setup as cerberus


# filters the subnet of interest and applies the network acl to create zone outage
def run(scenarios_list, config, wait_duration):
    failed_post_scenarios = ""
    for zone_outage_config in scenarios_list:
        if len(zone_outage_config) > 1:
            with open(zone_outage_config, "r") as f:
                zone_outage_config_yaml = yaml.full_load(f)
                scenario_config = zone_outage_config_yaml["zone_outage"]
                vpc_id = scenario_config["vpc_id"]
                subnet_id = scenario_config["subnet_id"]
                duration = scenario_config["duration"]
                cloud_type = scenario_config["cloud_type"]
                network_association_ids = []

                if cloud_type.lower() == "aws":
                    cloud_object = AWS()
                else:
                    logging.error("Cloud type " + cloud_type + " is not currently supported for zone outage scenarios")
                    sys.exit(1)

                start_time = int(time.time())

                associations, original_acl_id = cloud_object.describe_network_acls(vpc_id, subnet_id)
                for entry in associations:
                    if entry["SubnetId"] == subnet_id:
                        network_association_ids.append(entry["NetworkAclAssociationId"])
                logging.info(
                    "Network association ids associated with the subnet %s: %s" % (subnet_id, network_association_ids)
                )
                acl_id = cloud_object.create_default_network_acl(vpc_id)
                new_association_id = cloud_object.replace_network_acl_association(network_association_ids[0], acl_id)

                # wait for the specified duration
                logging.info("Waiting for the specified duration: %s" % (duration))
                time.sleep(duration)

                # replace the applied acl with the previous acl in use
                logging.info("Replacing the applied acl with the original acl: %s" % (original_acl_id))
                cloud_object.replace_network_acl_association(new_association_id, original_acl_id)

                # delete the network acl created for the run
                logging.info("Deleting the network acl created for the run: %s" % (acl_id))
                cloud_object.delete_network_acl(acl_id)

                logging.info("Waiting for the specified duration: %s" % (wait_duration))
                time.sleep(wait_duration)

                end_time = int(time.time())
                cerberus.publish_kraken_status(config, failed_post_scenarios, start_time, end_time)
