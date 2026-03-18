#!/usr/bin/env python
#
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
KRKN Template Manager Module

This module provides functionality to manage and run chaos scenario templates
for the KRKN chaos engineering tool.
"""

# Standard library imports
import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third-party imports
import yaml

# Local imports
from optparse import Values


class TemplateManager:
    """
    Manages KRKN chaos scenario templates including listing, running,
    and customizing predefined scenarios.
    """
    
    def __init__(self, templates_dir: str = "templates/chaos-scenarios"):
        """
        Initialize the Template Manager.
        
        Args:
            templates_dir: Path to the templates directory
        """
        # Use absolute path relative to package location
        if not Path(templates_dir).is_absolute():
            package_root = Path(__file__).parent.parent
            self.templates_dir = package_root / templates_dir
        else:
            self.templates_dir = Path(templates_dir)
        self.logger = logging.getLogger(__name__)
        
    def list_templates(self) -> Dict[str, Dict[str, Any]]:
        """
        List all available chaos scenario templates.
        
        Returns:
            Dictionary of template names and their metadata
        """
        templates = {}
        
        if not self.templates_dir.exists():
            self.logger.warning(f"Templates directory {self.templates_dir} not found")
            return templates
            
        for template_dir in self.templates_dir.iterdir():
            if template_dir.is_dir():
                template_name = template_dir.name
                metadata_file = template_dir / "metadata.yaml"
                
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = yaml.safe_load(f)
                        templates[template_name] = metadata
                    except Exception as e:
                        self.logger.error(f"Error reading metadata for {template_name}: {e}")
                        continue
                else:
                    self.logger.warning(f"No metadata.yaml found for template {template_name}")
                    
        return templates
    
    def get_template_details(self, template_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific template.
        
        Args:
            template_name: Name of the template
            
        Returns:
            Dictionary containing template details or None if not found
        """
        template_dir = self.templates_dir / template_name
        
        if not template_dir.exists():
            self.logger.error(f"Template {template_name} not found")
            return None
            
        details = {}
        
        # Read metadata
        metadata_file = template_dir / "metadata.yaml"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                details['metadata'] = yaml.safe_load(f)
        
        # Read scenario configuration
        scenario_file = template_dir / "scenario.yaml"
        if scenario_file.exists():
            with open(scenario_file, 'r') as f:
                details['scenario'] = yaml.safe_load(f)
        
        # Read README
        readme_file = template_dir / "README.md"
        if readme_file.exists():
            with open(readme_file, 'r') as f:
                details['readme'] = f.read()
                
        return details
    
    def prepare_template_config(self, template_name: str, 
                               params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Prepare a template configuration with custom parameters.
        
        Args:
            template_name: Name of the template
            params: Dictionary of parameter overrides
            
        Returns:
            Path to the prepared configuration file or None if failed
        """
        template_dir = self.templates_dir / template_name
        
        if not template_dir.exists():
            self.logger.error(f"Template {template_name} not found")
            return None
            
        scenario_file = template_dir / "scenario.yaml"
        if not scenario_file.exists():
            self.logger.error(f"No scenario.yaml found for template {template_name}")
            return None
            
        try:
            # Load the base scenario configuration
            with open(scenario_file, 'r') as f:
                scenario_config = yaml.safe_load(f)
            
            if not scenario_config:
                self.logger.error(f"Empty scenario configuration for template {template_name}")
                return None
            
            # Apply parameter overrides if provided
            if params:
                scenario_config = self._apply_parameters(scenario_config, params)
            
            # Wrap the scenario into a proper KRKN configuration structure
            krkn_config = self._create_krkn_config(scenario_config)
            
            # Create a temporary config file
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'-{template_name}.yaml', delete=False) as f:
                temp_config_path = f.name
                yaml.dump(krkn_config, f, default_flow_style=False)
            
            self.logger.info(f"Prepared template config: {temp_config_path}")
            return temp_config_path
            
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML for template {template_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error preparing template config: {e}")
            return None
    
    def _create_krkn_config(self, scenario_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a complete KRKN configuration structure.
        
        Args:
            scenario_config: The scenario configuration to wrap
            
        Returns:
            Complete KRKN configuration dictionary
        """
        return {
            'kraken': {
                'kubeconfig_path': '~/.kube/config',
                'exit_on_failure': False,
                'auto_rollback': True,
                'rollback_versions_directory': '/tmp/kraken-rollback',
                'publish_kraken_status': False,
                'signal_state': 'RUN',
                'signal_address': '0.0.0.0',
                'port': 8081,
                'chaos_scenarios': {
                    'template_scenarios': [scenario_config]
                }
            },
            'cerberus': {
                'cerberus_enabled': False,
                'cerberus_url': '',
                'check_application_routes': False
            },
            'performance_monitoring': {
                'prometheus_url': '',
                'prometheus_bearer_token': '',
                'uuid': None,
                'enable_alerts': False,
                'enable_metrics': False,
                'alert_profile': 'config/alerts.yaml',
                'metrics_profile': 'config/metrics-report.yaml',
                'check_critical_alerts': False
            },
            'tunings': {
                'wait_duration': 60,
                'iterations': 1,
                'daemon_mode': False
            },
            'elastic': {
                'enable_elastic': False,
                'verify_certs': False,
                'elastic_url': '',
                'elastic_port': 32766,
                'username': 'elastic',
                'password': 'test',
                'metrics_index': 'krkn-metrics',
                'alerts_index': 'krkn-alerts',
                'telemetry_index': 'krkn-telemetry',
                'run_tag': ''
            },
            'telemetry': {
                'enabled': False,
                'api_url': '',
                'username': '',
                'password': '',
                'prometheus_backup': True,
                'prometheus_namespace': '',
                'prometheus_container_name': '',
                'prometheus_pod_name': '',
                'full_prometheus_backup': False,
                'backup_threads': 5,
                'archive_path': '/tmp',
                'max_retries': 0,
                'run_tag': '',
                'archive_size': 500000,
                'telemetry_group': '',
                'logs_backup': True,
                'logs_filter_patterns': [
                    '(\\w{3}\\s\\d{1,2}\\s\\d{2}:\\d{2}:\\d{2}\\.\\d+).+',
                    'kinit (\\d+/\\d+/\\d+\\s\\d{2}:\\d{2}:\\d{2})\\s+',
                    '(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\.\\d+Z).+'
                ],
                'oc_cli_path': '/usr/bin/oc',
                'events_backup': True
            },
            'health_checks': {
                'interval': 2,
                'config': []
            },
            'kubevirt_checks': {
                'interval': 2,
                'namespace': '',
                'name': '',
                'only_failures': False,
                'disconnected': False,
                'ssh_node': '',
                'node_names': '',
                'exit_on_failure': False
            }
        }
    
    def _apply_parameters(self, config: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply parameter overrides to the scenario configuration.
        
        Args:
            config: Base scenario configuration
            params: Parameter overrides
            
        Returns:
            Updated configuration
        """
        # Deep copy to avoid modifying the original
        updated_config = config.copy()
        
        # Apply parameters to the first scenario's config
        if isinstance(updated_config, list) and len(updated_config) > 0:
            if 'config' in updated_config[0]:
                scenario_config = updated_config[0]['config'].copy()
                
                for param_name, param_value in params.items():
                    # Handle nested parameters (e.g., "target_pods.label_selector")
                    if '.' in param_name:
                        keys = param_name.split('.')
                        current = scenario_config
                        for key in keys[:-1]:
                            if key not in current:
                                current[key] = {}
                            current = current[key]
                        current[keys[-1]] = param_value
                    else:
                        scenario_config[param_name] = param_value
                
                updated_config[0]['config'] = scenario_config
        else:
            # Apply parameters directly to config if it's a dict
            if isinstance(updated_config, dict):
                for param_name, param_value in params.items():
                    if '.' in param_name:
                        keys = param_name.split('.')
                        current = updated_config
                        for key in keys[:-1]:
                            if key not in current:
                                current[key] = {}
                            current = current[key]
                        current[keys[-1]] = param_value
                    else:
                        updated_config[param_name] = param_value
        
        return updated_config
    
    def validate_template(self, template_name: str) -> bool:
        """
        Validate that a template has all required files.
        
        Args:
            template_name: Name of the template
            
        Returns:
            True if template is valid, False otherwise
        """
        template_dir = self.templates_dir / template_name
        
        if not template_dir.exists():
            self.logger.error(f"Template directory {template_name} not found")
            return False
            
        required_files = ["scenario.yaml", "metadata.yaml", "README.md"]
        
        for file_name in required_files:
            file_path = template_dir / file_name
            if not file_path.exists():
                self.logger.error(f"Required file {file_name} not found in template {template_name}")
                return False
                
        return True
    
    def get_template_categories(self) -> List[str]:
        """
        Get all unique template categories.
        
        Returns:
            List of category names
        """
        templates = self.list_templates()
        categories = set()
        
        for template_data in templates.values():
            if 'category' in template_data:
                categories.add(template_data['category'])
                
        return sorted(list(categories))
    
    def get_templates_by_category(self, category: str) -> Dict[str, Dict[str, Any]]:
        """
        Get templates filtered by category.
        
        Args:
            category: Category to filter by
            
        Returns:
            Dictionary of templates in the specified category
        """
        all_templates = self.list_templates()
        filtered_templates = {}
        
        for template_name, template_data in all_templates.items():
            if template_data.get('category') == category:
                filtered_templates[template_name] = template_data
                
        return filtered_templates


def list_templates_command(args) -> int:
    """
    CLI command to list available templates.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        template_manager = TemplateManager(args.templates_dir)
        templates = template_manager.list_templates()
        
        if not templates:
            print("No templates found.")
            return 0
        
        print("Available KRKN Chaos Scenario Templates:")
        print("=" * 50)
        
        for name, metadata in templates.items():
            print(f"\nTemplate: {name}")
            print(f"   Description: {metadata.get('description', 'No description')}")
            print(f"   Risk Level: {metadata.get('risk_level', 'unknown')}")
            print(f"   Category: {metadata.get('category', 'unknown')}")
            print(f"   Target: {metadata.get('target', 'unknown')}")
            print(f"   Duration: {metadata.get('estimated_duration', 'unknown')}")
        
        return 0
        
    except Exception as e:
        print(f"Error listing templates: {e}")
        return 1


def show_template_command(args) -> int:
    """
    CLI command to show detailed information about a template.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        template_manager = TemplateManager(args.templates_dir)
        details = template_manager.get_template_details(args.template)
        
        if not details:
            print(f"Template '{args.template}' not found.")
            return 1
        
        metadata = details.get('metadata', {})
        print(f"Template: {args.template}")
        print("=" * 50)
        print(f"Description: {metadata.get('description', 'No description')}")
        print(f"Risk Level: {metadata.get('risk_level', 'unknown')}")
        print(f"Category: {metadata.get('category', 'unknown')}")
        print(f"Target: {metadata.get('target', 'unknown')}")
        print(f"Version: {metadata.get('version', 'unknown')}")
        print(f"Author: {metadata.get('author', 'unknown')}")
        print(f"Duration: {metadata.get('estimated_duration', 'unknown')}")
        
        if 'tags' in metadata:
            print(f"Tags: {', '.join(metadata['tags'])}")
        
        if 'parameters' in metadata:
            print("\nParameters:")
            for param in metadata['parameters']:
                print(f"   - {param['name']}: {param['description']}")
                print(f"     Type: {param['type']}, Default: {param['default']}")
        
        if args.show_readme and 'readme' in details:
            print("\nREADME:")
            print("-" * 30)
            print(details['readme'])
        
        return 0
        
    except Exception as e:
        print(f"Error showing template details: {e}")
        return 1


def run_template_command(args) -> int:
    """
    CLI command to run a template.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    config_path = None
    try:
        template_manager = TemplateManager(args.templates_dir)
        
        # Validate template exists
        if not template_manager.validate_template(args.template):
            print(f"Template '{args.template}' is not valid or not found.")
            return 1
        
        # Parse parameters
        params = {}
        if args.param:
            for param in args.param:
                if '=' in param:
                    key, value = param.split('=', 1)
                    # Try to convert to appropriate type
                    if value.lower() in ['true', 'false']:
                        value = value.lower() == 'true'
                    elif value.isdigit():
                        value = int(value)
                    params[key] = value
                else:
                    print(f"Warning: Parameter '{param}' should be in format 'key=value'")
        
        # Prepare template configuration
        config_path = template_manager.prepare_template_config(args.template, params)
        
        if not config_path:
            print(f"Failed to prepare template '{args.template}'.")
            return 1
        
        print(f"Running template '{args.template}'...")
        print(f"Configuration: {config_path}")
        
        if params:
            print("Parameters:")
            for key, value in params.items():
                print(f"   {key}: {value}")
        
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
        try:
            # Add package directory to path for import
            package_root = Path(__file__).parent.parent
            sys.path.insert(0, str(package_root))
            
            # Try to import and run kraken
            try:
                from run_kraken import main as kraken_main
                retval = kraken_main(options, None)
            except ImportError as e:
                if 'krkn_lib' in str(e):
                    print("KRKN dependencies not available. Template config prepared successfully:")
                    print(f"Config file: {config_path}")
                    print("Run manually with: python run_kraken.py --cfg", config_path)
                    retval = 0
                else:
                    print(f"Cannot import KRKN main function: {e}")
                    print("Make sure you're running this from the KRKN root directory")
                    retval = 1
        except Exception as e:
            print(f"Error running KRKN: {e}")
            retval = 1
        
        # Only clean up temporary config file on successful execution
        if retval == 0:
            try:
                if os.path.exists(config_path):
                    os.remove(config_path)
                    print("Cleaned up temporary configuration file")
            except Exception as e:
                print(f"Warning: Could not clean up temporary config file: {e}")
        else:
            print(f"Configuration file preserved for debugging: {config_path}")
            
        if retval == 0:
            print(f"Template '{args.template}' completed successfully!")
        else:
            print(f"Template '{args.template}' failed with exit code {retval}")
            
        return retval
            
    except Exception as e:
        print(f"Error running template: {e}")
        if config_path and os.path.exists(config_path):
            print(f"Configuration file preserved for debugging: {config_path}")
        return 1


def main() -> int:
    """
    Main entry point for template CLI commands.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    try:
        parser = argparse.ArgumentParser(
            description="KRKN Template Manager - Manage and run chaos scenario templates"
        )
        
        parser.add_argument(
            "--templates-dir",
            default="templates/chaos-scenarios",
            help="Path to templates directory"
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # List templates command
        list_parser = subparsers.add_parser('list', help='List available templates')
        list_parser.set_defaults(func=list_templates_command)
        
        # Show template details command
        show_parser = subparsers.add_parser('show', help='Show template details')
        show_parser.add_argument('template', help='Template name')
        show_parser.add_argument(
            '--show-readme', 
            action='store_true',
            help='Show full README content'
        )
        show_parser.set_defaults(func=show_template_command)
        
        # Run template command
        run_parser = subparsers.add_parser('run', help='Run a template')
        run_parser.add_argument('template', help='Template name')
        run_parser.add_argument(
            '--param', 
            action='append',
            help='Override template parameter (key=value)'
        )
        run_parser.add_argument(
            '--output', 
            help='Output report location'
        )
        run_parser.add_argument(
            '--debug', 
            action='store_true',
            help='Enable debug logging'
        )
        run_parser.set_defaults(func=run_template_command)
        
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return 1
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s'
        )
        
        # Execute the command and return exit code
        return args.func(args)
        
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
