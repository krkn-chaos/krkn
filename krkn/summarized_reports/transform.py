"""
Transform Krkn chaos run JSON into different report formats.
"""

import json
from typing import Dict, Any


def get_executive_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract executive summary from chaos run JSON.

    Args:
        data: The parsed JSON from chaos_output.to_json()

    Returns:
        Dict with cluster info, test period, pass rate, resiliency score
    """
    telemetry = data.get('telemetry', {})

    # Count total and passed scenarios
    scenarios = telemetry.get('scenarios', [])
    total_scenarios = len(scenarios)
    passed_scenarios = sum(1 for s in scenarios if s.get('exit_status') == 0)
    failed_scenarios = total_scenarios - passed_scenarios

    # Calculate pass rate
    pass_rate = (passed_scenarios / total_scenarios * 100) if total_scenarios > 0 else 0

    return {
        'cluster_version': telemetry.get('cluster_version', 'Unknown'),
        'cloud_infrastructure': telemetry.get('cloud_infrastructure', 'Unknown'),
        'cloud_type': telemetry.get('cloud_type', 'Unknown'),
        'total_nodes': telemetry.get('total_node_count', 0),
        'run_uuid': telemetry.get('run_uuid', ''),
        'timestamp': telemetry.get('timestamp', ''),
        'total_scenarios': total_scenarios,
        'passed_scenarios': passed_scenarios,
        'failed_scenarios': failed_scenarios,
        'pass_rate': round(pass_rate, 2),
        'overall_status': 'PASSED' if telemetry.get('job_status', False) else 'FAILED',
    }


# Test it
if __name__ == '__main__':
    # Example: Load a JSON file and extract summary
    import sys

    if len(sys.argv) > 1:
        json_file = sys.argv[1]
        with open(json_file, 'r') as f:
            data = json.load(f)

        summary = get_executive_summary(data)
        print("Executive Summary:")
        print(json.dumps(summary, indent=2))
    else:
        print("Usage: python transform.py <chaos_output.json>")
