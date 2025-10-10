import json
import os
import time
import redis
import csv
import statistics  # NEW
from datetime import datetime
from edgeric_messenger import EdgericMessenger

edgeric_messenger = EdgericMessenger(socket_type="None")

def get_algorithm_name():
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        algo = r.get("scheduling_algorithm")
        if algo:
            return algo.decode("utf-8").replace(" ", "_")
        else:
            return "Unknown_Algorithm"
    except Exception as e:
        print(f"Warning: Could not read scheduling algorithm from Redis: {e}")
        return "Unknown_Algorithm"

# Determine current algorithm and timestamp
algo_name = get_algorithm_name()
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

base_dir = os.path.join("logs", algo_name)
charts_dir = os.path.join(base_dir, "charts")
os.makedirs(charts_dir, exist_ok=True)

filepath = os.path.join(base_dir, f"ue_metrics_{timestamp}.json")

ue_history = {}
full_log = {}
csv_files = {}
start_time_index = 1  # NEW


def write_to_csv(rnti, tti, metrics, time_index):  # NEW arg
    """Append per-UE metrics to its CSV log."""
    csv_path = csv_files[rnti]["path"]
    writer = csv_files[rnti]["writer"]

    writer.writerow({
        "time": time_index,  # NEW
        "tti": tti,
        "cqi": metrics.get("cqi", 0),
        "snr": metrics.get("snr", 0),
        "tx_bytes": metrics.get("tx_bytes", 0),
        "rx_bytes": metrics.get("rx_bytes", 0),
        "ul_buffer": metrics.get("ul_buffer", 0),
        "ul_harq_ack": metrics.get("ul_harq_ack", False),
        "ul_tx_attempt": metrics.get("ul_tx_attempt", 0),
        "Z": metrics.get("Z", 0),  # NEW
        "instantaneous_aoi": metrics.get("instantaneous_aoi", 0),
        "average_aoi": metrics.get("average_aoi", 0),
        "measured_throughput": metrics.get("measured_throughput", 0),  # RENAMED
        "ptx": metrics.get("ptx", 0),
        "sigma2": metrics.get("sigma2", 0)  # NEW
    })


def create_csv_for_ue(rnti):
    """Initialize a CSV file for a new UE."""
    ue_filename = f"UE_{rnti}_{timestamp}.csv"
    csv_path = os.path.join(base_dir, ue_filename)
    csv_file = open(csv_path, "w", newline="")
    fieldnames = [
        "time", "tti", "cqi", "snr", "tx_bytes", "rx_bytes",
        "ul_buffer", "ul_harq_ack", "ul_tx_attempt", "Z",  # NEW
        "instantaneous_aoi", "average_aoi",
        "measured_throughput", "ptx", "sigma2"  # UPDATED
    ]
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    csv_files[rnti] = {"file": csv_file, "writer": writer, "path": csv_path}


def main():
    print(f"Starting Enhanced UE Metrics Monitor...")
    print(f"Scheduling Algorithm: {algo_name}")
    print(f"Saving metrics to {base_dir}/UE_<rnti>_{timestamp}.csv")
    print("Press Ctrl+C to stop.\n")

    global start_time_index

    try:
        while True:
            tti_count, ue_data = edgeric_messenger.get_metrics(flag_print=False)
            snapshot = {"tti": tti_count, "ues": {}}

            for rnti, metrics in ue_data.items():
                if rnti not in ue_history:
                    ue_history[rnti] = {
                        "instantaneous_aoi": 1,
                        "average_aoi": 1.0,
                        "total_acks": 0,
                        "total_tx": 0,
                        "tti_seen": 0,
                        "sum_aoi": 0.0,
                        "Z_values": []  # NEW: for variance computation
                    }
                    create_csv_for_ue(rnti)

                hist = ue_history[rnti]
                hist["tti_seen"] += 1

                harq_ack = metrics.get("ul_harq_ack", False)
                tx_attempt = metrics.get("ul_tx_attempt", 0)
                hist["total_tx"] += tx_attempt

                # Compute Z
                Z = 1 if harq_ack and tx_attempt else 0
                hist["Z_values"].append(Z)  # record for variance
                sigma2 = statistics.pvariance(hist["Z_values"]) if len(hist["Z_values"]) > 1 else 0  # NEW

                # AoI calculation
                if harq_ack:
                    hist["instantaneous_aoi"] = 1
                    hist["total_acks"] += 1
                else:
                    hist["instantaneous_aoi"] += 1

                hist["sum_aoi"] += hist["instantaneous_aoi"]
                hist["average_aoi"] = hist["sum_aoi"] / hist["tti_seen"]

                measured_throughput = hist["total_acks"] / hist["tti_seen"] if hist["tti_seen"] > 0 else 0
                ptx = hist["total_acks"] / hist["total_tx"] if hist["total_tx"] > 0 else 0

                enriched_metrics = {
                    **metrics,
                    "Z": Z,
                    "instantaneous_aoi": hist["instantaneous_aoi"],
                    "average_aoi": round(hist["average_aoi"], 4),
                    "measured_throughput": round(measured_throughput, 4),  # RENAMED
                    "ptx": round(ptx, 4),
                    "sigma2": round(sigma2, 6)  # NEW
                }

                snapshot["ues"][rnti] = enriched_metrics
                write_to_csv(rnti, tti_count, enriched_metrics, hist["tti_seen"])  # UPDATED

            full_log[tti_count] = snapshot

            if tti_count % 100 == 0:
                with open(filepath, "w") as f:
                    json.dump(list(full_log.values()), f, indent=2)
                print(f"[TTI {tti_count}] Logged metrics for {len(ue_data)} UEs")

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\nInterrupted. Closing files and saving JSON...")
        for rnti, file_info in csv_files.items():
            file_info["file"].close()
        with open(filepath, "w") as f:
            json.dump(list(full_log.values()), f, indent=2)
        print(f"All logs saved in {base_dir}/")


if __name__ == "__main__":
    main()
