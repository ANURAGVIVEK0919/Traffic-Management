from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
HEADER = "timestep,reward,loss,epsilon,action"


def iter_files(pattern: str):
    for path in ROOT.rglob(pattern):
        if ".venv" in path.parts:
            continue
        if path.is_file():
            yield path


def iter_dirs(pattern: str):
    for path in ROOT.rglob(pattern):
        if ".venv" in path.parts:
            continue
        if path.is_dir():
            yield path


def check_models():
    exts = ("*.pt", "*.pth", "*.pkl", "*.h5")
    found = []
    for ext in exts:
        found.extend(iter_files(ext))
    return sorted(set(found))


def check_rl_log():
    rl_log = ROOT / "models" / "rl_logs.csv"
    if not rl_log.exists():
        return False, "missing"

    lines = rl_log.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        return False, f"expected 1 line, found {len(lines)}"
    if lines[0].strip() != HEADER:
        return False, f"header mismatch: {lines[0].strip()}"
    return True, "ok"


def check_pycache_dirs():
    return sorted(iter_dirs("__pycache__"))


def check_output_dirs():
    targets = ["logs", "outputs", "runs", "uploads"]
    status = {}
    for name in targets:
        path = ROOT / name
        if not path.exists():
            status[name] = "missing"
            continue
        if not path.is_dir():
            status[name] = "exists-non-dir"
            continue
        has_content = any(path.iterdir())
        status[name] = "empty" if not has_content else "non-empty"
    return status


def main():
    model_files = check_models()
    rl_ok, rl_detail = check_rl_log()
    pycache_dirs = check_pycache_dirs()
    output_status = check_output_dirs()

    print("=== Reset Verification ===")

    print("[1] Model files (*.pt, *.pth, *.pkl, *.h5):")
    if model_files:
        print(f"FAIL - found {len(model_files)} file(s)")
        for path in model_files:
            print(f"  - {path.relative_to(ROOT)}")
    else:
        print("PASS - none found")

    print("[2] models/rl_logs.csv one-line header check:")
    if rl_ok:
        print("PASS - header only")
    else:
        print(f"FAIL - {rl_detail}")

    print("[3] __pycache__ directories:")
    if pycache_dirs:
        print(f"FAIL - found {len(pycache_dirs)} directory(s)")
        for path in pycache_dirs:
            print(f"  - {path.relative_to(ROOT)}")
    else:
        print("PASS - none found")

    print("[4] logs/ outputs/ runs/ uploads/ state:")
    outputs_ok = True
    for key in ("logs", "outputs", "runs", "uploads"):
        value = output_status[key]
        if value not in ("missing", "empty"):
            outputs_ok = False
        print(f"  - {key}: {value}")
    if outputs_ok:
        print("PASS - all removed or empty")
    else:
        print("FAIL - one or more output dirs are not clean")

    overall_ok = (not model_files) and rl_ok and (not pycache_dirs) and outputs_ok
    print("\nOverall:", "PASS" if overall_ok else "FAIL")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
