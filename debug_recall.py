"""
debug_recall.py  — Memory recall verification
Run: python debug_recall.py
Purpose: Confirm fresh high-importance lessons surface in top-5 recall
No side effects beyond a test memory that gets cleaned up at the end.
"""
import sys, re, math
from datetime import datetime
sys.path.insert(0, r"C:\Users\fyou1\Desktop\New folder\nexus-ultra")

from nexus_memory_core import MemoryCore

core = MemoryCore()

print("\n=== STEP 1: Store fresh high-importance lesson ===")
mid = core.store(
    "TEST_LESSON: biometric auth dropped, using password+OTP only for hub login",
    importance=9.0,
    tags="auth,biometric,lesson,otp",
    agent="DEBUG_RECALL"
)
print(f"Stored → id={mid}")

# Confirm it's actually in the DB
row = core.conn.execute(
    "SELECT id, importance, created_at FROM memories WHERE id=?", (mid,)
).fetchone()
print(f"DB confirms: id={row[0]}, importance={row[1]}, created_at={row[2]}")

# Check fromisoformat works on this timestamp format
try:
    age_h = (datetime.utcnow() - datetime.fromisoformat(str(row[2])[:26])).total_seconds() / 3600
    print(f"Age: {age_h:.3f} hours — recency_boost will be {'3.0 (24h window OK)' if age_h < 24 else '0.0 (too old)'}")
except Exception as e:
    print(f"ERROR parsing created_at: {e}  <-- THIS IS THE BUG")

print("\n=== STEP 2: Recall with matching query ===")
hits = core.recall("biometric auth login method", top_k=5)
print(f"Returned {len(hits)} results:")
for i, h in enumerate(hits, 1):
    marker = " <-- TARGET" if h["id"] == mid else ""
    print(f"  {i}. id={h['id']} imp={h['importance']} | {h['content'][:70]}{marker}")

target_found = any(h["id"] == mid for h in hits)
print(f"\nLesson in top-5: {'YES — PASS' if target_found else 'NO — FAIL'}")

print("\n=== STEP 3: Check injection string ===")
injection = core.build_injection("biometric auth login method")
print(f"Injection contains lesson: {'YES' if 'biometric' in injection.lower() or 'TEST_LESSON' in injection else 'NO'}")
print(f"Injection preview:\n{injection[:300]}")

print("\n=== CLEANUP: removing test memory ===")
core.conn.execute("DELETE FROM memories WHERE agent='DEBUG_RECALL'")
core.conn.commit()
core.close()
print("Done — test memory removed.\n")
