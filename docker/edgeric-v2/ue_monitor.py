import os
import time
import glob
import pandas as pd
import redis
from datetime import datetime

def get_latest_algorithm_folder(base_path="logs"):
    """Return the most recently modified algorithm folder."""
    try:
        algo_folders = [os.path.join(base_path, d) for d in os.listdir(base_path)
                        if os.path.isdir(os.path.join(base_path, d))]
        if not algo_folders:
            return None
        latest_algo = max(algo_folders, key=os.path.getmtime)
        return latest_algo
    except Exception as e:
        print(f"Error finding latest algorithm folder: {e}")
        return None

def get_algorithm_name_from_redis():
    """Fetch the current scheduling algorithm from Redis."""
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        algo = r.get("scheduling_algorithm")
        if algo:
            return algo.decode("utf-8")
    except Exception:
        pass
    return "Unknown Algorithm"

def get_latest_csvs(algo_folder):
    """Get the latest timestamped CSVs for all UEs."""
    ue_files = sorted(glob.glob(os.path.join(algo_folder, "UE_*.csv")))
    if not ue_files:
        return []
    # group by UE ID prefix (since multiple timestamps might exist)
    latest_files = {}
    for file in ue_files:
        fname = os.path.basename(file)
        parts = fname.split("_")
        if len(parts) >= 3:
            rnti = parts[1]
            if rnti not in latest_files or os.path.getmtime(file) > os.path.getmtime(latest_files[rnti]):
                latest_files[rnti] = file
    return list(latest_files.values())

def read_latest_metrics(csv_path):
    """Read the last line from a UE CSV to show the most recent metrics."""
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return None
        latest = df.iloc[-1]
        return {
            "time": int(latest["time"]),
            "tti": int(latest["tti"]),
            "cqi": latest["cqi"],
            "snr": latest["snr"],
            "Z": latest["Z"],
            "instantaneous_aoi": latest["instantaneous_aoi"],
            "average_aoi": latest["average_aoi"],
            "measured_throughput": latest["measured_throughput"],
            "ptx": latest["ptx"],
            "sigma2": latest["sigma2"]
        }
    except Exception:
        return None

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def live_monitor(refresh_interval=1.0):
    """Continuously display live metrics for all UEs."""
    base_dir = "logs"
    latest_algo_path = get_latest_algorithm_folder(base_dir)
    if not latest_algo_path:
        print("No logs found yet. Run ue_metrics.py first.")
        return

    algo_name = os.path.basename(latest_algo_path)
    redis_algo = get_algorithm_name_from_redis()
    print(f"Monitoring latest algorithm folder: {algo_name}")
    print(f"Redis-reported algorithm: {redis_algo}")
    print("Press Ctrl+C to stop.\n")

    latest_csvs = get_latest_csvs(latest_algo_path)
    if not latest_csvs:
        print("No UE CSV files found.")
        return

    try:
        while True:
            clear_screen()
            print(f"=== LIVE UE METRICS MONITOR ===   ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            print(f"Algorithm Folder: {algo_name}")
            print(f"Redis Algorithm: {redis_algo}")
            print("-" * 90)
            print(f"{'UE ID':<10} {'Time':<6} {'TTI':<8} {'CQI':<5} {'SNR(dB)':<9} "
                  f"{'AoI':<6} {'AvgAoI':<8} {'Thrpt':<8} {'PTX':<6} {'σ²(Z)':<10}")
            print("-" * 90)

            for file in sorted(latest_csvs):
                ue_id = os.path.basename(file).split("_")[1]
                metrics = read_latest_metrics(file)
                if metrics:
                    print(f"{ue_id:<10} {metrics['time']:<6} {metrics['tti']:<8} "
                          f"{metrics['cqi']:<5} {metrics['snr']:<9.2f} "
                          f"{metrics['instantaneous_aoi']:<6} {metrics['average_aoi']:<8.2f} "
                          f"{metrics['measured_throughput']:<8.3f} {metrics['ptx']:<6.3f} "
                          f"{metrics['sigma2']:<10.6f}")
                else:
                    print(f"{ue_id:<10} --- No data yet ---")

            print("\nUpdating every {:.1f}s... (Ctrl+C to stop)".format(refresh_interval))
            time.sleep(refresh_interval)

    except KeyboardInterrupt:
        clear_screen()
        print("Stopped live monitoring.")


if __name__ == "__main__":
    live_monitor(refresh_interval=1.0)
