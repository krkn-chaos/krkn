#!/bin/bash
SCRIPT_PATH=./CI/CRC
DEPLOYMENT_PATH=$SCRIPT_PATH/deployment.yaml

[[ ! -f $DEPLOYMENT_PATH ]] && echo "[ERROR] please run $0 from GitHub action root directory" && exit 1
[[ -z $DEPLOYMENT_NAME ]] && echo "[ERROR] please set \$DEPLOYMENT_NAME environment variable" && exit 1
[[ -z $NAMESPACE ]] && echo "[ERROR] please set \$NAMESPACE environment variable" && exit 1


OPENSSL=`which openssl 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: openssl missing, please install it and try again" && exit 1
OC=`which oc 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: oc missing, please install it and try again" && exit 1
SED=`which sed 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: sed missing, please install it and try again" && exit 1
JQ=`which jq 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: jq missing, please install it and try again" && exit 1
ENVSUBST=`which envsubst 2>/dev/null`
[[ $? != 0 ]] && echo "[ERROR]: envsubst missing, please install it and try again" && exit 1


API_PORT="6443"
API_ADDRESS="https://api.`cat host`.nip.io:${API_PORT}"
FQN=$DEPLOYMENT_NAME.apps.$API_ADDRESS


echo "[INF] deploying example deployment: $DEPLOYMENT_NAME in namespace: $NAMESPACE"
$ENVSUBST < $DEPLOYMENT_PATH | $OC apply -f - > /dev/null 2>&1

echo "[INF] creating SSL self-signed certificates for route https://$FQN"
$OPENSSL genrsa -out servercakey.pem > /dev/null 2>&1
$OPENSSL req -new -x509 -key servercakey.pem -out serverca.crt -subj "/CN=$FQN/O=Red Hat Inc./C=US" > /dev/null 2>&1
$OPENSSL genrsa -out server.key > /dev/null 2>&1
$OPENSSL req -new -key server.key -out server_reqout.txt -subj "/CN=$FQN/O=Red Hat Inc./C=US" > /dev/null 2>&1
$OPENSSL x509 -req -in server_reqout.txt -days 3650 -sha256 -CAcreateserial -CA serverca.crt -CAkey servercakey.pem -out server.crt > /dev/null 2>&1
echo "[INF] creating deployment: $DEPLOYMENT_NAME public route: https://$FQN"
$OC create route --namespace $NAMESPACE  edge --service=$DEPLOYMENT_NAME-service --cert=server.crt --key=server.key --ca-cert=serverca.crt --hostname="$FQN" > /dev/null 2>&1


echo "[INF] setting github action environment variables"

NODE_NAME="`$OC get nodes  -o json | $JQ -r '.items[0].metadata.name'`"
COVERAGE_FILE="`pwd`/coverage.md"
echo "DEPLOYMENT_NAME=$DEPLOYMENT_NAME" >> $GITHUB_ENV
echo "DEPLOYMENT_FQN=$FQN" >> $GITHUB_ENV
echo "API_ADDRESS=$API_ADDRESS" >> $GITHUB_ENV
echo "API_PORT=$API_PORT" >> $GITHUB_ENV
echo "NODE_NAME=$NODE_NAME" >> $GITHUB_ENV
echo "NAMESPACE=$NAMESPACE" >> $GITHUB_ENV
echo "COVERAGE_FILE=$COVERAGE_FILE" >> $GITHUB_ENV

echo "[INF] deployment fully qualified name will be available in \${{ env.DEPLOYMENT_NAME }} with value $DEPLOYMENT_NAME"
echo "[INF] deployment name will be available in \${{ env.DEPLOYMENT_FQN }} with value $FQN"
echo "[INF] OCP API address will be available in \${{ env.API_ADDRESS }} with value $API_ADDRESS"
echo "[INF] OCP API port will be available in \${{ env.API_PORT }} with value $API_PORT"
echo "[INF] OCP node name will be available in \${{ env.NODE_NAME }} with value $NODE_NAME"
echo "[INF] coverage file will ve available in \${{ env.COVERAGE_FILE }} with value $COVERAGE_FILE"

