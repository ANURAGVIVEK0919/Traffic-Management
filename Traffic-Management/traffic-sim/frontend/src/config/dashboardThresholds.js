export const DASHBOARD_THRESHOLDS = {
  starvationTick: 8,
  sameLaneLock: 6,
  lowUtilizationPct: 55,
  highAvgWaitSec: 18,
  highAmbulanceWaitSec: 12,
};

export const DASHBOARD_THRESHOLD_PRESETS = {
  conservative: {
    starvationTick: 6,
    sameLaneLock: 5,
    lowUtilizationPct: 65,
    highAvgWaitSec: 14,
    highAmbulanceWaitSec: 10,
  },
  balanced: {
    starvationTick: 8,
    sameLaneLock: 6,
    lowUtilizationPct: 55,
    highAvgWaitSec: 18,
    highAmbulanceWaitSec: 12,
  },
  aggressive: {
    starvationTick: 10,
    sameLaneLock: 8,
    lowUtilizationPct: 45,
    highAvgWaitSec: 24,
    highAmbulanceWaitSec: 16,
  },
};
