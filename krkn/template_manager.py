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

import argparse
import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


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
        self.templates_dir = self._find_templates_directory()
        self._load_filesystem_templates()
    
    def _find_templates_directory(self) -> Optional[Path]:
        """
        Find the templates directory.
        
        ✅ FIX ISSUE #4: Locate templates/chaos-scenarios directory
        """
        # Try relative to current file
        current_file = Path(__file__).resolve()
        
        # Check ../templates/chaos-scenarios from krkn module
        templates_dir = current_file.parent.parent / "templates" / "chaos-scenarios"
        if templates_dir.exists():
            return templates_dir
        
        # Check ./templates/chaos-scenarios from current directory
        templates_dir = Path.cwd() / "templates" / "chaos-scenarios"
        if templates_dir.exists():
            return templates_dir
        
        logging.warning("Templates directory not found")
        return None
    
    def _load_filesystem_templates(self):
        """
        Load templates from filesystem.
        
        ✅ FIX ISSUE #4: Load all templates from templates/chaos-scenarios/
        """
        if not self.templates_dir:
            logging.warning("No templates directory found, skipping filesystem templates")
            return
        
        logging.info(f"Loading templates from: {self.templates_dir}")
        
        # Iterate through template directories
        for template_dir in self.templates_dir.iterdir():
            if not template_dir.is_dir():
                continue
            
            metadata_file = template_dir / "metadata.yaml"
            scenario_file = template_dir / "scenario.yaml"
            
            if not metadata_file.exists() or not scenario_file.exists():
                logging.warning(f"Skipping {template_dir.name}: missing metadata.yaml or scenario.yaml")
                continue
            
            try:
                # Load metadata
                with open(metadata_file, 'r') as f:
                    metadata = yaml.safe_load(f)
                
                # Load scenario
                with open(scenario_file, 'r') as f:
                    scenario_list = yaml.safe_load(f)
                
                # Extract scenario config (first item in list, under 'config' key)
                if not scenario_list or not isinstance(scenario_list, list):
                    logging.warning(f"Skipping {template_dir.name}: invalid scenario format")
                    continue
                
                scenario_item = scenario_list[0]
                scenario_config = scenario_item.get('config', {})
                scenario_id = scenario_item.get('id', template_dir.name)
                
                # Determine scenario type from directory structure or metadata
                scenario_type = self._infer_scenario_type(metadata, scenario_config)
                
                # Build parameters from metadata
                parameters = {}
                for param in metadata.get('parameters', []):
                    param_name = param['name']
                    parameters[param_name] = TemplateParameter(
                        name=param_name,
                        description=param.get('description', ''),
                        required=param.get('required', False),
                        default=param.get('default'),
                        type=param.get('type', 'string')
                    )
                
                # Create template
                template = ChaosTemplate(
                    name=metadata['name'],
                    description=metadata.get('description', ''),
                    scenario_type=scenario_type,
                    scenario_config=scenario_config,
                    parameters=parameters
                )
                
                self.templates[template.name] = template
                logging.info(f"Loaded template: {template.name}")
                
            except Exception as e:
                logging.error(f"Failed to load template from {template_dir.name}: {e}")
                continue
    
    def _infer_scenario_type(self, metadata: Dict, scenario_config: Dict) -> str:
        """
        Infer the scenario type from metadata or config.
        
        Maps template categories to KRKN scenario types.
        """
        category = metadata.get('category', '').lower()
        target = metadata.get('target', '').lower()
        
        # Map categories to scenario types
        if 'pod' in target or 'pod' in category:
            return 'pod_disruption_scenarios'
        elif 'node' in target or 'node' in category:
            return 'node_scenarios'
        elif 'network' in target or 'network' in category:
            return 'network_chaos_scenarios'
        elif 'container' in target or 'container' in category:
            return 'container_scenarios'
        elif 'vm' in target or 'kubevirt' in target:
            return 'kubevirt_scenarios'
        elif 'cpu' in category or 'memory' in category or 'disk' in category:
            return 'hog_scenarios'
        else:
            # Default fallback
            return 'plugin_scenarios'
    
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
        
        ✅ FIX ISSUE #1: Creates proper scenario YAML with 'config' key
        ✅ FIX ISSUE #3: Clears existing chaos_scenarios to run only template
        
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
        
        # ✅ FIX ISSUE #3: Clear existing chaos_scenarios to run ONLY this template
        config['kraken']['chaos_scenarios'] = []
        
        # Create scenario data from template with proper structure
        scenario_config = template.to_scenario_dict(params)
        
        # ✅ FIX ISSUE #2: Wrap in proper YAML structure with 'config' key
        scenario_data = [{
            'id': template.name,
            'config': scenario_config
        }]
        
        # Write scenario to temp file
        scenario_fd, scenario_path = tempfile.mkstemp(
            suffix='.yaml', 
            prefix=f'krkn_scenario_{template_name}_'
        )
        try:
            with os.fdopen(scenario_fd, 'w') as f:
                yaml.dump(scenario_data, f)
        except Exception as e:
            logging.error(f"Failed to write scenario file: {e}")
            try:
                os.unlink(scenario_path)
            except:
                pass
            return None
        
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
    
    ✅ FIX ISSUE #5: Uses logging instead of print()
    ✅ FIX ISSUE #6: Returns proper exit code with logging
    """
    try:
        template_manager = TemplateManager()
        templates = template_manager.list_templates()
        
        if not templates:
            logging.info("No templates available.")
            return 0
        
        logging.info("\n📋 Available Chaos Templates:\n")
        for template in templates:
            logging.info(f"  • {template.name}")
            logging.info(f"    {template.description}")
            logging.info("")
        
        return 0
    except Exception as e:
        logging.error(f"Error listing templates: {e}")
        return 1


def show_template_command(args) -> int:
    """
    Show details of a specific template.
    
    ✅ FIX ISSUE #5: Uses logging instead of print()
    ✅ FIX ISSUE #6: Returns proper exit code with logging
    """
    try:
        template_manager = TemplateManager()
        template = template_manager.get_template(args.template)
        
        if not template:
            logging.error(f"Template '{args.template}' not found.")
            return 1
        
        logging.info(f"\n📄 Template: {template.name}\n")
        logging.info(f"Description: {template.description}")
        logging.info(f"Type: {template.scenario_type}")
        
        if template.parameters:
            logging.info("\nParameters:")
            for param_name, param_info in template.parameters.items():
                required = "required" if param_info.required else "optional"
                default = f" (default: {param_info.default})" if param_info.default is not None else ""
                logging.info(f"  • {param_name} ({required}){default}")
                logging.info(f"    {param_info.description}")
        
        logging.info("")
        return 0
    except Exception as e:
        logging.error(f"Error showing template: {e}")
        return 1


def run_template_command(args) -> int:
    """
    Execute a template with the given parameters.
    
    ✅ FIX ISSUE #1: Uses prepare_template_config with proper YAML format
    ✅ FIX ISSUE #4: Returns standardized exit code (0 or 1)
    ✅ FIX ISSUE #5: Uses logging instead of print()
    ✅ FIX ISSUE #6: Logs exit code
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
        logging.error(f"Failed to prepare template '{args.template}'.")
        return 1
    
    logging.info(f"🚀 Running template '{args.template}'...")
    logging.info(f"Configuration: {config_path}")
    
    if params:
        logging.info("Parameters:")
        for key, value in params.items():
            logging.info(f"   {key}: {value}")
    
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
        
        # ✅ FIX ISSUE #4: Standardize exit code to 0 (success) or 1 (failure)
        exit_code = 0 if retval == 0 else 1
        
        # ✅ FIX ISSUE #6: Log exit code
        if exit_code == 0:
            logging.info(f"✅ Template '{args.template}' completed successfully (exit code: {exit_code})")
        else:
            logging.error(f"❌ Template '{args.template}' failed (exit code: {exit_code})")
        
        return exit_code
        
    except Exception as e:
        logging.error(f"Error running template: {e}")
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
