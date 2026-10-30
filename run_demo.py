"""Prepare the local demo and start the FastAPI backend."""
from pathlib import Path
import subprocess, sys

ROOT = Path(__file__).resolve().parent

def run(module):
    subprocess.run([sys.executable, "-m", module], cwd=ROOT, check=True)

if __name__ == "__main__":
    traffic = ROOT / "data" / "traffic.csv"
    model = ROOT / "ml" / "isolation_forest.joblib"
    if not traffic.exists():
        run("data.generate_synthetic_traffic")
    if not model.exists():
        run("ml.train_model")
    print("Backend: http://127.0.0.1:8000")
    print("Dashboard: open dashboard/index.html")
    subprocess.run([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, check=True)
