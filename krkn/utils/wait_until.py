import importlib
import logging
import subprocess
import time


DEFAULT_POLL_INTERVAL = 10


def wait_until_condition(
    wait_config: dict,
    kubeconfig: str,
    scenario: str,
) -> bool:
    """
    Polls a user-provided condition (Python function or shell script)
    until it succeeds or max_wait_time is reached.

    :param wait_config: dict with keys: type, target, max_wait_time, poll_interval
    :param kubeconfig: path to the kubeconfig file
    :param scenario: path to the scenario config file
    :return: True if condition was met, False if timed out
    """
    condition_type = wait_config.get("type")
    target = wait_config.get("target")
    max_wait_time = wait_config.get("max_wait_time")
    poll_interval = wait_config.get("poll_interval", DEFAULT_POLL_INTERVAL)

    if not condition_type or not target or max_wait_time is None:
        logging.error(
            "wait_until: missing required fields (type, target, max_wait_time)"
        )
        return False

    if condition_type == "python":
        check_fn = _load_python_condition(target)
        if check_fn is None:
            return False
    elif condition_type == "script":
        check_fn = None
    else:
        logging.error(f"wait_until: unknown type '{condition_type}', expected 'python' or 'script'")
        return False

    logging.info(
        f"wait_until: polling {condition_type} condition '{target}' "
        f"every {poll_interval}s (max {max_wait_time}s)"
    )

    deadline = time.time() + max_wait_time
    while time.time() < deadline:
        try:
            if condition_type == "python":
                result = check_fn(kubeconfig, scenario)
                if result:
                    logging.info(f"wait_until: condition '{target}' met")
                    return True
            else:
                completed = subprocess.run(
                    [target, kubeconfig, scenario],
                    capture_output=True,
                    text=True,
                    timeout=poll_interval,
                )
                if completed.returncode == 0:
                    logging.info(f"wait_until: script '{target}' returned 0, condition met")
                    return True
        except subprocess.TimeoutExpired:
            logging.warning(f"wait_until: script '{target}' timed out during poll, retrying")
        except Exception as e:
            logging.warning(f"wait_until: condition check raised {type(e).__name__}: {e}")

        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))

    logging.warning(
        f"wait_until: condition '{target}' not met within {max_wait_time}s, continuing"
    )
    return False


def _load_python_condition(target: str):
    """
    Import a Python function from a 'module.submodule.function' path.
    Returns the callable or None on failure.
    """
    parts = target.rsplit(".", 1)
    if len(parts) != 2:
        logging.error(
            f"wait_until: invalid python target '{target}', "
            f"expected 'module.function' format"
        )
        return None

    module_path, func_name = parts
    try:
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        if not callable(func):
            logging.error(f"wait_until: '{target}' is not callable")
            return None
        return func
    except (ImportError, AttributeError) as e:
        logging.error(f"wait_until: failed to load '{target}': {e}")
        return None
