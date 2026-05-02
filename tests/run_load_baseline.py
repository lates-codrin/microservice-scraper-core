import json
import subprocess
import sys
import time


def run_baseline():
    print("Starting uvicorn server...")
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8081"])
    time.sleep(3)

    print("Running locust load test...")
    cmd = [
        "locust",
        "-f",
        "tests/load/locustfile.py",
        "--headless",
        "-u",
        "10",
        "-r",
        "10",
        "--run-time",
        "60s",
        "--host",
        "http://127.0.0.1:8081",
        "--csv",
        "tests/load/locust_stats",
    ]
    subprocess.run(cmd)

    server.terminate()
    server.wait()

    # Read CSV and assert
    import csv

    baseline = {}
    with open("tests/load/locust_stats_stats.csv") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Name"]
            if name == "Aggregated":
                continue
            p95 = float(row.get("95%", 0))
            baseline[name] = {"p95": p95}
            if name == "/v1/jobs/{job_id}" and "documents" not in name:
                assert p95 < 200, f"Job poll p95={p95} exceeds 200ms"
            elif "/documents" in name:
                assert p95 < 500, f"Documents page p95={p95} exceeds 500ms"

    with open("tests/load/baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)

    print("Baseline test passed and saved to tests/load/baseline.json")


if __name__ == "__main__":
    run_baseline()
