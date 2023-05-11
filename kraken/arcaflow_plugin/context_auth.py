import yaml
import os
import base64


class ContextAuth:
    clusterCertificate: str = None
    clusterCertificateData: str = None
    clusterHost: str = None
    clientCertificate: str = None
    clientCertificateData: str = None
    clientKey: str = None
    clientKeyData: str = None
    clusterName: str = None
    username: str = None
    password: str = None
    bearerToken: str = None
    # TODO: integrate in krkn-lib-kubernetes in the next iteration

    @property
    def clusterCertificateDataBase64(self):
        if self.clusterCertificateData is not None:
            return base64.b64encode(bytes(self.clusterCertificateData,'utf8')).decode("ascii")
        return

    @property
    def clientCertificateDataBase64(self):
        if self.clientCertificateData is not None:
            return base64.b64encode(bytes(self.clientCertificateData,'utf8')).decode("ascii")
        return

    @property
    def clientKeyDataBase64(self):
        if self.clientKeyData is not None:
            return base64.b64encode(bytes(self.clientKeyData,"utf-8")).decode("ascii")
        return



    def fetch_auth_data(self, kubeconfig: any):
        context_username = None
        current_context = kubeconfig["current-context"]
        if current_context is None:
            raise Exception("no current-context found in kubeconfig")

        for context in kubeconfig["contexts"]:
            if context["name"] == current_context:
                context_username = context["context"]["user"]
                self.clusterName = context["context"]["cluster"]
        if context_username is None:
            raise Exception("user not found for context {0}".format(current_context))
        if self.clusterName is None:
            raise Exception("cluster not found for context {0}".format(current_context))
        cluster_id = None
        user_id = None
        for index, user in enumerate(kubeconfig["users"]):
            if user["name"] == context_username:
                user_id = index
        if user_id is None :
            raise Exception("user {0} not found in kubeconfig users".format(context_username))

        for index, cluster in enumerate(kubeconfig["clusters"]):
            if cluster["name"] == self.clusterName:
                cluster_id = index

        if cluster_id is None:
            raise Exception(
                "no cluster {} found in kubeconfig users".format(self.clusterName)
            )

        user = kubeconfig["users"][user_id]["user"]
        cluster = kubeconfig["clusters"][cluster_id]["cluster"]
        # sets cluster api URL
        self.clusterHost = cluster["server"]
        # client certificates

        if "client-key" in user:
            try:
                self.clientKey = user["client-key"]
                self.clientKeyData = self.read_file(user["client-key"])
            except Exception as e:
                raise e

        if "client-key-data" in user:
            try:
                self.clientKeyData = base64.b64decode(user["client-key-data"]).decode('utf-8')
            except Exception as e:
                raise Exception("impossible to decode client-key-data")

        if "client-certificate" in user:
            try:
                self.clientCertificate = user["client-certificate"]
                self.clientCertificateData = self.read_file(user["client-certificate"])
            except Exception as e:
                raise e

        if "client-certificate-data" in user:
            try:
                self.clientCertificateData = base64.b64decode(user["client-certificate-data"]).decode('utf-8')
            except Exception as e:
                raise Exception("impossible to decode client-certificate-data")

        # cluster certificate authority

        if "certificate-authority" in cluster:
            try:
                self.clusterCertificate = cluster["certificate-authority"]
                self.clusterCertificateData = self.read_file(cluster["certificate-authority"])
            except Exception as e:
                raise e

        if "certificate-authority-data" in cluster:
            try:
                self.clusterCertificateData = base64.b64decode(cluster["certificate-authority-data"]).decode('utf-8')
            except Exception as e:
                raise Exception("impossible to decode certificate-authority-data")

        if "username" in user:
            self.username = user["username"]

        if "password" in user:
            self.password = user["password"]

        if "token" in user:
            self.bearerToken = user["token"]

    def read_file(self, filename:str) -> str:
        if not os.path.exists(filename):
            raise Exception("file not found {0} ".format(filename))
        with open(filename, "rb") as file_stream:
            return file_stream.read().decode('utf-8')











