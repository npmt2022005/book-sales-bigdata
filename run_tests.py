"""One command: python run_tests.py [--unit-only]. No data rebuild or overwrite."""
import argparse
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--unit-only',action='store_true');args=p.parse_args()
commands=[['src/test_benchmark_optimized.py'],['-m','unittest','discover','-s','tests','-v']]
if not args.unit_only:commands.append(['src/10_validate_data.py'])
for command in commands:
    completed=subprocess.run([sys.executable]+command,cwd=ROOT)
    if completed.returncode:sys.exit(completed.returncode)
print('ALL CHECKS PASSED')
