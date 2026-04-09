import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

import time

with open("C:/Temp/probe.txt", "w") as f:
    f.write(f"start {time.time()}\n")
    f.flush()

print("pre-torch", flush=True)

import torch

with open("C:/Temp/probe.txt", "a") as f:
    f.write(f"torch ok {torch.__version__} {time.time()}\n")

print("torch", torch.__version__, flush=True)
