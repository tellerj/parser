import atexit
import os
import shutil
import site
import sys

from setuptools import setup

# This file exists only as a fallback for direct invocations
# (e.g. `python setup.py install`).  pip uses pyproject.toml instead.
#
# When run directly:
#   - Auto-detects missing write access and falls back to --user install.
#   - Registers an atexit hook that screams loudly if the installed command
#     ends up outside PATH, so the install doesn't silently appear to work
#     while leaving the command unfindable.

_DIRECT_INSTALL_CMDS = {"install", "develop", "easy_install"}

if __name__ == "__main__" and any(cmd in sys.argv for cmd in _DIRECT_INSTALL_CMDS):
    if "--user" not in sys.argv:
        sp_dirs = getattr(site, "getsitepackages", lambda: [])()
        first_sp = next(iter(sp_dirs), None)
        if first_sp and not os.access(first_sp, os.W_OK):
            print(
                f"NOTICE: No write access to {first_sp}.\n"
                f"Installing for current user only ({site.getusersitepackages()}).\n"
            )
            sys.argv.append("--user")

    def _post_install_check():
        if shutil.which("link16-parser") is not None:
            return
        local_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
        border = "!" * 66
        print(f"""
{border}
  INSTALL INCOMPLETE — 'link16-parser' IS NOT ON YOUR PATH

  The command was installed to: {local_bin}
  That directory is not in your current PATH.

  Fix it right now:
    export PATH="$HOME/.local/bin:$PATH"

  Fix it permanently (add to your shell config, then reload):
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    source ~/.bashrc

  Or just use the install script next time, which handles this:
    ./install.sh
{border}
""")

    atexit.register(_post_install_check)

setup()
