import argparse
import json
from collections import Counter, defaultdict

from backend.services.results_service import get_decision_logs, get_simulation_results


LANES = ['north', 'east', 'south', 'west']


def summarize_decision_logs(logs):
    total = len(logs)
    lane_counts = Counter()
    strategy_counts = Counter()
    lane_switches = 0
    previous_lane = None
    starvation = {lane: 0 for lane in LANES}
    max_starvation = {lane: 0 for lane in LANES}
    empty_lane_selection_count = 0
    low_confidence_count = 0
    avg_confidences = []
    queue_samples = defaultdict(list)

    for log in logs:
        selected_lane = (log.get('selected_lane') or '').lower()
        strategy = log.get('strategy') or 'unknown'
        debug = log.get('debug') or {}
        snapshot = log.get('snapshot') or {}

        lane_counts[selected_lane] += 1
        strategy_counts[strategy] += 1

        if previous_lane is not None and selected_lane != previous_lane:
            lane_switches += 1
        previous_lane = selected_lane

        if strategy == 'rl_all_empty':
            empty_lane_selection_count += 1

        avg_conf = debug.get('average_confidence')
        if isinstance(avg_conf, (int, float)):
            avg_confidences.append(float(avg_conf))
            if avg_conf < 0.25 or debug.get('confidence_filtered'):
                low_confidence_count += 1

        lane_metrics = debug.get('lane_metrics') or {}
        for lane in LANES:
            if lane == selected_lane:
                starvation[lane] = 0
            else:
                starvation[lane] += 1
                max_starvation[lane] = max(max_starvation[lane], starvation[lane])

            lane_metric = lane_metrics.get(lane) or {}
            if 'vehicle_count' in lane_metric:
                queue_samples[lane].append(float(lane_metric.get('vehicle_count', 0)))

    avg_selected_confidence = sum(avg_confidences) / len(avg_confidences) if avg_confidences else None
    avg_lane_queue = {
        lane: (sum(values) / len(values) if values else 0.0)
        for lane, values in queue_samples.items()
    }

    return {
        'total_decisions': total,
        'lane_selection_counts': dict(lane_counts),
        'strategy_counts': dict(strategy_counts),
        'lane_switches': lane_switches,
        'max_starvation': max_starvation,
        'empty_lane_selection_count': empty_lane_selection_count,
        'low_confidence_count': low_confidence_count,
        'avg_selected_confidence': avg_selected_confidence,
        'avg_lane_queue': avg_lane_queue,
    }


def build_report(session_id):
    results = get_simulation_results(session_id)
    logs = get_decision_logs(session_id)
    metrics = summarize_decision_logs(logs)

    report = {
        'sessionId': session_id,
        'decisionMetrics': metrics,
        'results': results if 'error' not in results else None,
        'resultError': results.get('error') if isinstance(results, dict) else None,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description='Generate prototype session quality report')
    parser.add_argument('--session-id', required=True, help='Session ID to report on')
    parser.add_argument('--json', action='store_true', help='Print report as JSON')
    args = parser.parse_args()

    report = build_report(args.session_id)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    metrics = report['decisionMetrics']
    print(f"Session: {report['sessionId']}")
    print(f"Total decisions: {metrics['total_decisions']}")
    print(f"Lane switches: {metrics['lane_switches']}")
    print(f"Empty-lane selections: {metrics['empty_lane_selection_count']}")
    print(f"Low-confidence ticks: {metrics['low_confidence_count']}")
    print("Max starvation per lane:")
    for lane, value in metrics['max_starvation'].items():
        print(f"  {lane}: {value}")
    print("Strategy counts:")
    for strategy, count in metrics['strategy_counts'].items():
        print(f"  {strategy}: {count}")


if __name__ == '__main__':
    main()