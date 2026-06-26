"""Enable ``python -m mcp_host_bridge`` and serve as the PyInstaller entry script."""

import sys

from mcp_host_bridge.cli import main

if __name__ == "__main__":
    sys.exit(main())
