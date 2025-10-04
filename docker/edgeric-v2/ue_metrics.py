#!/usr/bin/env python3
"""
Improved muApp3_monitor_terminal.py
- Logs UE metrics per TTI to a CSV file
- Prints clean, minimal status updates
- Exits cleanly on Ctrl+C
"""

import csv
import os
import sys
import time
from datetime import datetime
from edgeric_messenger import EdgericMessenger
# Initialize EdgericMessenger
edgeric_messenger = EdgericMessenger(socket_type="None")

# Create a timestamped log file
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"ue_metrics_{timestamp}.csv"

# Ensure directory
os.makedirs("logs", exist_ok=True)
filepath = os.path.join("logs", filename)

# CSV fieldnames (per TTI per UE)
FIELDS = [
    "tti_count", "rnti", "cqi", "snr",
    "tx_bytes", "rx_bytes", "dl_buffer",
    "ul_buffer", "dl_tbs", "ul_harq_ack"
]

def main():
    print(f"Starting UE Metrics Monitor...")
    print(f"Saving metrics to {filepath}")
    print("Press Ctrl+C to stop.\n")

    with open(filepath, mode="w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDS)
        writer.writeheader()

        try:
            while True:
                tti_count, ue_data = edgeric_messenger.get_metrics(flag_print=False)

                # Log each UE's data
                for rnti, metrics in ue_data.items():
                    row = {"tti_count": tti_count, "rnti": rnti, **metrics}
                    writer.writerow(row)

                # Print progress every 500 TTIs
                if tti_count % 500 == 0:
                    print(f"[TTI {tti_count}] Logged metrics for {len(ue_data)} UEs")

        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Exiting gracefully...")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            print(f"Data saved to {filepath}")

if __name__ == "__main__":
    main()
