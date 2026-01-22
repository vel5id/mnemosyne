"""
Pytest configuration for Mnemosyne Core tests.

Ensures the project root is in PYTHONPATH for proper module imports.
"""

import sys
from pathlib import Path

# Add project root to PYTHONPATH
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
