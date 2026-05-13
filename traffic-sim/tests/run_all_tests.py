"""
Master Autonomous Test Runner
Runs all logic tests and generates a feature-compliance report.
"""

import subprocess
import os
import json
from datetime import datetime

TEST_FILES = [
    "tests/test_signal_core.py",
    "tests/test_v2i_preemption.py",
    "tests/preemption_trace_test.py", # Existing test
    "tests/groq_test.py"            # Existing test
]

def run_suite():
    print(f"Starting Autonomous Project Validation | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = {}
    
    for test_file in TEST_FILES:
        print(f"\nRunning: {test_file}...")
        try:
            # Run the test script and capture output
            process = subprocess.run(
                ["python", test_file],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if process.returncode == 0:
                print(f"PASS: {test_file}")
                results[test_file] = {"status": "PASS", "output": process.stdout}
            else:
                print(f"FAIL: {test_file}")
                print("-" * 40)
                print(process.stderr)
                print("-" * 40)
                results[test_file] = {"status": "FAIL", "error": process.stderr}
                
        except Exception as e:
            print(f"💥 Fatal Error running {test_file}: {e}")
            results[test_file] = {"status": "ERROR", "message": str(e)}

    print("\n" + "="*80)
    print("📊 GENERATING FINAL COMPLIANCE REPORT...")
    
    report_path = "tests/compliance_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 🚦 Hybrid AI Traffic Controller: Compliance Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("**Status:** " + ("✅ ALL SYSTEMS OPERATIONAL" if all(r["status"] == "PASS" for r in results.values()) else "⚠️ SOME FEATURES REQUIRE FIXING") + "\n\n")
        
        f.write("## Feature Validation Results\n")
        f.write("| Feature | Status | Details |\n")
        f.write("| :--- | :--- | :--- |\n")
        
        mapping = {
            "tests/test_signal_core.py": "AI Neural Controller & Constraints",
            "tests/test_v2i_preemption.py": "V2I Digital Beacon & Hub Logic",
            "tests/preemption_trace_test.py": "Context Save/Resume Logic",
            "tests/groq_test.py": "LLM Reasoning & Chat Config"
        }
        
        for test, info in results.items():
            name = mapping.get(test, test)
            status_icon = "PASS" if info["status"] == "PASS" else "FAIL"
            f.write(f"| {name} | {status_icon} {info['status']} | {test} |\n")

    print(f"🏆 Report generated at: {report_path}")
    return results

if __name__ == "__main__":
    run_suite()
