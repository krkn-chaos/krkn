import importlib
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


DEFAULT_POLL_INTERVAL = 10
MAX_SCRIPT_OUTPUT_LEN = 4096


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
    if not isinstance(wait_config, dict):
        logging.error(
            f"wait_until: expected a dict, got {type(wait_config).__name__}"
        )
        return False

    condition_type = wait_config.get("type")
    target = wait_config.get("target")
    max_wait_time = wait_config.get("max_wait_time")
    poll_interval = wait_config.get("poll_interval", DEFAULT_POLL_INTERVAL)

    if not condition_type or not target or max_wait_time is None:
        logging.error(
            "wait_until: missing required fields (type, target, max_wait_time)"
        )
        return False

    try:
        max_wait_time = float(max_wait_time)
        poll_interval = float(poll_interval)
    except (TypeError, ValueError):
        logging.error(
            "wait_until: max_wait_time and poll_interval must be numeric"
        )
        return False

    if max_wait_time <= 0 or poll_interval <= 0:
        logging.error(
            "wait_until: max_wait_time and poll_interval must be > 0"
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
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        poll_timeout = min(poll_interval, remaining)

        try:
            if condition_type == "python":
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(check_fn, kubeconfig, scenario)
                    result = future.result(timeout=poll_timeout)
                if result:
                    logging.info(f"wait_until: condition '{target}' met")
                    return True
            else:
                completed = subprocess.run(
                    [target, kubeconfig, scenario],
                    capture_output=True,
                    text=True,
                    timeout=poll_timeout,
                )
                if completed.returncode == 0:
                    logging.info(f"wait_until: script '{target}' returned 0, condition met")
                    return True
                else:
                    if completed.stderr:
                        logging.debug(
                            f"wait_until: script stderr: "
                            f"{completed.stderr[:MAX_SCRIPT_OUTPUT_LEN]}"
                        )
                    if completed.stdout:
                        logging.debug(
                            f"wait_until: script stdout: "
                            f"{completed.stdout[:MAX_SCRIPT_OUTPUT_LEN]}"
                        )
        except FuturesTimeoutError:
            logging.warning(f"wait_until: python condition '{target}' timed out during poll, retrying")
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
