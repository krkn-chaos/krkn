Supported Cloud Providers:

- [AWS](#aws)
- [GCP](#gcp)
- [Openstack](#openstack)
- [Azure](#azure)
- [Alibaba](#alibaba)
- [VMware](#vmware)
- [IBMCloud](#ibmcloud)

## AWS

**NOTE**: For clusters with AWS make sure [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) is installed and properly [configured](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html) using an AWS account

## GCP
**NOTE**: For clusters with GCP make sure [GCP CLI](https://cloud.google.com/sdk/docs/install#linux) is installed.

A google service account is required to give proper authentication to GCP for node actions. See [here](https://cloud.google.com/docs/authentication/getting-started) for how to create a service account.

**NOTE**: A user with 'resourcemanager.projects.setIamPolicy' permission is required to grant project-level permissions to the service account.

After creating the service account you will need to enable the account using the following: ```export GOOGLE_APPLICATION_CREDENTIALS="<serviceaccount.json>"```

## Openstack

**NOTE**: For clusters with Openstack Cloud, ensure to create and source the [OPENSTACK RC file](https://docs.openstack.org/newton/user-guide/common/cli-set-environment-variables-using-openstack-rc.html) to set the OPENSTACK environment variables from the server where Kraken runs.

## Azure

**NOTE**: For Azure node killing scenarios, make sure [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli?view=azure-cli-latest) is installed.

You will also need to create a service principal and give it the correct access, see [here](https://docs.openshift.com/container-platform/4.5/installing/installing_azure/installing-azure-account.html) for creating the service principal and setting the proper permissions.

To properly run the service principal requires “Azure Active Directory Graph/Application.ReadWrite.OwnedBy” api permission granted and “User Access Administrator”.

Before running you will need to set the following:
1. Login using ```az login```

2. ```export AZURE_TENANT_ID=<tenant_id>```

3. ```export AZURE_CLIENT_SECRET=<client secret>```

4. ```export AZURE_CLIENT_ID=<client id>```

## Alibaba

See the [Installation guide](https://www.alibabacloud.com/help/en/alibaba-cloud-cli/latest/installation-guide) to install alicloud cli.

1. ```export ALIBABA_ID=<access_key_id>```

2. ```export ALIBABA_SECRET=<access key secret>```

3. ```export ALIBABA_REGION_ID=<region id>```

Refer to [region and zone page](https://www.alibabacloud.com/help/en/elastic-compute-service/latest/regions-and-zones#concept-2459516) to get the region id for the region you are running on.

Set cloud_type to either alibaba or alicloud in your node scenario yaml file.

## VMware

Set the following environment variables

1. ```export VSPHERE_IP=<vSphere_client_IP_address>```

2. ```export VSPHERE_USERNAME=<vSphere_client_username>```

3. ```export VSPHERE_PASSWORD=<vSphere_client_password>```

These are the credentials that you would normally use to access the vSphere client.


## IBMCloud
If no api key is set up with proper VPC resource permissions, use the following to create: 
* Access group
* Service id with the following access
  * With policy **VPC Infrastructure Services**
  * Resources = All
  * Roles: 
    * Editor
    * Administrator 
    * Operator  
    * Viewer
* API Key

Set the following environment variables

1. ```export IBMC_URL=https://<region>.iaas.cloud.ibm.com/v1```

2. ```export IBMC_APIKEY=<ibmcloud_api_key>```
