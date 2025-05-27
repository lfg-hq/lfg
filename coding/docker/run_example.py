#!/usr/bin/env python3
"""
Helper script to run Docker sandbox examples.

This script provides a simple way to run the examples from the examples.py file.
"""

import sys
import os
import importlib.util

def import_module_from_path(module_name, file_path):
    """Import a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    """Run the specified example or list available examples."""
    # Get the path to the examples.py file
    current_dir = os.path.dirname(os.path.abspath(__file__))
    examples_path = os.path.join(current_dir, "examples.py")
    
    if not os.path.exists(examples_path):
        print(f"Error: Could not find examples.py in {current_dir}")
        return 1
    
    # Import the examples module
    examples = import_module_from_path("examples", examples_path)
    
    # Get all example functions
    example_funcs = {
        name.replace("example_", ""): getattr(examples, name)
        for name in dir(examples)
        if name.startswith("example_") and callable(getattr(examples, name))
    }
    
    # Add the "all" option
    example_funcs["all"] = lambda: [func() for func in example_funcs.values()]
    
    # Get the example to run from command line arguments
    if len(sys.argv) < 2:
        print("Docker Sandbox Examples")
        print("======================")
        print("\nAvailable examples:")
        for name in sorted(example_funcs.keys()):
            print(f"  - {name}")
        print("\nUsage: python run_example.py <example_name>")
        print("Example: python run_example.py basic")
        return 0
    
    example_name = sys.argv[1]
    if example_name in example_funcs:
        print(f"Running example: {example_name}")
        example_funcs[example_name]()
    else:
        print(f"Unknown example: {example_name}")
        print(f"Available examples: {', '.join(sorted(example_funcs.keys()))}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 