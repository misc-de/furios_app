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


def _deps():
    """miscde/deps.py, loaded by path: importing the package would import
    GTK 4 and libadwaita first - the very things it is there to look for."""
    import importlib.util
    for base in sys.path:
        path = os.path.join(base, "miscde", "deps.py")
        if os.path.isfile(path):
            spec = importlib.util.spec_from_file_location("miscde_deps", path)
            deps = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(deps)
            return deps
    return None


def main(argv):
    """The check first; the window only once it has said yes."""
    deps = _deps()
    if deps is not None and not deps.check():
        return 1
    from miscde.window import App
    return App().run(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
