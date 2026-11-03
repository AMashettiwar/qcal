"""Local CI: python run_tests.py  (works the same in PowerShell and bash)."""
import subprocess, sys
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "tests"]))
