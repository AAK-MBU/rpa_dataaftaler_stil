"""PyInstaller entry point for the Dataaftaler desktop app.

Kept at the repo root (not inside ``gui/``) so the frozen app resolves the same
top-level modules — ``main``, ``helpers``, ``processes``, ``gui`` — that
``python -m gui.app`` does. Build it into a Windows ``.exe`` with PyInstaller;
see ``BUILD.md``.
"""

from gui.app import main

if __name__ == "__main__":
    main()
