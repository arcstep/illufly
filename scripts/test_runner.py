# scripts/test_runner.py
import sys
from pytest import main as pytest_main

def main():
    sys.exit(pytest_main())

if __name__ == "__main__":
    main()