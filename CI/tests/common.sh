ERRORED=false

function finish {
    if [ $? -eq 1 ] && [ $ERRORED != "true" ]
    then
        error
    fi
}

function error {
    echo "Error caught."
    ERRORED=true
}

function get_node {
  worker_node=$(oc get nodes --no-headers | grep worker | head -n 1)
  export WORKER_NODE=$worker_node
}
