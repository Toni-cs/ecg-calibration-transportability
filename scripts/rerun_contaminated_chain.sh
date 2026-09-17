#!/usr/bin/env bash
# Serial rerun of every artifact produced inside the label-encoding contamination
# window (2026-09-09 20:26:34 .. 2026-09-16 20:48:18).
#
# Order is descending manuscript value:
#   E3  full-n Brier/DCR/NCV   -- lets the paper drop the "n=20 subsample" caveat
#   E1a L2 390-cell shift grid -- backs the safety-rate claim (157/390)
#   E2  discrimination table   -- backs the AUROC/AUPRC columns
#   E4  temperature family     -- backs the fitted-T distribution
#   E6  reliability diagrams   -- figures
#   E1b LOCO                   -- exploratory; not cited in the manuscript
#
# Backups of the contaminated originals live next to them as *.bak_contaminated.
# The BiMamba grid was stopped before this chain so the GPU is free.
set -u
cd "$(dirname "$0")/.." || exit 1

PY="C:/python/python.exe"
LOG="logs/rerun_master.log"
mkdir -p logs

stamp() { date +"%Y-%m-%d %H:%M:%S"; }

run() {
  local name="$1"; shift
  printf '\n[%s] START %s\n' "$(stamp)" "$name" | tee -a "$LOG"
  local t0 t1 rc
  t0=$(date +%s)
  "$@" > "logs/rerun_${name}.log" 2>&1
  rc=$?
  t1=$(date +%s)
  printf '[%s] END   %s rc=%s elapsed=%s min\n' "$(stamp)" "$name" "$rc" "$(( (t1 - t0) / 60 ))" | tee -a "$LOG"
  return 0
}

{
  echo "================================================================"
  echo "Contaminated-artifact rerun chain"
  echo "started $(stamp)"
  echo "================================================================"
} | tee -a "$LOG"

run e3_full   "$PY" scripts/run_e3_brier_dcr_ncv.py --regen
run e1a_l2    "$PY" scripts/run_e1a_l2_shift_full.py --force
run e2_disc   "$PY" scripts/run_e2_ablation_discrimination.py --no-cache
run e4_temp   "$PY" scripts/run_e4_temperature_analysis.py
run e6_reliab "$PY" scripts/run_e6_reliability_diagrams.py --all
run e1b_loco  "$PY" scripts/run_e1b_loco_validation.py

printf '\n[%s] CHAIN DONE\n' "$(stamp)" | tee -a "$LOG"
