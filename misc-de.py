#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""What `misc-de` starts. The app itself is the miscde package next to it.

This file stayed behind when the window was split up on 15.9.2026, and it is
deliberately this short. It is what install.sh copies to /usr/local/bin, what
the launcher entry names and what the app hands to execv when it restarts
itself into a new version - three things that should not have to change again
because a page moved.

The package is looked for next to this file first. From the source tree that
is the clone, so `./misc-de.py` runs what is checked out rather than what is
installed; from /usr/local/bin there is nothing beside it and the path added
below is the installed one.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
for base in (HERE, "/usr/local/lib/misc-de", "/usr/lib/misc-de"):
    if os.path.isdir(os.path.join(base, "miscde")):
        sys.path.insert(0, base)
        break

from miscde.window import App  # noqa: E402  - only after the path is set

if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
