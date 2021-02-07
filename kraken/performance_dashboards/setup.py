import subprocess
import logging
import git


# Installs a mutable grafana on the Kubernetes/OpenShift cluster and loads the performance dashboards
def setup(repo):
    command = "cd /tmp/performance-dashboards/dittybopper && ./deploy.sh"
    delete_repo = "rm -rf /tmp/performance-dashboards || exit 0"
    logging.info("Cloning, installing mutable grafana on the cluster and loading the dashboards")
    try:
        # delete repo to clone the latest copy if exists
        subprocess.run(delete_repo, shell=True, universal_newlines=True, timeout=45)
        # clone the repo
        git.Repo.clone_from(repo, '/tmp/performance-dashboards')
        # deploy performance dashboards
        subprocess.run(command, shell=True, universal_newlines=True)
    except Exception as e:
        logging.error("Failed to install performance-dashboards, error: %s" % (e))
