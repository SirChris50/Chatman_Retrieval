import os, sys, traceback, time

log = open("C:/Temp/probe_onnx.txt", "w")
log.write(f"start {time.time()}\n"); log.flush()

try:
    from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
    log.write("imported ONNXMiniLM_L6_V2\n"); log.flush()
    ef = ONNXMiniLM_L6_V2()
    log.write("created ef\n"); log.flush()
    result = ef(["hello world"])
    log.write(f"embed ok, dim={len(result[0])}\n"); log.flush()
except Exception as e:
    log.write(f"EXCEPTION: {e}\n")
    traceback.print_exc(file=log)
finally:
    log.flush()
    log.close()

print("done", flush=True)
