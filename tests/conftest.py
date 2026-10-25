"""Shared test configuration.

With pytest's default (prepend) import mode and no ``__init__.py`` under
``tests/``, this conftest puts ``tests/`` on ``sys.path``, which makes the
``support`` helpers importable as ``from support.png import ...``.
"""
