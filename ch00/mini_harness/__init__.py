"""Stage 0 package: the deliberately naive mini harness.

This package exists to make the problem visible before we fix it. Every
function here is written the way a first prototype usually looks: a workspace
folder, a string prefix check, and a shell call. Do not copy these helpers into
a real agent. Later chapters replace them one at a time.
"""

# The version string is repeated in each chapter so a reader can tell which
# snapshot they are running when they open a terminal in an old folder.
__version__ = "0.0.0"
