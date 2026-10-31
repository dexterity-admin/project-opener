"""Developer launcher: python run.py  (same as python -m project_opener)."""
import sys

from project_opener.app import main

if __name__ == "__main__":
    sys.exit(main())
