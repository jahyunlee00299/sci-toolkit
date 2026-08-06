#!/usr/bin/env python3
"""
Research Information Lookup Tool (Free APIs)
Wrapper that imports from the parent module.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from research_lookup import ResearchLookup, main

if __name__ == "__main__":
    sys.exit(main())
