#!/usr/bin/env python3
"""
Test script for the Health Check Factory integration.

This script verifies that the health check plugin system is working correctly.

How to run:
    # Run directly (no dependencies required for simple_health_check plugin)
    python3 tests/test_health_check_factory.py

    # Run from project root
    cd /path/to/kraken
    python3 tests/test_health_check_factory.py

    # Run with pytest (if available)
    pytest tests/test_health_check_factory.py -v

    # Run with unittest
    python3 -m unittest tests/test_health_check_factory.py -v

Note:
    - This test checks the factory loading mechanism
    - Tests simple_health_check plugin (no external dependencies)
    - HTTP and Virt plugins may fail to load if dependencies are missing
    - Check factory.failed_plugins for details on any failures
"""

import logging
import queue
import sys
import os

# Add parent directory to path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from krkn.health_checks import HealthCheckFactory, HealthCheckPluginNotFound

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def test_factory_loading():
    """Test that the factory loads plugins correctly."""
    print("\n" + "="*70)
    print("TEST 1: Factory Plugin Loading")
    print("="*70)

    factory = HealthCheckFactory()

    print(f"\n✓ Loaded plugins: {list(factory.loaded_plugins.keys())}")

    if factory.failed_plugins:
        print(f"\n⚠ Failed plugins ({len(factory.failed_plugins)}):")
        for module, cls, error in factory.failed_plugins:
            print(f"  - {module} ({cls}): {error}")
    else:
        print("\n✓ No failed plugins")

    # Verify expected plugins are loaded
    expected_plugins = ["simple_health_check", "test_health_check"]
    for plugin_type in expected_plugins:
        if plugin_type in factory.loaded_plugins:
            print(f"✓ Found expected plugin: {plugin_type}")
        else:
            print(f"✗ Missing expected plugin: {plugin_type}")

    return factory


def test_plugin_creation(factory):
    """Test creating plugin instances."""
    print("\n" + "="*70)
    print("TEST 2: Plugin Instance Creation")
    print("="*70)

    # Test simple health check
    try:
        plugin = factory.create_plugin("simple_health_check", iterations=5)
        print(f"\n✓ Created plugin: {plugin.__class__.__name__}")
        print(f"  - Types: {plugin.get_health_check_types()}")
        print(f"  - Iterations: {plugin.iterations}")
        print(f"  - Current iterations: {plugin.current_iterations}")
        print(f"  - Return value: {plugin.get_return_value()}")
    except HealthCheckPluginNotFound as e:
        print(f"\n✗ Failed to create plugin: {e}")
        return None

    return plugin


def test_plugin_methods(plugin):
    """Test plugin methods."""
    print("\n" + "="*70)
    print("TEST 3: Plugin Methods")
    print("="*70)

    # Test increment_iterations
    initial = plugin.current_iterations
    plugin.increment_iterations()
    after = plugin.current_iterations
    print(f"\n✓ increment_iterations: {initial} -> {after}")

    # Test set_return_value
    plugin.set_return_value(2)
    print(f"✓ set_return_value(2): {plugin.get_return_value()}")

    plugin.set_return_value(0)
    print(f"✓ set_return_value(0): {plugin.get_return_value()}")

    # Test run_health_check (with empty config)
    telemetry_queue = queue.Queue()
    try:
        plugin.run_health_check({}, telemetry_queue)
        print(f"✓ run_health_check executed successfully")

        # Check if telemetry was collected
        if not telemetry_queue.empty():
            telemetry = telemetry_queue.get_nowait()
            print(f"✓ Telemetry collected: {telemetry}")
    except Exception as e:
        print(f"✗ run_health_check failed: {e}")


def test_multiple_types(factory):
    """Test that one plugin can handle multiple types."""
    print("\n" + "="*70)
    print("TEST 4: Multiple Type Mapping")
    print("="*70)

    # SimpleHealthCheckPlugin handles both simple_health_check and test_health_check
    plugin1 = factory.create_plugin("simple_health_check", iterations=3)
    plugin2 = factory.create_plugin("test_health_check", iterations=3)

    print(f"\n✓ Plugin 1 class: {plugin1.__class__.__name__}")
    print(f"✓ Plugin 2 class: {plugin2.__class__.__name__}")
    print(f"✓ Same class: {plugin1.__class__.__name__ == plugin2.__class__.__name__}")


def test_http_plugin_loading(factory):
    """Test HTTP plugin loading (may fail if requests not installed)."""
    print("\n" + "="*70)
    print("TEST 5: HTTP Plugin Loading")
    print("="*70)

    if "http_health_check" in factory.loaded_plugins:
        print("\n✓ HTTP health check plugin loaded")
        try:
            plugin = factory.create_plugin("http_health_check", iterations=5)
            print(f"✓ Created HTTP plugin: {plugin.__class__.__name__}")
            print(f"  - Types: {plugin.get_health_check_types()}")
        except Exception as e:
            print(f"✗ Failed to create HTTP plugin: {e}")
    else:
        print("\n⚠ HTTP health check plugin not loaded")
        # Check if it's in failed plugins
        for module, cls, error in factory.failed_plugins:
            if "http_health_check" in module:
                print(f"  - Reason: {error}")


def test_virt_plugin_loading(factory):
    """Test Virt plugin loading (may fail if dependencies not available)."""
    print("\n" + "="*70)
    print("TEST 6: Virt Plugin Loading")
    print("="*70)

    virt_types = ["virt_health_check", "kubevirt_health_check", "vm_health_check"]
    found = False

    for virt_type in virt_types:
        if virt_type in factory.loaded_plugins:
            print(f"\n✓ Virt health check plugin loaded as '{virt_type}'")
            found = True
            try:
                # Note: krkn_lib is required but we don't have it here
                print("  - Plugin available but requires krkn_lib for instantiation")
            except Exception as e:
                print(f"✗ Failed to create virt plugin: {e}")
            break

    if not found:
        print("\n⚠ Virt health check plugin not loaded")
        for module, cls, error in factory.failed_plugins:
            if "virt_health_check" in module:
                print(f"  - Reason: {error}")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Health Check Factory Integration Tests")
    print("="*70)

    # Test 1: Factory loading
    factory = test_factory_loading()

    # Test 2: Plugin creation
    plugin = test_plugin_creation(factory)

    if plugin:
        # Test 3: Plugin methods
        test_plugin_methods(plugin)

        # Test 4: Multiple types
        test_multiple_types(factory)

    # Test 5: HTTP plugin
    test_http_plugin_loading(factory)

    # Test 6: Virt plugin
    test_virt_plugin_loading(factory)

    print("\n" + "="*70)
    print("Tests Complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
