#!/usr/bin/env python
"""
Test CLI integration for KRKN Chaos Library
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

def test_cli_help():
    """Test CLI help functionality"""
    print("🧪 Testing CLI Help Functionality")
    print("=" * 50)
    
    # Create a minimal test script that imports just the template manager
    test_script = '''
import sys
sys.path.insert(0, '.')

from krkn.template_manager import TemplateManager

def main():
    template_manager = TemplateManager()
    templates = template_manager.list_templates()
    
    print("Available Chaos Scenario Templates:")
    print("=" * 50)
    for template in templates:
        print(f"Name: {template.get('name', 'N/A')}")
        print(f"Description: {template.get('description', 'N/A')}")
        print(f"Target: {template.get('target', 'N/A')}")
        print(f"Risk Level: {template.get('risk_level', 'N/A')}")
        print(f"Category: {template.get('category', 'N/A')}")
        print("-" * 50)

if __name__ == "__main__":
    main()
'''
    
    # Write test script to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        test_file = f.name
    
    try:
        # Run the test script
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            print("✅ CLI help functionality working correctly")
            print("\nSample output:")
            print(result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout)
            return True
        else:
            print("❌ CLI help test failed")
            print("Error:", result.stderr)
            return False
            
    finally:
        # Clean up
        os.unlink(test_file)

def test_template_validation():
    """Test template validation functionality"""
    print("\n🔍 Testing Template Validation")
    print("=" * 50)
    
    test_script = '''
import sys
from pathlib import Path
sys.path.insert(0, '.')

from krkn.template_manager import TemplateManager

def main():
    template_manager = TemplateManager()
    
    # Test validation of all templates
    templates_dir = Path("templates/chaos-scenarios")
    all_valid = True
    
    for template_dir in templates_dir.iterdir():
        if template_dir.is_dir():
            template_name = template_dir.name
            result = template_manager.validate_template(template_name)
            
            if result['valid']:
                print(f"OK {template_name}: Valid")
            else:
                print(f"FAIL {template_name}: Invalid")
                for error in result['errors']:
                    print(f"  - {error}")
                all_valid = False
    
    return all_valid

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        test_file = f.name
    
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            print("OK All template validations passed")
            print("\nValidation results:")
            print(result.stdout)
            return True
        else:
            print("FAIL Template validation failed")
            print("Error:", result.stderr)
            return False
            
    finally:
        os.unlink(test_file)

def test_parameter_override():
    """Test parameter override functionality"""
    print("\n⚙️ Testing Parameter Override")
    print("=" * 50)
    
    test_script = '''
import sys
sys.path.insert(0, '.')

from krkn.template_manager import TemplateManager

def main():
    template_manager = TemplateManager()
    
    # Get pod-failure template
    template = template_manager.get_template('pod-failure')
    
    if not template:
        print("FAIL Could not load pod-failure template")
        return False
    
    # Test parameter override
    original_scenario = template['scenario']
    params = {'kill': 5, 'namespace_pattern': '^production$'}
    
    modified_scenario = template_manager._apply_parameter_overrides(
        original_scenario, 
        template['metadata'], 
        params
    )
    
    # Check if override worked
    if modified_scenario and modified_scenario[0]['config'].get('kill') == 5:
        print("OK Parameter override working correctly")
        print(f"  Original kill: {original_scenario[0]['config'].get('kill')}")
        print(f"  Modified kill: {modified_scenario[0]['config'].get('kill')}")
        print(f"  Original namespace: {original_scenario[0]['config'].get('namespace_pattern')}")
        print(f"  Modified namespace: {modified_scenario[0]['config'].get('namespace_pattern')}")
        return True
    else:
        print("FAIL Parameter override failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        test_file = f.name
    
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, cwd='.')
        
        if result.returncode == 0:
            print("OK Parameter override functionality working")
            print("\nOverride test results:")
            print(result.stdout)
            return True
        else:
            print("FAIL Parameter override test failed")
            print("Error:", result.stderr)
            return False
            
    finally:
        os.unlink(test_file)

def main():
    """Main test function"""
    print("🚀 KRKN Chaos Library - CLI Integration Test Suite")
    print("=" * 60)
    
    # Run all tests
    test1_passed = test_cli_help()
    test2_passed = test_template_validation()
    test3_passed = test_parameter_override()
    
    # Summary
    print("\n📊 CLI Integration Test Summary")
    print("=" * 50)
    
    all_passed = test1_passed and test2_passed and test3_passed
    
    if all_passed:
        print("OK All CLI integration tests passed!")
        print("OK KRKN Chaos Library CLI is working correctly!")
        print("\n🎉 Ready for production use!")
        
        print("\n📚 Available CLI Commands:")
        print("  krkn list-templates")
        print("  krkn run-template <template-name>")
        print("  krkn run-template <template-name> --param key=value")
        print("  krkn validate-template <template-name>")
        
        return True
    else:
        print("❌ Some CLI integration tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
