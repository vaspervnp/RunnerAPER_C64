"""Runs every tests/test_*.py module, each in its own process (one VICE each)."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))


def run(module):
    proc = subprocess.run([sys.executable, "-m", "unittest", "-v", module], cwd=HERE,
                          capture_output=True, text=True)
    return module, proc.returncode, proc.stderr + proc.stdout


def main():
    wanted = sys.argv[1:]
    modules = sorted(f[:-3] for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
    if wanted:
        modules = [m for m in modules if any(w in m for w in wanted)]
    failed = []
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        for module, code, output in pool.map(run, modules):
            print(output.rstrip())
            if code:
                failed.append(module)
    print()
    print(f"{len(modules) - len(failed)}/{len(modules)} modules passed" + (f"; failed: {', '.join(failed)}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
