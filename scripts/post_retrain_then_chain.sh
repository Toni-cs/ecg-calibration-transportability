#!/usr/bin/env bash
# After the cpsc_ptbxl/inceptiontime/seed{42,43} retrain lands, verify model
# independence, rebuild the 60-cell main table, and restart the
# contaminated-artifact rerun chain. Unattended.
#
# Why this exists: the retrain has to finish before anything downstream can run
# (the GPU is single-tenant and every downstream step reads those checkpoints),
# and the retrain takes ~30 min. This wrapper removes the idle gap.
set -u
cd "$(dirname "$0")/.." || exit 1

PY="C:/python/python.exe"
LOG="logs/post_retrain_master.log"
mkdir -p logs
stamp() { date +"%Y-%m-%d %H:%M:%S"; }

S42="checkpoints/transfer/cpsc_ptbxl/inceptiontime/seed42/transfer_result.json"
S43="checkpoints/transfer/cpsc_ptbxl/inceptiontime/seed43/transfer_result.json"
REF="checkpoints/transfer/cpsc_chapman/inceptiontime/seed42/best_model.pt"

log() { printf '[%s] %s\n' "$(stamp)" "$*" | tee -a "$LOG"; }

log "waiting for retrain to land (seed42 + seed43 transfer_result.json)"

# --- 1) wait, with a hard timeout so a failed retrain cannot hang forever ---
DEADLINE=$(( $(date +%s) + 3600 ))
while { [ ! -f "$S42" ] || [ ! -f "$S43" ]; }; do
  if [ "$(date +%s)" -gt "$DEADLINE" ]; then
    log "TIMEOUT after 60 min -- aborting, chain NOT started"
    exit 1
  fi
  sleep 30
done
log "retrain landed"

# --- 2) independence check: the new files must differ from the chapman side ---
for s in 42 43; do
  new_md5=$(md5sum "checkpoints/transfer/cpsc_ptbxl/inceptiontime/seed$s/best_model.pt" | cut -c1-12)
  ref_md5=$(md5sum "checkpoints/transfer/cpsc_chapman/inceptiontime/seed$s/best_model.pt" | cut -c1-12)
  if [ "$new_md5" = "$ref_md5" ]; then
    log "FAIL seed$s still identical to chapman side ($new_md5) -- aborting"
    exit 1
  fi
  log "OK   seed$s new=$new_md5  chapman=$ref_md5  (independent)"
done

# --- 3) rebuild the 60-cell main table ---
log "rebuilding main table via generate_robustness_report_v2.py"
"$PY" generate_robustness_report_v2.py > "logs/post_retrain_main_table.log" 2>&1
log "main table rc=$?"

# --- 4) restart the contaminated-artifact rerun chain ---
log "starting rerun chain"
bash scripts/rerun_contaminated_chain.sh
log "chain finished"
