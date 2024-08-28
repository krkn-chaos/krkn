set -xeEo pipefail

source CI/tests/common.sh

trap error ERR
trap finish EXIT
# port mapping has been configured in kind-config.yml
SERVICE_URL=http://localhost:8888
PAYLOAD_GET_1="{ \
  \"status\":\"internal server error\" \
}"
STATUS_CODE_GET_1=500

PAYLOAD_PATCH_1="resource patched"
STATUS_CODE_PATCH_1=201

PAYLOAD_POST_1="{ \
  \"status\": \"unauthorized\" \
}"
STATUS_CODE_POST_1=401

PAYLOAD_GET_2="{ \
  \"status\":\"resource created\" \
}"
STATUS_CODE_GET_2=201

PAYLOAD_PATCH_2="bad request"
STATUS_CODE_PATCH_2=400

PAYLOAD_POST_2="not found"
STATUS_CODE_POST_2=404

JSON_MIME="application/json"
TEXT_MIME="text/plain; charset=utf-8"

function functional_test_service_hijacking {

  export scenario_type="service_hijacking"
  export scenario_file="scenarios/kube/service_hijacking.yaml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/service_hijacking.yaml
  python3 -m coverage run -a run_kraken.py -c CI/config/service_hijacking.yaml  > /dev/null 2>&1 &
  PID=$!
  #Waiting the hijacking to have effect
  COUNTER=0
  while [ `curl -X GET -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/list/index.php` == 404 ]
   do
    echo "waiting scenario to kick in."
    sleep 1
    COUNTER=$((COUNTER+1))
    [ $COUNTER -eq "100" ] && echo "maximum number of retry reached, test failed" && exit 1
  done

  #Checking Step 1 GET on /list/index.php
  OUT_GET="`curl -X GET -s $SERVICE_URL/list/index.php`"
  OUT_CONTENT=`curl -X GET -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/list/index.php`
  OUT_STATUS_CODE=`curl -X GET -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/list/index.php`
  [ "${PAYLOAD_GET_1//[$'\t\r\n ']}" == "${OUT_GET//[$'\t\r\n ']}" ] && echo "Step 1 GET Payload OK" || (echo "Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_GET_1" ] && echo "Step 1 GET Status Code OK" || (echo " Step 1 GET status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$JSON_MIME" ] && echo "Step 1 GET MIME OK" || (echo " Step 1 GET MIME did not match. Test failed." && exit 1)

  #Checking Step 1 POST on /list/index.php
  OUT_POST="`curl -s -X POST $SERVICE_URL/list/index.php`"
  OUT_STATUS_CODE=`curl -X POST -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/list/index.php`
  OUT_CONTENT=`curl -X POST -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/list/index.php`
  [ "${PAYLOAD_POST_1//[$'\t\r\n ']}" == "${OUT_POST//[$'\t\r\n ']}" ] && echo "Step 1 POST Payload OK" || (echo "Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_POST_1" ] && echo "Step 1 POST Status Code OK" || (echo "Step 1 POST status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$JSON_MIME" ] && echo "Step 1 POST MIME OK" || (echo " Step 1 POST MIME did not match. Test failed." && exit 1)

  #Checking Step 1 PATCH on /patch
  OUT_PATCH="`curl -s -X PATCH $SERVICE_URL/patch`"
  OUT_STATUS_CODE=`curl -X PATCH -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/patch`
  OUT_CONTENT=`curl -X PATCH -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/patch`
  [ "${PAYLOAD_PATCH_1//[$'\t\r\n ']}" == "${OUT_PATCH//[$'\t\r\n ']}" ] && echo "Step 1 PATCH Payload OK" || (echo "Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_PATCH_1" ] && echo "Step 1 PATCH Status Code OK" || (echo "Step 1 PATCH status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$TEXT_MIME" ] && echo "Step 1 PATCH MIME OK" || (echo " Step 1 PATCH MIME did not match. Test failed." && exit 1)
  # wait for the next step
  sleep 16

  #Checking Step 2 GET on /list/index.php
  OUT_GET="`curl -X GET -s $SERVICE_URL/list/index.php`"
  OUT_CONTENT=`curl -X GET -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/list/index.php`
  OUT_STATUS_CODE=`curl -X GET -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/list/index.php`
  [ "${PAYLOAD_GET_2//[$'\t\r\n ']}" == "${OUT_GET//[$'\t\r\n ']}" ] && echo "Step 2 GET Payload OK" || (echo "Step 2 GET Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_GET_2" ] && echo "Step 2 GET Status Code OK" || (echo "Step 2 GET status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$JSON_MIME" ] && echo "Step 2 GET MIME OK" || (echo " Step 2 GET MIME did not match. Test failed." && exit 1)

  #Checking Step 2 POST on /list/index.php
  OUT_POST="`curl -s -X POST $SERVICE_URL/list/index.php`"
  OUT_CONTENT=`curl -X POST -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/list/index.php`
  OUT_STATUS_CODE=`curl -X POST -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/list/index.php`
  [ "${PAYLOAD_POST_2//[$'\t\r\n ']}" == "${OUT_POST//[$'\t\r\n ']}" ] && echo "Step 2 POST Payload OK" || (echo "Step 2 POST Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_POST_2" ] && echo "Step 2 POST Status Code OK" || (echo "Step 2 POST status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$TEXT_MIME" ] && echo "Step 2 POST MIME OK" || (echo " Step 2 POST MIME did not match. Test failed." && exit 1)

  #Checking Step 2 PATCH on /patch
  OUT_PATCH="`curl -s -X PATCH $SERVICE_URL/patch`"
  OUT_CONTENT=`curl -X PATCH -s -o /dev/null -I -w "%{content_type}" $SERVICE_URL/patch`
  OUT_STATUS_CODE=`curl -X PATCH -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL/patch`
  [ "${PAYLOAD_PATCH_2//[$'\t\r\n ']}" == "${OUT_PATCH//[$'\t\r\n ']}" ] && echo "Step 2 PATCH Payload OK" || (echo "Step 2 PATCH Payload did not match. Test failed." && exit 1)
  [ "$OUT_STATUS_CODE" == "$STATUS_CODE_PATCH_2" ] && echo "Step 2 PATCH Status Code OK" || (echo "Step 2 PATCH status code did not match. Test failed." && exit 1)
  [ "$OUT_CONTENT" == "$TEXT_MIME" ] && echo "Step 2 PATCH MIME OK" || (echo " Step 2 PATCH MIME did not match. Test failed." && exit 1)
  wait $PID

  # now checking  if service has been restore correctly and nginx responds correctly
  curl -s  $SERVICE_URL | grep nginx! && echo "BODY: Service restored!" || (echo "BODY: failed to restore service" && exit 1)
  OUT_STATUS_CODE=`curl -X GET -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL`
  [ "$OUT_STATUS_CODE" == "200" ] && echo "STATUS_CODE: Service restored!" || (echo "STATUS_CODE: failed to restore service" && exit 1)

  echo "Service Hijacking Chaos test: Success"
}


functional_test_service_hijacking
