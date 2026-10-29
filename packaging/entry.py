"""PyInstaller entry point of the portable build (PRD F22-1): the same ``main`` as the gui-script."""

from snapocr.__main__ import main

raise SystemExit(main())
