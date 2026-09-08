@echo off
cd /d D:\A1\ecg-lab-v2
python scripts/eval_transfer.py --source ptbxl --source-dir data/ptbxl_processed --target chapman --target-dir data/chapman_processed_v2 --arch inceptiontime --d-model 32 --batch-size 16 --seeds 43 --epochs 50 --bootstrap 2000 --methods ts platt --num-workers 4 --gpu-inference > s1_final_seed43.log 2>&1