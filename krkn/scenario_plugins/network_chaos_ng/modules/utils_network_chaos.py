import subprocess
import logging
from typing import Optional

from krkn_lib.k8s import KrknKubernetes

from krkn.scenario_plugins.network_chaos_ng.modules.utils import (
    log_info,
    log_warning,
    log_error,
)

ROOT_HANDLE = "100:"
CLASS_ID = "100:1"
NETEM_HANDLE = "101:"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Esegue un comando e ritorna CompletedProcess."""
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def tc_node(args: list[str]) -> subprocess.CompletedProcess:
    """Esegue tc nel namespace del nodo (host)."""
    return run(["tc"] + args)


def get_build_tc_tree_commands(devs: list[str]) -> list[str]:
    """Crea la struttura HTB/NETEM nel namespace del pod, se non esiste."""
    tree = []
    for dev in devs:
        tree.append(f"tc qdisc add dev {dev} root handle {ROOT_HANDLE} htb default 1")
        tree.append(
            f"tc class add dev {dev} parent {ROOT_HANDLE} classid {CLASS_ID} htb rate 1gbit",
        )
        tree.append(
            f"tc qdisc add dev {dev} parent {CLASS_ID} handle {NETEM_HANDLE} netem delay 0ms loss 0%",
        )

    return tree


def namespaced_tc_commands(pids: list[str], commands: list[str]) -> list[str]:
    return [
        f"nsenter --target {pid} --net -- {rule}" for pid in pids for rule in commands
    ]


def get_egress_shaping_comand(
    devices: list[str],
    rate_mbit: Optional[str],
    delay_ms: Optional[str],
    loss_pct: Optional[str],
) -> list[str]:
    """Applica rate/delay/loss nel pod."""
    rate_commands = []
    rate = f"{rate_mbit}mbit" if rate_mbit is not None else "1gbit"
    d = delay_ms if delay_ms is not None else 0
    l = loss_pct if loss_pct is not None else 0
    for dev in devices:
        rate_commands.append(
            f"tc class change dev {dev} parent {ROOT_HANDLE} classid {CLASS_ID} htb rate {rate}"
        )
        rate_commands.append(
            f"tc qdisc change dev {dev} parent {CLASS_ID} handle {NETEM_HANDLE} netem delay {d}ms loss {l}%"
        )
    return rate_commands


def get_clear_egress_shaping_commands(devices: list[str]) -> list[str]:
    return [f"tc qdisc del dev {dev} root handle {ROOT_HANDLE}" for dev in devices]


def get_ingress_shaping_commands(
    devs: list[str],
    rate_mbit: Optional[str],
    delay_ms: Optional[str],
    loss_pct: Optional[str],
    ifb_dev: str = "ifb0",
) -> list[str]:

    rate_commands = [
        f"modprobe ifb || true",
        f"ip link add {ifb_dev} type ifb || true",
        f"ip link set {ifb_dev} up || true",
    ]

    for dev in devs:
        rate_commands.append(f"tc qdisc add dev {dev} handle ffff: ingress || true")

        rate_commands.append(
            f"tc filter add dev {dev} parent ffff: protocol all prio 1 "
            f"matchall action mirred egress redirect dev {ifb_dev} || true"
        )

    rate_commands.append(
        f"tc qdisc add dev {ifb_dev} root handle {ROOT_HANDLE} htb default 1 || true"
    )
    rate_commands.append(
        f"tc class add dev {ifb_dev} parent {ROOT_HANDLE} classid {CLASS_ID} "
        f"htb rate {rate_mbit if rate_mbit else '1gbit'}mbit || true"
    )
    rate_commands.append(
        f"tc qdisc add dev {ifb_dev} parent {CLASS_ID} handle {NETEM_HANDLE} "
        f"netem delay {delay_ms if delay_ms else '0'}ms "
        f"loss {loss_pct if loss_pct else '0'}% || true"
    )

    return rate_commands


def get_clear_ingress_shaping_commands(
    devs: list[str],
    ifb_dev: str = "ifb0",
) -> list[str]:

    cmds: list[str] = []
    for dev in devs:
        cmds.append(f"tc qdisc del dev {dev} ingress || true")

    cmds.append(f"tc qdisc del dev {ifb_dev} root handle {ROOT_HANDLE} || true")

    cmds.append(f"ip link set {ifb_dev} down || true")
    cmds.append(f"ip link del {ifb_dev} || true")

    return cmds


def node_qdisc_is_simple(dev: str) -> bool:
    """
    Ritorna True se la qdisc del nodo per dev ha solo la qdisc root di default
    (pfifo_fast, fq_codel, mq...).
    Ritorna False se già contiene htb/netem/clsact o strutture complesse.
    """
    res = tc_node(["qdisc", "show", "dev", dev])
    lines = [l for l in res.stdout.splitlines() if l.strip()]
    if len(lines) != 1:
        return False

    line = lines[0].lower()
    if "htb" in line or "netem" in line or "clsact" in line:
        return False

    return True


def ensure_tree_node(dev: str, force: bool = False) -> list[str]:
    """
    Crea la struttura HTB/NETEM sul nodo.
    Se la qdisc è complessa:
        force=False -> RuntimeError
        force=True  -> warning e procedi comunque
    """
    is_simple = node_qdisc_is_simple(dev)

    if not is_simple and not force:
        raise RuntimeError(
            f"L'interfaccia {dev} ha già una configurazione tc complessa; "
            "usa force=True per sovrascriverla comunque."
        )

    if not is_simple and force:
        logging.warning(
            "FORCE ENABLED: Sostituendo la qdisc root su %s anche se è complessa. "
            "Questo può rompere la rete del nodo!",
            dev,
        )
    return [
        f"tc qdisc replace dev {dev} root handle {ROOT_HANDLE} htb default 1",
        f"tc class add dev {dev} parent {ROOT_HANDLE} classid {CLASS_ID} htb rate 1gbit",
        f"tc qdisc add dev {dev} parent {CLASS_ID} handle {NETEM_HANDLE} netem delay 0ms loss 0%",
    ]


def set_limits_node(
    dev: str,
    rate_mbit: Optional[int],
    delay_ms: Optional[int],
    loss_pct: Optional[float],
    force: bool = False,
):
    """Applica rate/delay/loss sul nodo."""
    ensure_tree_node(dev, force=force)

    rate = f"{rate_mbit}mbit" if rate_mbit is not None else "1gbit"
    tc_node(
        [
            "class",
            "change",
            "dev",
            dev,
            "parent",
            ROOT_HANDLE,
            "classid",
            CLASS_ID,
            "htb",
            "rate",
            rate,
        ]
    )

    d = delay_ms if delay_ms is not None else 0
    l = loss_pct if loss_pct is not None else 0
    tc_node(
        [
            "qdisc",
            "change",
            "dev",
            dev,
            "parent",
            CLASS_ID,
            "handle",
            NETEM_HANDLE,
            "netem",
            "delay",
            f"{d}ms",
            "loss",
            f"{l}%",
        ]
    )


def clear_limits_node(dev: str):
    """Rimuove la nostra qdisc root HTB dal nodo."""
    tc_node(["qdisc", "del", "dev", dev, "root", "handle", ROOT_HANDLE], check=False)


def common_set_limit_rules(
    egress: bool,
    ingress: bool,
    interfaces: list[str],
    bandwidth: str,
    latency: str,
    loss: str,
    parallel: bool,
    target: str,
    kubecli: KrknKubernetes,
    network_chaos_pod_name: str,
    namespace: str,
    pids: Optional[list[str]] = None,
):
    if egress:
        build_tree_commands = get_build_tc_tree_commands(interfaces)
        if pids:
            build_tree_commands = namespaced_tc_commands(pids, build_tree_commands)
        egress_shaping_commands = get_egress_shaping_comand(
            interfaces,
            bandwidth,
            latency,
            loss,
        )
        if pids:
            egress_shaping_commands = namespaced_tc_commands(
                pids, egress_shaping_commands
            )
        error_counter = 0
        for rule in build_tree_commands:
            result = kubecli.exec_cmd_in_pod([rule], network_chaos_pod_name, namespace)
            if not result:
                log_info(f"created tc tree in pod: {rule}", parallel, target)
            else:
                error_counter += 1
        if len(build_tree_commands) == error_counter:
            log_error(
                "failed to apply egress shaping rules on cluster", parallel, target
            )

        for rule in egress_shaping_commands:
            result = kubecli.exec_cmd_in_pod([rule], network_chaos_pod_name, namespace)
            if not result:
                log_info(f"applied egress shaping rules: {rule}", parallel, target)
    if ingress:
        ingress_shaping_commands = get_ingress_shaping_commands(
            interfaces,
            bandwidth,
            latency,
            loss,
        )
        if pids:
            ingress_shaping_commands = namespaced_tc_commands(
                pids, ingress_shaping_commands
            )
        error_counter = 0
        for rule in ingress_shaping_commands:

            result = kubecli.exec_cmd_in_pod([rule], network_chaos_pod_name, namespace)
            if not result:
                log_info(
                    f"applied ingress shaping rule: {rule}",
                    parallel,
                    network_chaos_pod_name,
                )
            else:
                error_counter += 1

        if len(ingress_shaping_commands) == error_counter:
            log_error(
                "failed to apply ingress shaping rules on cluster", parallel, target
            )


def common_delete_limit_rules(
    egress: bool,
    ingress: bool,
    interfaces: list[str],
    network_chaos_pod_name: str,
    network_chaos_namespace: str,
    kubecli: KrknKubernetes,
    pids: Optional[list[str]],
    parallel: bool,
    target: str,
):
    if egress:
        clear_commands = get_clear_egress_shaping_commands(interfaces)
        if pids:
            clear_commands = namespaced_tc_commands(pids, clear_commands)
        error_counter = 0
        for rule in clear_commands:
            result = kubecli.exec_cmd_in_pod(
                [rule], network_chaos_pod_name, network_chaos_namespace
            )
            if not result:
                log_info(f"removed egress shaping rule : {rule}", parallel, target)
            else:
                error_counter += 1
        if len(clear_commands) == error_counter:
            log_error(
                "failed to remove egress shaping rules on cluster", parallel, target
            )

    if ingress:
        clear_commands = get_clear_ingress_shaping_commands(interfaces)
        if pids:
            clear_commands = namespaced_tc_commands(pids, clear_commands)
        error_counter = 0
        for rule in clear_commands:
            result = kubecli.exec_cmd_in_pod(
                [rule], network_chaos_pod_name, network_chaos_namespace
            )
            if not result:
                log_info(f"removed ingress shaping rule: {rule}", parallel, target)
            else:
                error_counter += 1
        if len(clear_commands) == error_counter:
            log_error(
                "failed to remove ingress shaping rules on cluster", parallel, target
            )
