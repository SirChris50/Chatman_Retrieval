import os, sys, traceback, time

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"

log = open("C:/Temp/probe2.txt", "w")
log.write(f"start {time.time()}\n"); log.flush()

try:
    import torch
    log.write(f"torch ok {torch.__version__}\n")
except Exception as e:
    log.write(f"EXCEPTION: {e}\n")
    traceback.print_exc(file=log)
finally:
    log.flush()
    log.close()
