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
Test script for KRKN Template functionality
"""

import sys
import os
import yaml
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_template_listing():
    """Test template listing functionality"""
    print("🧪 Testing Template Listing...")
    
    try:
        from krkn.template_manager import TemplateManager
        template_manager = TemplateManager()
        templates = template_manager.list_templates()
        
        print(f"✅ Found {len(templates)} templates")
        
        expected_templates = [
            'pod-failure', 'node-failure', 'network-latency', 
            'cpu-stress', 'disk-stress', 'pod-kill', 
            'container-restart', 'vm-outage', 'resource-failure'
        ]
        
        for template_name in expected_templates:
            if template_name in templates:
                print(f"✅ Template '{template_name}' found")
            else:
                print(f"❌ Template '{template_name}' missing")
                
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_template_details():
    """Test template details functionality"""
    print("\n🧪 Testing Template Details...")
    
    try:
        from krkn.template_manager import TemplateManager
        template_manager = TemplateManager()
        details = template_manager.get_template_details('pod-failure')
        
        if details and 'metadata' in details and 'scenario' in details:
            print("✅ Template details retrieved successfully")
            print(f"   Description: {details['metadata'].get('description', 'N/A')}")
            print(f"   Risk Level: {details['metadata'].get('risk_level', 'N/A')}")
            return True
        else:
            print("❌ Incomplete template details")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_template_validation():
    """Test template validation functionality"""
    print("\n🧪 Testing Template Validation...")
    
    try:
        from krkn.template_manager import TemplateManager
        template_manager = TemplateManager()
        
        # Test valid template
        if template_manager.validate_template('pod-failure'):
            print("✅ Valid template validation passed")
        else:
            print("❌ Valid template validation failed")
            return False
        
        # Test invalid template
        if not template_manager.validate_template('nonexistent-template'):
            print("✅ Invalid template validation passed")
        else:
            print("❌ Invalid template validation failed")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_template_config_preparation():
    """Test template configuration preparation"""
    print("\n🧪 Testing Template Config Preparation...")
    
    try:
        from krkn.template_manager import TemplateManager
        template_manager = TemplateManager()
        
        # Test with no parameters
        config_path = template_manager.prepare_template_config('pod-failure')
        if config_path and os.path.exists(config_path):
            print("✅ Config preparation without parameters successful")
            
            # Verify config content
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config and len(config) > 0:
                    print("✅ Config content is valid")
                else:
                    print("❌ Config content is invalid")
                    return False
            
            # Clean up
            os.remove(config_path)
        else:
            print("❌ Config preparation failed")
            return False
        
        # Test with parameters
        params = {
            'name_pattern': '^test-.*$',
            'kill': 2,
            'krkn_pod_recovery_time': 180
        }
        config_path = template_manager.prepare_template_config('pod-failure', params)
        if config_path and os.path.exists(config_path):
            print("✅ Config preparation with parameters successful")
            
            # Verify parameter application
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                scenario_config = config[0]['config']
                if (scenario_config.get('name_pattern') == '^test-.*$' and 
                    scenario_config.get('kill') == 2 and
                    scenario_config.get('krkn_pod_recovery_time') == 180):
                    print("✅ Parameter application successful")
                else:
                    print("❌ Parameter application failed")
                    return False
            
            # Clean up
            os.remove(config_path)
        else:
            print("❌ Config preparation with parameters failed")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_template_categories():
    """Test template categories functionality"""
    print("\n🧪 Testing Template Categories...")
    
    try:
        from krkn.template_manager import TemplateManager
        template_manager = TemplateManager()
        
        categories = template_manager.get_template_categories()
        expected_categories = ['availability', 'performance']
        
        print(f"✅ Found categories: {categories}")
        
        for category in expected_categories:
            if category in categories:
                print(f"✅ Category '{category}' found")
            else:
                print(f"❌ Category '{category}' missing")
                return False
        
        # Test filtering by category
        availability_templates = template_manager.get_templates_by_category('availability')
        if len(availability_templates) > 0:
            print(f"✅ Found {len(availability_templates)} availability templates")
        else:
            print("❌ No availability templates found")
            return False
            
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_template_structure():
    """Test that all templates have the required structure"""
    print("\n🧪 Testing Template Structure...")
    
    templates_dir = Path("templates/chaos-scenarios")
    required_files = ["scenario.yaml", "metadata.yaml", "README.md"]
    
    if not templates_dir.exists():
        print("❌ Templates directory not found")
        return False
    
    all_valid = True
    for template_dir in templates_dir.iterdir():
        if template_dir.is_dir():
            template_name = template_dir.name
            print(f"   Checking template '{template_name}'...")
            
            for required_file in required_files:
                file_path = template_dir / required_file
                if file_path.exists():
                    print(f"     ✅ {required_file} exists")
                else:
                    print(f"     ❌ {required_file} missing")
                    all_valid = False
            
            # Validate metadata structure
            metadata_file = template_dir / "metadata.yaml"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = yaml.safe_load(f)
                    
                    required_fields = ['name', 'description', 'target', 'risk_level', 'category']
                    for field in required_fields:
                        if field in metadata:
                            print(f"     ✅ {field} present in metadata")
                        else:
                            print(f"     ❌ {field} missing from metadata")
                            all_valid = False
                            
                except Exception as e:
                    print(f"     ❌ Error reading metadata: {e}")
                    all_valid = False
    
    return all_valid

def main():
    """Run all tests"""
    print("🚀 KRKN Template Functionality Tests")
    print("=" * 50)
    
    tests = [
        test_template_listing,
        test_template_details,
        test_template_validation,
        test_template_config_preparation,
        test_template_categories,
        test_template_structure
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Template system is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
