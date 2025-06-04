import warnings
from krkn_lib.k8s import KrknKubernetes

def __getattr__(name):
    if name in deprecated_modules:
        warnings.warn(
            f"'{name}' is deprecated, use krkn_lib.k8s.KrknKubernetes instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return KrknKubernetes().__getattr__(name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

deprecated_modules = [
    "get_node_by_name",
    "get_node",
    "get_test_pods",
    "wait_for_ready_status",
    "wait_for_not_ready_status",
    "wait_for_unknown_status",
]