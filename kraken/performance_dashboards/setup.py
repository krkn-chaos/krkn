import subprocess
import logging
import git
import sys
import shutil

# Installs a mutable grafana on the Kubernetes/OpenShift cluster and loads the performance dashboards


def setup(repo, distribution):
    workdir = "performance-dashboards/dittybopper"
    if distribution == "kubernetes":
        command = "./k8s-deploy.sh"
    elif distribution == "openshift":
        command = "./deploy.sh"
    else:
        logging.error("Provided distribution: %s is not supported" %
                      (distribution))
        sys.exit(1)
    logging.info(
        "Cloning, installing mutable grafana on the cluster and loading the dashboards")
    try:
        # delete repo to clone the latest copy if exists
        try:
            shutil.rmtree("performance-dashboards")
        except Exception as e:
            logging.warn(
                "Failed to remove folder: %s" % (e))
        # clone the repo
        git.Repo.clone_from(repo, "performance-dashboards")
        # deploy performance dashboards
        subprocess.run(command, shell=False, cwd=workdir,
                       universal_newlines=True)

    except Exception as e:
        logging.error(
            "Failed to install performance-dashboards, error: %s" % (e))
