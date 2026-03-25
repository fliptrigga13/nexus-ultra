"""
VeilPiercer Python SDK
======================
Submit tasks to your VeilPiercer swarm and retrieve results.

Usage:
    from veilpiercer import VeilPiercer
    vp = VeilPiercer(token="YOUR_TOKEN", hub="https://veil-piercer.com")
    result = vp.submit_task("Research my top 3 competitors")
    print(result)

Requirements: requests (pip install requests)
"""

import time
try:
    import requests
except ImportError:
    raise ImportError("Install requests: pip install requests")


class VeilPiercer:
    def __init__(self, token: str, hub: str = "https://veil-piercer.com"):
        self.token = token
        self.hub = hub.rstrip("/")
        self._verify_token()

    def _verify_token(self):
        try:
            r = requests.get(f"{self.hub}/access/verify?token={self.token}", timeout=10)
            data = r.json()
            if not data.get("ok"):
                raise ValueError(f"Invalid token: {data.get('error', 'unknown error')}")
            self.email = data.get("email", "")
            self.tier = data.get("tier", "Starter")
            print(f"[VeilPiercer] Connected — {self.email} ({self.tier})")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Cannot reach VeilPiercer hub at {self.hub}")

    def submit_task(self, task: str, context: str = "", poll: bool = True, timeout: int = 300) -> str:
        """Submit a task to the swarm. Returns the output string."""
        r = requests.post(
            f"{self.hub}/api/customer-task",
            json={"token": self.token, "task": task, "context": context},
            timeout=15
        )
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Task submission failed: {data.get('error')}")

        task_id = data.get("task_id")
        eta = data.get("eta_minutes", 5)
        print(f"[VeilPiercer] Task queued (id={task_id}, eta~{eta}min)")

        if not poll or not task_id:
            return task_id  # Return task_id for manual polling

        # Poll for result
        start = time.time()
        while time.time() - start < timeout:
            time.sleep(10)
            try:
                r = requests.get(
                    f"{self.hub}/api/customer-task/{task_id}?token={self.token}",
                    timeout=10
                )
                result = r.json()
                if result.get("status") == "complete":
                    return result.get("output", "")
            except Exception:
                pass

        raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")

    def get_memories(self, limit: int = 20) -> list:
        """Retrieve recent swarm memories."""
        r = requests.get(
            f"{self.hub}/api/memories?token={self.token}&limit={limit}",
            timeout=10
        )
        return r.json().get("memories", [])

    def get_cycle_stats(self) -> dict:
        """Get current swarm cycle statistics."""
        r = requests.get(f"{self.hub}/api/status", timeout=10)
        return r.json()


if __name__ == "__main__":
    import sys
    token = input("Enter your VeilPiercer token: ").strip()
    vp = VeilPiercer(token=token)
    task = input("Enter task for the swarm: ").strip()
    print("\n[VeilPiercer] Submitting task...")
    result = vp.submit_task(task)
    print(f"\n[RESULT]\n{result}")
