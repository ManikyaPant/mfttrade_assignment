"""Add the project root to sys.path."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
