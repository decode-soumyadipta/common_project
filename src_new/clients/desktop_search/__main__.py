"""Allow package to be run as a module: python -m src_new.clients.desktop_search"""
import sys

from src_new.clients.desktop_search.main import main

if __name__ == "__main__":
    sys.exit(main())
