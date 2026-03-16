#!/usr/bin/env python
"""
Simple test script to validate template functionality
"""

import os
import sys
import yaml
from pathlib import Path

# Add the krkn directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'krkn'))

from template_manager import TemplateManager

def test_template_manager():
    """Test the TemplateManager functionality"""
    print("🧪 Testing KRKN Template Manager")
    print("=" * 50)
    
    # Initialize template manager
    templates_dir = Path(__file__).parent / "templates" / "chaos-scenarios"
    template_manager = TemplateManager(str(templates_dir))
    
    # Test 1: List templates
    print("\n📋 Test 1: Listing available templates")
    templates = template_manager.list_templates()
    
    if templates:
        print(f"✓ Found {len(templates)} templates:")
        for template in templates:
            print(f"  - {template.get('name', 'Unknown')} ({template.get('risk_level', 'Unknown')})")
    else:
        print("✗ No templates found")
        return False
    
    # Test 2: Get specific template
    print(f"\n📄 Test 2: Getting template details for 'pod-failure'")
    template = template_manager.get_template('pod-failure')
    
    if template:
        print("✓ Template loaded successfully")
        print(f"  - Description: {template['metadata'].get('description', 'N/A')}")
        print(f"  - Target: {template['metadata'].get('target', 'N/A')}")
        print(f"  - Risk Level: {template['metadata'].get('risk_level', 'N/A')}")
        print(f"  - Parameters: {len(template['metadata'].get('parameters', []))}")
    else:
        print("✗ Failed to load template")
        return False
    
    # Test 3: Validate template
    print(f"\n✅ Test 3: Validating 'pod-failure' template")
    validation_result = template_manager.validate_template('pod-failure')
    
    if validation_result['valid']:
        print("✓ Template validation passed")
    else:
        print("✗ Template validation failed:")
        for error in validation_result['errors']:
            print(f"  - {error}")
        return False
    
    # Test 4: Test parameter override
    print(f"\n⚙️ Test 4: Testing parameter override functionality")
    original_scenario = template['scenario']
    params = {'kill': 2, 'namespace_pattern': '^production$'}
    
    modified_scenario = template_manager._apply_parameter_overrides(
        original_scenario, 
        template['metadata'], 
        params
    )
    
    if modified_scenario and modified_scenario[0]['config'].get('kill') == 2:
        print("✓ Parameter override working correctly")
    else:
        print("✗ Parameter override failed")
        return False
    
    # Test 5: Check all templates have required files
    print(f"\n📁 Test 5: Checking template file structure")
    all_valid = True
    for template_name in [t['name'] for t in templates]:
        template_path = templates_dir / template_name
        required_files = ['scenario.yaml', 'metadata.yaml', 'README.md']
        
        missing_files = []
        for file_name in required_files:
            if not (template_path / file_name).exists():
                missing_files.append(file_name)
        
        if missing_files:
            print(f"✗ Template '{template_name}' missing files: {missing_files}")
            all_valid = False
        else:
            print(f"✓ Template '{template_name}' has all required files")
    
    return all_valid

def test_template_content():
    """Test the content of templates"""
    print("\n🔍 Testing Template Content")
    print("=" * 50)
    
    templates_dir = Path(__file__).parent / "templates" / "chaos-scenarios"
    
    # Check each template's metadata
    required_metadata_fields = ['name', 'description', 'target', 'risk_level', 'category']
    
    for template_dir in templates_dir.iterdir():
        if template_dir.is_dir():
            print(f"\n📋 Checking template: {template_dir.name}")
            
            # Check metadata
            metadata_file = template_dir / "metadata.yaml"
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r') as f:
                        metadata = yaml.safe_load(f)
                    
                    missing_fields = []
                    for field in required_metadata_fields:
                        if field not in metadata:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        print(f"  ✗ Missing metadata fields: {missing_fields}")
                    else:
                        print(f"  ✓ All required metadata fields present")
                        print(f"    - Risk Level: {metadata.get('risk_level', 'N/A')}")
                        print(f"    - Target: {metadata.get('target', 'N/A')}")
                        
                except Exception as e:
                    print(f"  ✗ Error reading metadata: {e}")
            else:
                print(f"  ✗ Metadata file missing")
            
            # Check scenario
            scenario_file = template_dir / "scenario.yaml"
            if scenario_file.exists():
                try:
                    with open(scenario_file, 'r') as f:
                        scenario = yaml.safe_load(f)
                    
                    if isinstance(scenario, list) and len(scenario) > 0:
                        print(f"  ✓ Scenario file valid")
                    else:
                        print(f"  ✗ Scenario file invalid (should be non-empty list)")
                        
                except Exception as e:
                    print(f"  ✗ Error reading scenario: {e}")
            else:
                print(f"  ✗ Scenario file missing")
            
            # Check README
            readme_file = template_dir / "README.md"
            if readme_file.exists():
                with open(readme_file, 'r') as f:
                    readme_content = f.read()
                
                if len(readme_content) > 100:  # Basic content check
                    print(f"  ✓ README file has content")
                else:
                    print(f"  ✗ README file too short")
            else:
                print(f"  ✗ README file missing")

def main():
    """Main test function"""
    print("🚀 KRKN Chaos Library - Test Suite")
    print("=" * 60)
    
    # Test template manager
    template_tests_passed = test_template_manager()
    
    # Test template content
    test_template_content()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 50)
    
    if template_tests_passed:
        print("✅ All template manager tests passed!")
        print("✅ Template functionality is working correctly!")
        print("\n🎉 KRKN Chaos Library implementation is complete!")
        
        print("\n📚 Available Templates:")
        templates_dir = Path(__file__).parent / "templates" / "chaos-scenarios"
        for template_dir in sorted(templates_dir.iterdir()):
            if template_dir.is_dir():
                metadata_file = template_dir / "metadata.yaml"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = yaml.safe_load(f)
                    print(f"  - {metadata.get('name', template_dir.name)}: {metadata.get('description', 'No description')}")
        
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
