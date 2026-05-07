#!/usr/bin/env python
# Copyright 2025 The Krkn Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
KRKN Chaos Template Manager

Provides pre-configured chaos scenario templates for easy execution.
"""

import sys
import os
import json
import yaml
import logging
import argparse
import tempfile
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class TemplateParameter:
    """Represents a template parameter"""
    name: str
    description: str
    required: bool = False
    default: Any = None
    type: str = "string"


@dataclass
class ChaosTemplate:
    """Represents a chaos scenario template"""
    name: str
    description: str
    scenario_type: str
    scenario_config: Dict[str, Any]
    parameters: Dict[str, TemplateParameter] = field(default_factory=dict)
    
    def to_scenario_dict(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert template to scenario dict with parameters applied.
        
        Args:
            params: Parameter values to inject
            
        Returns:
            Scenario configuration dict
        """
        # Deep copy the scenario config
        scenario = json.loads(json.dumps(self.scenario_config))
        
        # Apply parameters
        for param_name, param_value in params.items():
            if param_name in self.parameters:
                # Replace parameter placeholders in the scenario
                scenario = self._replace_param(scenario, param_name, param_value)
        
        # Apply default values for missing required parameters
        for param_name, param_def in self.parameters.items():
            if param_name not in params and param_def.default is not None:
                scenario = self._replace_param(scenario, param_name, param_def.default)
        
        return scenario
    
    def _replace_param(self, obj: Any, param_name: str, value: Any) -> Any:
        """Recursively replace parameter placeholders"""
        if isinstance(obj, dict):
            return {k: self._replace_param(v, param_name, value) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_param(item, param_name, value) for item in obj]
        elif isinstance(obj, str):
            placeholder = f"${{{param_name}}}"
            if placeholder in obj:
                return obj.replace(placeholder, str(value))
        return obj


class TemplateManager:
    """Manages chaos scenario templates"""
    
    def __init__(self):
        self.templates: Dict[str, ChaosTemplate] = {}
        self._load_builtin_templates()
    
    def _load_builtin_templates(self):
        """Load built-in templates"""
        # Pod network outage template
        self.templates['pod-network-outage'] = ChaosTemplate(
            name='pod-network-outage',
            description='Simulate network outage for pods in a namespace',
            scenario_type='pod_network_scenarios',
            scenario_config={
                'id': 'pod_network_outage',
                'namespace': '${namespace}',
                'label_selector': '${label_selector}',
                'duration': '${duration}',
                'instance_count': 1
            },
            parameters={
                'namespace': TemplateParameter(
                    name='namespace',
                    description='Target namespace',
                    required=True,
                    type='string'
                ),
                'label_selector': TemplateParameter(
                    name='label_selector',
                    description='Pod label selector',
                    required=False,
                    default='',
                    type='string'
                ),
                'duration': TemplateParameter(
                    name='duration',
                    description='Outage duration in seconds',
                    required=False,
                    default=60,
                    type='int'
                )
            }
        )
        
        # Pod kill template
        self.templates['pod-kill'] = ChaosTemplate(
            name='pod-kill',
            description='Kill pods matching label selector',
            scenario_type='pod_disruption_scenarios',
            scenario_config={
                'id': 'pod_kill',
                'namespace': '${namespace}',
                'label_selector': '${label_selector}',
                'kill_count': '${kill_count}'
            },
            parameters={
                'namespace': TemplateParameter(
                    name='namespace',
                    description='Target namespace',
                    required=True,
                    type='string'
                ),
                'label_selector': TemplateParameter(
                    name='label_selector',
                    description='Pod label selector',
                    required=True,
                    type='string'
                ),
                'kill_count': TemplateParameter(
                    name='kill_count',
                    description='Number of pods to kill',
                    required=False,
                    default=1,
                    type='int'
                )
            }
        )
    
    def list_templates(self) -> List[ChaosTemplate]:
        """List all available templates"""
        return list(self.templates.values())
    
    def get_template(self, name: str) -> Optional[ChaosTemplate]:
        """Get a template by name"""
        return self.templates.get(name)
    
    def prepare_template_config(
        self, 
        template_name: str, 
        params: Dict[str, Any],
        base_config_path: str = None
    ) -> Optional[str]:
        """
        Prepare a complete KRKN configuration file for template execution.
        
        ✅ FIX ISSUE #1: Creates full config with kraken:, tunings:, etc.
        
        Args:
            template_name: Name of the template to prepare
            params: Parameters to inject into the template
            base_config_path: Path to base config (defaults to config/config.yaml)
        
        Returns:
            Path to the prepared config file, or None on failure
        """
        # Get template
        template = self.get_template(template_name)
        if not template:
            logging.error(f"Template '{template_name}' not found")
            return None
        
        # Load base config
        if not base_config_path:
            base_config_path = "config/config.yaml"
        
        try:
            with open(base_config_path, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logging.error(f"Failed to load base config from {base_config_path}: {e}")
            return None
        
        # Ensure required top-level keys exist
        if 'kraken' not in config:
            config['kraken'] = {}
        if 'tunings' not in config:
            config['tunings'] = {'wait_duration': 60, 'iterations': 1, 'daemon_mode': False}
        if 'performance_monitoring' not in config:
            config['performance_monitoring'] = {}
        
        # Create scenario file from template
        scenario_data = template.to_scenario_dict(params)
        
        # Write scenario to temp file
        scenario_fd, scenario_path = tempfile.mkstemp(
            suffix='.yaml', 
            prefix=f'krkn_scenario_{template_name}_'
        )
        try:
            with os.fdopen(scenario_fd, 'w') as f:
                yaml.dump([scenario_data], f)
        except Exception as e:
            logging.error(f"Failed to write scenario file: {e}")
            try:
                os.unlink(scenario_path)
            except:
                pass
            return None
        
        # Inject scenario path into config
        if 'chaos_scenarios' not in config['kraken']:
            config['kraken']['chaos_scenarios'] = []
        
        # Add the scenario reference
        config['kraken']['chaos_scenarios'].append({
            template.scenario_type: [scenario_path]
        })
        
        # Write complete config to temp file
        config_fd, config_path = tempfile.mkstemp(
            suffix='.yaml', 
            prefix=f'krkn_config_{template_name}_'
        )
        try:
            with os.fdopen(config_fd, 'w') as f:
                yaml.dump(config, f)
            logging.info(f"Prepared config at: {config_path}")
            logging.info(f"Scenario file at: {scenario_path}")
            return config_path
        except Exception as e:
            logging.error(f"Failed to write config file: {e}")
            try:
                os.unlink(config_path)
                os.unlink(scenario_path)
            except:
                pass
            return None


def list_templates_command(args) -> int:
    """
    List all available templates.
    
    ✅ FIX ISSUE #3: Returns proper exit code
    """
    try:
        template_manager = TemplateManager()
        templates = template_manager.list_templates()
        
        if not templates:
            print("No templates available.")
            return 0
        
        print("\n📋 Available Chaos Templates:\n")
        for template in templates:
            print(f"  • {template.name}")
            print(f"    {template.description}")
            print()
        
        return 0
    except Exception as e:
        print(f"❌ Error listing templates: {e}", file=sys.stderr)
        return 1


def show_template_command(args) -> int:
    """
    Show details of a specific template.
    
    ✅ FIX ISSUE #3: Returns proper exit code
    """
    try:
        template_manager = TemplateManager()
        template = template_manager.get_template(args.template)
        
        if not template:
            print(f"❌ Template '{args.template}' not found.", file=sys.stderr)
            return 1
        
        print(f"\n📄 Template: {template.name}\n")
        print(f"Description: {template.description}")
        print(f"Type: {template.scenario_type}")
        
        if template.parameters:
            print("\nParameters:")
            for param_name, param_info in template.parameters.items():
                required = "required" if param_info.required else "optional"
                default = f" (default: {param_info.default})" if param_info.default is not None else ""
                print(f"  • {param_name} ({required}){default}")
                print(f"    {param_info.description}")
        
        print()
        return 0
    except Exception as e:
        print(f"❌ Error showing template: {e}", file=sys.stderr)
        return 1


def run_template_command(args) -> int:
    """
    Execute a template with the given parameters.
    
    ✅ FIX ISSUE #1: Uses prepare_template_config with full config
    ✅ FIX ISSUE #3: Returns proper exit code
    """
    template_manager = TemplateManager()
    
    # Parse parameters if provided
    params = {}
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            # Try key=value format
            for param in args.params.split(','):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key.strip()] = value.strip()
    
    # Prepare template configuration with base config
    base_config = getattr(args, 'base_config', None) or 'config/config.yaml'
    config_path = template_manager.prepare_template_config(
        args.template, 
        params,
        base_config_path=base_config
    )
    
    if not config_path:
        print(f"❌ Failed to prepare template '{args.template}'.")
        return 1
    
    print(f"🚀 Running template '{args.template}'...")
    print(f"Configuration: {config_path}")
    
    if params:
        print("Parameters:")
        for key, value in params.items():
            print(f"   {key}: {value}")
    
    # Import and run kraken with the prepared config
    try:
        from optparse import Values
        
        # Create options object for kraken
        options = Values({
            'cfg': config_path,
            'output': args.output or f"krkn-{args.template}.report",
            'debug': args.debug,
            'junit_testcase': None,
            'junit_testcase_path': None,
            'junit_testcase_version': None,
            'run_uuid': None,
            'scenario_type': None,
        })
        
        # Import and run main kraken function
        from run_kraken import main as kraken_main
        retval = kraken_main(options, None)
        
        # Cleanup temp files
        try:
            os.unlink(config_path)
        except:
            pass
        
        return retval
        
    except Exception as e:
        print(f"❌ Error running template: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    """
    Main entry point for template CLI.
    
    ✅ FIX ISSUE #3: Returns exit code instead of None
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description='KRKN Chaos Template Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  krkn-template list
  krkn-template show pod-network-outage
  krkn-template run pod-network-outage --params '{"namespace":"default"}'
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available templates')
    list_parser.set_defaults(func=list_templates_command)
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show template details')
    show_parser.add_argument('template', help='Name of the template')
    show_parser.set_defaults(func=show_template_command)
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run a template')
    run_parser.add_argument('template', help='Name of the template to run')
    run_parser.add_argument('--params', help='Template parameters (JSON or key=value pairs)')
    run_parser.add_argument(
        '--base-config', 
        default='config/config.yaml',
        help='Base KRKN config file (default: config/config.yaml)'
    )
    run_parser.add_argument('--output', help='Output report location')
    run_parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    run_parser.set_defaults(func=run_template_command)
    
    args = parser.parse_args()
    
    # ✅ FIX ISSUE #3: Handle missing command
    if not args.command:
        parser.print_help()
        return 1
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    # ✅ FIX ISSUE #3: Execute command and return exit code
    try:
        result = args.func(args)
        return result if result is not None else 0
    except Exception as e:
        logging.error(f"Error executing command '{args.command}': {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    # ✅ FIX ISSUE #3: Propagate exit code
    sys.exit(main())
