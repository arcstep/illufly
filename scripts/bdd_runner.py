# scripts/bdd_runner.py
import sys
from behave.__main__ import main as behave_main

def main():
    sys.exit(behave_main())

if __name__ == "__main__":
    main()