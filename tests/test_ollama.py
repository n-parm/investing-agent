#!/usr/bin/env python
"""Test Ollama connectivity with enhanced diagnostics.

Usage:
    python test_ollama.py              # Show formatted diagnostics
    python test_ollama.py --json       # Output raw JSON
    python test_ollama.py --quiet      # Exit silently (useful for CI)

This script combines the functionality of tools/check_ollama.py and provides
multiple output formats for different use cases.
"""

import json
import sys
import os
import argparse

# Ensure the project root is on sys.path so `src` can be imported
# Go up one level from tests/ to reach project root
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from src.llm import check_ollama

def main():
    parser = argparse.ArgumentParser(
        description="Test Ollama connectivity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_ollama.py              Show formatted diagnostics
  python test_ollama.py --json       Output raw JSON (for parsing)
  python test_ollama.py --quiet      Silent exit (0 if OK, 2 if failed)
        """
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of formatted text"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Silent mode - only exit code (0=success, 2=failure)"
    )
    args = parser.parse_args()
    
    result = check_ollama()
    
    if args.quiet:
        # Exit silently - useful for CI/automation
        sys.exit(0 if result.get("ok") else 2)
    
    if args.json:
        # Output raw JSON - useful for parsing
        print(json.dumps(result, indent=2))
    else:
        # Output formatted diagnostics - human-readable
        print("\n" + "="*70)
        print("OLLAMA CONNECTIVITY DIAGNOSTIC")
        print("="*70 + "\n")
        
        print(json.dumps(result, indent=2))
        
        print("\n" + "="*70)
        if result.get("ok"):
            print("✓ SUCCESS: Ollama is reachable and ready!")
        else:
            print("✗ FAILURE: Ollama connection failed")
        print("="*70 + "\n")
    
    # Exit with appropriate code (0 for success, 2 for failure)
    sys.exit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()

