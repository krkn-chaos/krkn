# aichaos
Enhancing Chaos Engineering with AI-assisted fault injection for better resiliency and non-functional testing.


## Installing the dependencies
```
python3.7 -m venv ~/.venv/aichaos37
source ~/.venv/aichaos37/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## RBAC
```
export KUBECONFIG=~/.kube/config.yaml
kubectl apply -f https://litmuschaos.github.io/litmus/litmus-operator-v1.13.8.yaml
kubectl apply -f https://hub.litmuschaos.io/api/chaos/2.9.0?file=charts/generic/experiments.yaml -n robot-shop

cd config

kubectl apply -f rbac.yaml -n robot-shop
kubectl apply -f rbac_cpuhog.yaml -n robot-shop
kubectl apply -f rbac_diskfill.yaml -n robot-shop
kubectl apply -f rbac_network_corruption.yaml -n robot-shop
kubectl apply -f rbac_network_latency.yaml -n robot-shop
kubectl apply -f rbac_network_loss.yaml -n robot-shop
kubectl apply -f rbac_dns_error.yaml -n robot-shop
kubectl apply -f rbac_io_stress.yaml -n robot-shop
```
