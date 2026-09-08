import sys, time
print("bg test start", flush=True)
print(f"python: {sys.executable}", flush=True)
try:
    import torch
    print(f"torch: {torch.__version__}, cuda: {torch.cuda.is_available()}", flush=True)
    if torch.cuda.is_available():
        x = torch.randn(10, 10).cuda()
        print(f"cuda tensor ok: {x.sum().item():.4f}", flush=True)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}", flush=True)
time.sleep(30)
print("bg test end", flush=True)