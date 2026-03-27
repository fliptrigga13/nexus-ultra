"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  NEXUS MODEL ROUTER — 3-Tier Cascade Intelligence                            ║
║                                                                              ║
║  Tier 1 (FAST)     → deepseek-r1:8b   — classification, routing, edits      ║
║  Tier 2 (STANDARD) → deepseek-r1:14b  — main reasoning, CRITIC evaluation   ║
║  Tier 3 (CRITICAL) → Gemini Flash     — ESCALATE cases, final arbitration   ║
║                                                                              ║
║  Auto-detection:                                                             ║
║    - Short prompts / classification → Tier 1                                ║
║    - Standard agent reasoning       → Tier 2                                ║
║    - ESCALATE signals / Tier-3 bench → Tier 3                               ║
║                                                                              ║
║  Cascade: if Tier 3 rate-limits → falls back to Tier 2. Never fails silent. ║
║                                                                              ║
║  Usage:                                                                      ║
║    from nexus_model_router import router                                     ║
║    result = await router.call(system, user, tier=2)                          ║
║    result = await router.call(system, user)  # auto-detect                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

BASE_DIR    = Path(__file__).parent
ROUTER_LOG  = BASE_DIR / "nexus_router_log.json"
ROUTER_STAT = BASE_DIR / "nexus_router_stats.json"

log = logging.getLogger("ROUTER")
log.setLevel(logging.INFO)
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s [ROUTER] %(message)s"))
    log.addHandler(h)

# ══════════════════════════════════════════════════════════════════════════════
# MODEL CONFIGS
# ══════════════════════════════════════════════════════════════════════════════

OLLAMA_BASE = "http://127.0.0.1:11434"

MODELS = {
    1: {
        "name":        "deepseek-r1:8b",
        "provider":    "ollama",
        "temp":        0.3,
        "max_tokens":  150,
        "description": "Fast: classification, routing, short edits — R1 reasoning even in small form",
        "cost_weight": 0.1,
    },
    2: {
        "name":        "deepseek-r1:14b",
        "provider":    "ollama",
        "temp":        0.7,
        "max_tokens":  600,
        "description": "Standard: deep agent reasoning, CRITIC evaluation — R1 chain-of-thought",
        "cost_weight": 0.5,
    },
    3: {
        "name":        "gemini-2.5-flash",
        "provider":    "gemini",
        "temp":        0.4,
        "max_tokens":  600,
        "description": "Critical: ESCALATE arbitration, Tier-3 benchmarks",
        "cost_weight": 1.0,
    },
}

# Auto-detect signals → Tier 3 escalation
TIER3_KEYWORDS = [
    "escalate", "critical failure", "hallucination", "fabricated",
    "final decision", "arbitrate", "override", "tier-3",
]

# Auto-detect signals → Tier 1 (fast path)
TIER1_KEYWORDS = [
    "classify", "route", "tag", "label", "category",
    "yes or no", "true or false", "one word",
]

# ══════════════════════════════════════════════════════════════════════════════
# STATS TRACKER
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RouterStats:
    tier_calls:   dict = field(default_factory=lambda: {1: 0, 2: 0, 3: 0})
    tier_errors:  dict = field(default_factory=lambda: {1: 0, 2: 0, 3: 0})
    fallbacks:    int  = 0
    total_calls:  int  = 0
    cost_saved:   float = 0.0   # relative to always using Tier 3
    last_updated: str  = ""

    def record(self, tier: int, fallback: bool = False):
        self.tier_calls[tier] = self.tier_calls.get(tier, 0) + 1
        self.total_calls += 1
        if fallback:
            self.fallbacks += 1
        # Cost saved vs always using Tier 3
        self.cost_saved += MODELS[3]["cost_weight"] - MODELS[tier]["cost_weight"]
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def record_error(self, tier: int):
        self.tier_errors[tier] = self.tier_errors.get(tier, 0) + 1

    def to_dict(self) -> dict:
        return {
            "tier_calls":   self.tier_calls,
            "tier_errors":  self.tier_errors,
            "fallbacks":    self.fallbacks,
            "total_calls":  self.total_calls,
            "cost_saved":   round(self.cost_saved, 3),
            "last_updated": self.last_updated,
            "tier_distribution": {
                k: f"{round(v/max(self.total_calls,1)*100)}%"
                for k, v in self.tier_calls.items()
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
# MODEL ROUTER
# ══════════════════════════════════════════════════════════════════════════════

class ModelRouter:
    """
    3-tier model router with automatic cascade fallback.

    Usage:
        router = ModelRouter()
        text = await router.call(system_prompt, user_prompt, tier=2)
        text = await router.call(system_prompt, user_prompt)  # auto-detect
        text = await router.call_critic(system_prompt, user_prompt)  # always Tier 2
        text = await router.call_agent(system_prompt, user_prompt)   # Tier 2, cascade to 3
        text = await router.call_fast(system_prompt, user_prompt)    # always Tier 1
    """

    def __init__(self):
        self.stats = RouterStats()
        self._load_stats()
        log.info("✅ ModelRouter online — 3 tiers active")
        log.info(f"   T1={MODELS[1]['name']} | T2={MODELS[2]['name']} | T3={MODELS[3]['name']}")

    def _load_stats(self):
        if ROUTER_STAT.exists():
            try:
                d = json.loads(ROUTER_STAT.read_text(encoding="utf-8"))
                self.stats.tier_calls   = {int(k): v for k, v in d.get("tier_calls", {}).items()}
                self.stats.tier_errors  = {int(k): v for k, v in d.get("tier_errors", {}).items()}
                self.stats.fallbacks    = d.get("fallbacks", 0)
                self.stats.total_calls  = d.get("total_calls", 0)
                self.stats.cost_saved   = d.get("cost_saved", 0.0)
            except Exception:
                pass

    def _save_stats(self):
        ROUTER_STAT.write_text(
            json.dumps(self.stats.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def auto_detect_tier(self, system: str, user: str) -> int:
        """Detect appropriate tier from prompt content."""
        combined = (system + " " + user).lower()

        # Tier 3: critical signals
        if any(kw in combined for kw in TIER3_KEYWORDS):
            return 3

        # Tier 1: fast-path signals OR very short prompts
        if any(kw in combined for kw in TIER1_KEYWORDS):
            return 1
        if len(user) < 80:
            return 1

        # Default: Tier 2
        return 2

    # ── OLLAMA CALL ─────────────────────────────────────────────────────────

    async def _ollama_call(self, model: str, system: str, user: str,
                           max_tokens: int, temp: float) -> str:
        async with httpx.AsyncClient(timeout=90.0) as client:
            r = await client.post(f"{OLLAMA_BASE}/api/chat", json={
                "model":   model,
                "stream":  False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "options": {"num_predict": max_tokens, "temperature": temp},
            })
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "").strip()

    # ── GEMINI CALL ─────────────────────────────────────────────────────────

    async def _gemini_call(self, system: str, user: str, max_tokens: int) -> str:
        from nexus_gemini import gemini_call
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: gemini_call(system, user, max_tokens)
        )

    # ── CORE CALL ───────────────────────────────────────────────────────────

    async def call(
        self,
        system:     str,
        user:       str,
        tier:       Optional[int] = None,
        max_tokens: Optional[int] = None,
        fallback:   bool = True,
    ) -> str:
        """
        Route call to appropriate model tier.

        Args:
            system:     System prompt
            user:       User prompt
            tier:       1=fast, 2=standard, 3=critical. None=auto-detect.
            max_tokens: Override token limit
            fallback:   If Tier 3 fails, fall back to Tier 2 (default True)
        """
        if tier is None:
            tier = self.auto_detect_tier(system, user)

        model_cfg  = MODELS[tier]
        tokens     = max_tokens or model_cfg["max_tokens"]
        t_start    = time.time()
        used_tier  = tier
        is_fallback = False

        log.debug(f"  → Tier {tier} [{model_cfg['name']}] | {len(user)} chars")

        try:
            if model_cfg["provider"] == "ollama":
                result = await self._ollama_call(
                    model_cfg["name"], system, user, tokens, model_cfg["temp"]
                )
            else:
                result = await self._gemini_call(system, user, tokens)

        except Exception as e:
            self.stats.record_error(tier)
            err_str = str(e)

            # Gemini rate-limit → cascade to Tier 2
            if tier == 3 and fallback and ("429" in err_str or "quota" in err_str.lower()):
                log.warning(f"  ⚠️  Tier 3 rate-limited → falling back to Tier 2")
                is_fallback = True
                used_tier   = 2
                model_cfg   = MODELS[2]
                tokens      = max_tokens or model_cfg["max_tokens"]
                try:
                    result = await self._ollama_call(
                        model_cfg["name"], system, user, tokens, model_cfg["temp"]
                    )
                except Exception as e2:
                    log.error(f"  ❌ Tier 2 fallback failed: {e2}")
                    return f"[ROUTER_ERROR: {e2}]"

            # Ollama unavailable → try Gemini if available
            elif tier <= 2 and fallback:
                log.warning(f"  ⚠️  Tier {tier} failed → trying Tier 3 | {e}")
                is_fallback = True
                used_tier   = 3
                try:
                    result = await self._gemini_call(system, user, tokens)
                except Exception as e3:
                    log.error(f"  ❌ All tiers failed: {e3}")
                    return f"[ROUTER_ERROR: all tiers failed]"
            else:
                return f"[ROUTER_ERROR: {e}]"

        latency = int((time.time() - t_start) * 1000)
        self.stats.record(used_tier, fallback=is_fallback)
        if self.stats.total_calls % 10 == 0:
            self._save_stats()

        log.debug(f"  ✓ Tier {used_tier} | {latency}ms | {len(result)} chars")
        return result

    # ── CONVENIENCE METHODS ─────────────────────────────────────────────────

    async def call_fast(self, system: str, user: str, max_tokens: int = 100) -> str:
        """Tier 1 — deepseek-r1:8b. Classification, routing, simple edits."""
        return await self.call(system, user, tier=1, max_tokens=max_tokens)

    async def call_agent(self, system: str, user: str, max_tokens: int = 600) -> str:
        """Tier 2 — deepseek-r1:14b. Main agent reasoning. Escalates to Gemini if needed."""
        return await self.call(system, user, tier=2, max_tokens=max_tokens)

    async def call_critic(self, system: str, user: str, max_tokens: int = 150) -> str:
        """Tier 2 — deepseek-r1:14b, temp=0.3. Strict CRITIC evaluation. No Gemini."""
        cfg = MODELS[2]
        try:
            return await self._ollama_call(
                cfg["name"], system, user, max_tokens, temp=0.3
            )
        except Exception as e:
            return f"[ROUTER_ERROR: {e}]"

    async def call_critical(self, system: str, user: str, max_tokens: int = 600) -> str:
        """Tier 3 — Gemini Flash. Final arbitration, ESCALATE override decisions."""
        return await self.call(system, user, tier=3, max_tokens=max_tokens, fallback=True)

    def get_stats(self) -> dict:
        """Return current routing statistics."""
        self._save_stats()
        return self.stats.to_dict()

    def log_summary(self):
        """Print current routing stats to log."""
        s = self.stats.to_dict()
        log.info(f"  Router stats: {s['total_calls']} calls | "
                 f"dist={s['tier_distribution']} | "
                 f"fallbacks={s['fallbacks']} | "
                 f"cost_saved={s['cost_saved']}")


# ── SINGLETON ────────────────────────────────────────────────────────────────

router = ModelRouter()


# ── COMPATIBILITY SHIMS ──────────────────────────────────────────────────────
# Drop-in replacements for existing llm_call / ollama_only_call usage

async def llm_call(system: str, user: str, max_tokens: int = 300) -> str:
    """Auto-routed call — replaces old llm_call in benchmark and swarm."""
    return await router.call(system, user, max_tokens=max_tokens)

async def ollama_only_call(system: str, user: str, max_tokens: int = 300) -> str:
    """CRITIC-safe Ollama-only call — replaces benchmark's ollama_only_call."""
    return await router.call_critic(system, user, max_tokens=max_tokens)

async def gemini_only_call(system: str, user: str, max_tokens: int = 600) -> str:
    """Critical decision call — Gemini with Ollama fallback."""
    return await router.call_critical(system, user, max_tokens=max_tokens)


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def test():
        print("=" * 60)
        print("NEXUS MODEL ROUTER — SELF TEST")
        print("=" * 60)

        tests = [
            ("Tier 1 auto",    "Classify this.",        "Is this a question? Yes or no."),
            ("Tier 2 auto",    "You are a copywriter.",  "Write a 3-sentence Reddit reply about VeilPiercer's session diff feature for r/LocalLLaMA."),
            ("Tier 1 explicit", None,                    None),
        ]

        for name, system, user in tests:
            if system is None:
                detected = router.auto_detect_tier("classify this", "yes or no label")
                print(f"\n[{name}] Auto-detected tier: {detected}")
                continue

            print(f"\n[{name}]")
            t = time.time()
            result = await router.call(system, user)
            ms = int((time.time() - t) * 1000)
            print(f"  Result ({ms}ms): {result[:100]}...")

        router.log_summary()
        print("\n" + "=" * 60)
        print("Stats:", json.dumps(router.get_stats(), indent=2))

    asyncio.run(test())
