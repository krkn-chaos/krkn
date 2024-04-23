ERRORED=false

function finish {
    if [ $? != 0 ] && [ $ERRORED != "true" ]
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
    elif [ $exit_code == 2 ]
    then
      echo "Run with exit code 2 detected, it is expected, wrapping the exit code with 0 to avoid pipeline failure"
      exit 0
    fi
}

function get_node {
  worker_node=$(kubectl get nodes --no-headers | grep worker | head -n 1)
  export WORKER_NODE=$worker_node
}
