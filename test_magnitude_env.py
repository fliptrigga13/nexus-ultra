import redis
import psutil
import pynvml
import time
import sys

# Set stdout to utf-8 if possible
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_magnitude_env():
    print("--- MAGNITUDE ENVIRONMENT TEST ---")
    
    # 1. Redis
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.set('test_key', 'test_value')
        if r.get('test_key') == 'test_value':
            print("[OK] Redis: CONNECTED & WRITABLE")
        else:
            print("[FAIL] Redis: Read/Write mismatch")
    except Exception as e:
        print(f"[FAIL] Redis: FAILED - {e}")

    # 2. psutil
    try:
        mem = psutil.virtual_memory()
        print(f"[OK] RAM: {mem.percent}% used ({mem.used // 10**6}MB)")
    except Exception as e:
        print(f"[FAIL] psutil: FAILED - {e}")

    # 3. pynvml
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        print(f"[OK] GPU: {pynvml.nvmlDeviceGetName(handle)}")
        print(f"[OK] VRAM: {info.used // 10**6}MB / {info.total // 10**6}MB used")
        print(f"[OK] GPU Load: {util.gpu}%")
        pynvml.nvmlShutdown()
    except Exception as e:
        print(f"[FAIL] pynvml: FAILED - {e}")

if __name__ == "__main__":
    test_magnitude_env()
