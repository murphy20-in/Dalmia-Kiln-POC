"""Step 6 - Operating-state, load, AFR and Phase 4 context of every candidate episode (CONTEXT, NEVER CAUSE).

Rules (abn_core.add_context / classify, fixed precedence, first match wins):
  STARTUP / RESTART   onset inside [Phase 2 restart, restart + ramp + 6 h]; STARTUP when the stop lasted >= 24 h
  SHUTDOWN            a kiln stop in [start, end + 2 h] that is <= 6 h after the onset
  NORMAL_LOAD_CHANGE  load deviated (|feed change vs 2 h before onset| >= training P90 of the 2-h feed change, or >= 50 %
                      of buckets outside the training feed range, or |kiln speed / clinker robust z| >= 3) AND < 2
                      process families deviated
  AFR_TRANSITION      a Phase 5 AFR_STOP / AFR_RAMP_DOWN in [onset - 3 h, onset + 1 h] AND < 2 families deviated
  CONTROL_ACTION      coal (kiln + PC) step across the onset >= training P90 of the 1-h coal change, feed step <= its
                      training P75, AND < 2 families deviated
The Phase 2 events are retrospective (full-period) and the state is a POC proxy (UNCONFIRMED); AFR and Phase 4 overlaps are
temporal coincidence only. Writes outputs/abnormal_episode_context.csv.
"""
from __future__ import annotations

import numpy as np

from abn_core import load_stage, log, write_csv

lg = log("classify_operating_context")
DEFINITIONAL = {"DATA_QUALITY_ARTIFACT", "SHORT_TRANSIENT", "INSUFFICIENT_DATA"}
PROXY_BASED = {"STARTUP", "RESTART", "SHUTDOWN", "NORMAL_LOAD_CHANGE"}
COINCIDENCE = {"AFR_TRANSITION", "CONTROL_ACTION"}


def context_confidence(primary: str, load_context: str) -> str:
    if primary in DEFINITIONAL:
        return "HIGH (definitional rule on measured data)"
    if primary in PROXY_BASED:
        return "MEDIUM (Phase 2 state proxy / load measurement; state UNCONFIRMED)"
    if primary in COINCIDENCE:
        return "LOW (temporal coincidence with a control input; co-manipulated, not isolable)"
    return ("MEDIUM (no ordinary-transition context matched; load independent)" if load_context == "LOAD_INDEPENDENT"
            else "LOW (no ordinary-transition context matched, but a load contribution cannot be ruled out)")


def main():
    ep = load_stage("episodes")
    out = ep[["episode_id", "reference_state", "startup_overlap", "shutdown_overlap", "restart_overlap",
              "load_change_overlap", "afr_start_overlap", "afr_stop_overlap", "afr_ramp_overlap",
              "phase4_indicator_overlap", "data_quality_overlap"]].copy()
    after = np.where(ep.shutdown_overlap, "; STOP FOLLOWS", "")
    before = np.where(ep.startup_overlap | ep.restart_overlap, "; IN RESTART RAMP + SETTLE", "")
    out["operating_state"] = "RUNNING (POC PROXY - UNCONFIRMED)" + before + after
    out["primary_context"] = ep.primary_context
    out["secondary_context"] = ep.secondary_context
    out["context_confidence"] = [context_confidence(p, lc) for p, lc in zip(ep.primary_context, ep.load_context)]
    for c in ["load_context", "feed_change_vs_pre2h", "feed_z", "speed_z", "clinker_z", "oor_share", "hours_since_restart",
              "stop_follows_within_2h", "afr_context", "afr_near_onset", "afr_episode_ids", "phase4_active_buckets_pre2h",
              "phase4_indicator_context", "coal_step_at_onset", "control_action_overlap", "data_quality_context"]:
        out[c] = ep[c]
    out["interpretation"] = "CONTEXT ONLY - an overlap is a temporal coincidence, not a cause"
    write_csv(out, "abnormal_episode_context.csv", lg)
    lg.info("primary context: %s", ep.primary_context.value_counts().to_dict())


if __name__ == "__main__":
    main()
