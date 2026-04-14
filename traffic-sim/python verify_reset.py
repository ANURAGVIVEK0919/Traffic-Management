import os

PROJECT_ROOT = os.getcwd()

model_exts = (".pt", ".pth", ".pkl", ".h5")
log_exts = (".log",)
pycache_name = "__pycache__"

model_files = []
log_files = []
pycache_dirs = []
uploads_exists = False
logs_exists = False

# Walk through project
for root, dirs, files in os.walk(PROJECT_ROOT):

    # Skip virtual environment
    if ".venv" in root:
        continue

    # Check pycache
    for d in dirs:
        if d == pycache_name:
            pycache_dirs.append(os.path.join(root, d))

    # Check files
    for file in files:
        path = os.path.join(root, file)

        if file.endswith(model_exts):
            model_files.append(path)

        if file.endswith(log_exts):
            log_files.append(path)

# Check logs folder
if os.path.exists("logs"):
    logs_exists = True

# Check uploads folder
if os.path.exists("uploads"):
    uploads_exists = True

# Check rl_logs.csv
rl_log_path = os.path.join("models", "rl_logs.csv")
rl_log_lines = 0

if os.path.exists(rl_log_path):
    with open(rl_log_path, "r") as f:
        rl_log_lines = len(f.readlines())

# 🔍 Print results
print("\n========== PHASE 1 VERIFICATION ==========\n")

print(f"Model files found: {len(model_files)}")
for f in model_files:
    print("  ", f)

print(f"\nLog files found: {len(log_files)}")
for f in log_files[:10]:
    print("  ", f)

print(f"\n__pycache__ folders found: {len(pycache_dirs)}")

print(f"\nlogs/ folder exists: {logs_exists}")
print(f"uploads/ folder exists: {uploads_exists}")

print(f"\nrl_logs.csv line count: {rl_log_lines}")

print("\n========== RESULT ==========\n")

# Final decision
if (
    len(model_files) == 0 and
    len(log_files) == 0 and
    len(pycache_dirs) == 0 and
    not logs_exists and
    not uploads_exists and
    rl_log_lines == 1
):
    print("✅ PHASE 1 COMPLETE — CLEAN STATE CONFIRMED")
else:
    print("❌ PHASE 1 NOT CLEAN — FIX ABOVE ISSUES")