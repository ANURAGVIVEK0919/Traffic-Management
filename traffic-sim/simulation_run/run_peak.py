import subprocess
from pathlib import Path

def run():
    launcher_path = Path(__file__).parent / "launcher.py"
    subprocess.run(["python", str(launcher_path), "peak_hour"])

if __name__ == "__main__":
    run()
