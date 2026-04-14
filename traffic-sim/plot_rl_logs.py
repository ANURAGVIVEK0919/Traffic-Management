import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def load_rows(csv_path):
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(
                {
                    "timestep": int(row.get("timestep", 0)),
                    "reward": float(row.get("reward", 0.0)),
                    "loss": float(row.get("loss", 0.0)),
                    "epsilon": float(row.get("epsilon", 0.0)),
                    "action": int(row.get("action", 0)),
                }
            )
    return rows


def plot_metrics(rows):
    timesteps = [row["timestep"] for row in rows]
    rewards = [row["reward"] for row in rows]
    losses = [row["loss"] for row in rows]
    epsilons = [row["epsilon"] for row in rows]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    axes[0].plot(timesteps, rewards, color="tab:blue", linewidth=1.6)
    axes[0].set_ylabel("Reward")
    axes[0].set_title("Reward vs Time")
    axes[0].grid(True, linestyle="--", alpha=0.35)

    axes[1].plot(timesteps, losses, color="tab:red", linewidth=1.6)
    axes[1].set_ylabel("Loss")
    axes[1].set_title("Loss vs Time")
    axes[1].grid(True, linestyle="--", alpha=0.35)

    axes[2].plot(timesteps, epsilons, color="tab:green", linewidth=1.6)
    axes[2].set_ylabel("Epsilon")
    axes[2].set_xlabel("Timestep")
    axes[2].set_title("Epsilon Decay")
    axes[2].grid(True, linestyle="--", alpha=0.35)

    plt.tight_layout()
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Plot RL training metrics from rl_logs.csv")
    parser.add_argument(
        "--csv",
        default="models/rl_logs.csv",
        help="Path to rl log CSV file (default: models/rl_logs.csv)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(f"RL log file not found: {csv_path}")

    rows = load_rows(csv_path)
    if not rows:
        raise RuntimeError(f"No rows found in RL log file: {csv_path}")

    plot_metrics(rows)


if __name__ == "__main__":
    main()
