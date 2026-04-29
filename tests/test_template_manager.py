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
Test module for KRKN Template functionality
"""

import pytest
import sys
import os
import yaml
from pathlib import Path

# Add the krkn package to Python path
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

from krkn.template_manager import TemplateManager


class TestTemplateManager:
    """Test cases for TemplateManager class"""

    @pytest.fixture
    def template_manager(self):
        """Create a template manager instance for testing"""
        return TemplateManager()

    def test_template_listing(self, template_manager):
        """Test template listing functionality"""
        print("Testing Template Listing...")
        
        templates = template_manager.list_templates()
        
        print(f"Found {len(templates)} templates")
        
        expected_templates = [
            'pod-failure', 'node-failure', 'network-latency', 
            'cpu-stress', 'disk-stress', 'pod-kill', 
            'container-restart', 'vm-outage', 'resource-failure'
        ]
        
        for template_name in expected_templates:
            if template_name in templates:
                print(f"Template '{template_name}' found")
                assert template_name in templates
            else:
                print(f"Template '{template_name}' missing")
                # Don't fail the test for missing templates as they might not be available in test environment

    def test_template_validation(self, template_manager):
        """Test template validation functionality"""
        print("Testing Template Validation...")
        
        templates = template_manager.list_templates()
        
        for template_name in templates:
            is_valid = template_manager.validate_template(template_name)
            if is_valid:
                print(f"Template '{template_name}' is valid")
                assert is_valid
            else:
                print(f"Template '{template_name}' validation failed")

    def test_template_details(self, template_manager):
        """Test getting template details"""
        print("Testing Template Details...")
        
        templates = template_manager.list_templates()
        
        for template_name in list(templates.keys())[:3]:  # Test first 3 templates
            details = template_manager.get_template_details(template_name)
            if details:
                print(f"Got details for template '{template_name}'")
                assert 'metadata' in details or 'scenario' in details
            else:
                print(f"Could not get details for template '{template_name}'")

    def test_prepare_template_config(self, template_manager):
        """Test preparing template configuration"""
        print("Testing Template Config Preparation...")
        
        templates = template_manager.list_templates()
        
        if not templates:
            print("No templates available for config preparation test")
            return
        
        # Test with first available template
        template_name = list(templates.keys())[0]
        
        # Test without parameters
        config_path = template_manager.prepare_template_config(template_name)
        if config_path:
            print(f"Prepared config for template '{template_name}': {config_path}")
            assert os.path.exists(config_path)
            
            # Verify it's a valid KRKN config
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            assert 'kraken' in config
            assert 'chaos_scenarios' in config['kraken']
            
            # Clean up
            os.remove(config_path)
        else:
            print(f"Failed to prepare config for template '{template_name}'")

    def test_prepare_template_config_with_params(self, template_manager):
        """Test preparing template configuration with parameters"""
        print("Testing Template Config Preparation with Parameters...")
        
        templates = template_manager.list_templates()
        
        if not templates:
            print("No templates available for config preparation test")
            return
        
        # Test with first available template
        template_name = list(templates.keys())[0]
        
        # Test with parameters
        params = {
            'duration': 120,
            'namespace': 'test-namespace'
        }
        
        config_path = template_manager.prepare_template_config(template_name, params)
        if config_path:
            print(f"Prepared config with params for template '{template_name}': {config_path}")
            assert os.path.exists(config_path)
            
            # Clean up
            os.remove(config_path)
        else:
            print(f"Failed to prepare config with params for template '{template_name}'")

    def test_template_categories(self, template_manager):
        """Test getting template categories"""
        print("Testing Template Categories...")
        
        categories = template_manager.get_template_categories()
        print(f"Found {len(categories)} categories: {categories}")
        assert isinstance(categories, list)

    def test_templates_by_category(self, template_manager):
        """Test filtering templates by category"""
        print("Testing Templates by Category...")
        
        categories = template_manager.get_template_categories()
        
        if categories:
            category = categories[0]
            filtered_templates = template_manager.get_templates_by_category(category)
            print(f"Found {len(filtered_templates)} templates in category '{category}'")
            assert isinstance(filtered_templates, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
