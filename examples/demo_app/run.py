"""Example project: this build needs an environment variable the repo never declares.

Try it:

    cd examples/demo_app
    DEMO_LICENSE_KEY=granted python3 run.py     # passes locally
    python3 -m cleanroom test 'python3 run.py'  # clean room reports the hidden dependency
"""

import os
import sys

if os.environ.get("DEMO_LICENSE_KEY") != "granted":
    print("missing DEMO_LICENSE_KEY", file=sys.stderr)
    sys.exit(1)

print("build ok")
