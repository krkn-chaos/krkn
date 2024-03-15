ERRORED=false

function finish {
    if [ $? -eq 1 ] && [ $ERRORED != "true" ]
    then
        error
    fi
}

function error {
    exit_code=$?
    if [ $exit_code == 1 ]
    then
      echo "Error caught."
      ERRORED=true
    else
      echo "Exit code greater than zero detected: $exit_code"
    fi
}

function get_node {
  worker_node=$(kubectl get nodes --no-headers | grep worker | head -n 1)
  export WORKER_NODE=$worker_node
}
