function functional_pod_network_filter {
  export SERVICE_URL="http://localhost:8889"
  export scenario_type="network_chaos_ng_scenarios"
  export scenario_file="scenarios/kube/pod-network-filter.yml"
  export post_config=""
  envsubst < CI/config/common_test_config.yaml > CI/config/pod_network_filter.yaml
  yq -i '.[0].test_duration=10' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].label_selector=""' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].ingress=false' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].egress=true' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].target="pod-network-filter-test"' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].protocols=["tcp"]' scenarios/kube/pod-network-filter.yml
  yq -i '.[0].ports=[443]' scenarios/kube/pod-network-filter.yml

  ## Test webservice deployment
  kubectl apply -f ./CI/templates/pod_network_filter.yaml
  COUNTER=0
  while true
   do
    curl $SERVICE_URL
    EXITSTATUS=$?
    if [ "$EXITSTATUS" -eq "0" ]
      then
        break
    fi
    sleep 1
    COUNTER=$((COUNTER+1))
    [ $COUNTER -eq "100" ] && echo "maximum number of retry reached, test failed" && exit 1
  done

  cat scenarios/kube/pod-network-filter.yml

  python3 -m coverage run -a run_kraken.py -c CI/config/pod_network_filter.yaml > krkn_pod_network.out 2>&1 &
  PID=$!

  # wait until the dns resolution starts failing and the service returns 400
  DNS_FAILURE_STATUS=0
  while true
   do
    OUT_STATUS_CODE=$(curl -X GET -s -o /dev/null -I -w "%{http_code}" $SERVICE_URL)
    if [ "$OUT_STATUS_CODE" -eq "404" ]
      then
        DNS_FAILURE_STATUS=404
    fi

    if [ "$DNS_FAILURE_STATUS" -eq "404" ] && [ "$OUT_STATUS_CODE" -eq "200" ]
      then
        echo "service restored"
        break
    fi
    COUNTER=$((COUNTER+1))
    [ $COUNTER -eq "100" ] && echo "maximum number of retry reached, test failed" && exit 1
    sleep 2
  done

  wait $PID

}

functional_pod_network_filter

