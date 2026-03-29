"""
vp_acquisition_main.py
════════════════════════════════════════════════════════════════
VeilPiercer Client-Acquisition AGI — 5-Agent Orchestration

Agents:
  1. LeadResearcherAgent  — score + route leads by tier
  2. OutreachAgent        — open genuine conversations (no pitch)
  3. QualifierAgent       — identify fit, book calls, record outcomes
  4. CloserAgent          — lock in the sale only when fit is clear
  5. AnalyticsAgent       — weekly improvement loop + dashboard

SINGLE-Clarity principles applied here:
  - Talk WITH people, not AT them
  - Lead with genuine insight or a question about their situation
  - Mention VeilPiercer only when it naturally answers their stated problem
  - Close only when the prospect has the actual problem we solve
  - All outcomes feed back into LeadScorer for continuous self-improvement

GPU THROTTLE — 13 seconds minimum between any LLM/Ollama call:
  All agent LLM calls go through _gpu_call(), which acquires GPU_LOCK and
  enforces a 13-second cooldown between calls. This prevents GPU throttling
  and OOM from concurrent inference while still allowing sequential use.

Run:
  python vp_acquisition_main.py --demo                     # demo with sample leads
  python vp_acquisition_main.py --score leads.json         # score a batch file
  python vp_acquisition_main.py --reply lead123 "text"     # process a reply
  python vp_acquisition_main.py --purchase lead123         # record a purchase
  python vp_acquisition_main.py --analytics                # run analytics now
  python vp_acquisition_main.py --dashboard                # print model dashboard
  python vp_acquisition_main.py --status                   # pipeline stats
════════════════════════════════════════════════════════════════
"""

import json
import time
import argparse
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

BASE = Path(__file__).parent
log  = logging.getLogger("ACQUISITION")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── GPU throttle ─────────────────────────────────────────────────────────────
# All LLM calls go through _gpu_call(). One call at a time, 13s minimum gap.
_GPU_LOCK            = threading.Lock()
_LAST_GPU_CALL_TIME  = 0.0
GPU_COOLDOWN_SECONDS = 13.0


def _gpu_call(prompt: str,
              model: str = "qwen2.5:7b-instruct-q5_K_M",
              max_tokens: int = 350,
              temperature: float = 0.35) -> str:
    """
    Call local Ollama with a 13-second GPU cooldown between calls.
    Acquires _GPU_LOCK so concurrent threads queue up rather than crash the GPU.
    Returns response string or empty string on failure.
    """
    global _LAST_GPU_CALL_TIME
    with _GPU_LOCK:
        elapsed = time.time() - _LAST_GPU_CALL_TIME
        wait    = GPU_COOLDOWN_SECONDS - elapsed
        if wait > 0:
            log.debug(f"[GPU] Waiting {wait:.1f}s cooldown before next call...")
            time.sleep(wait)
        try:
            import requests
            resp = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model":   model,
                    "prompt":  prompt,
                    "stream":  False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
                timeout=90,
            )
            _LAST_GPU_CALL_TIME = time.time()
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e:
            log.warning(f"[GPU] Ollama call failed: {e}")
        _LAST_GPU_CALL_TIME = time.time()
        return ""


# ── CRM persistence ───────────────────────────────────────────────────────────
CRM_FILE = BASE / "vp_crm_state.json"


def load_crm() -> Dict:
    try:
        if CRM_FILE.exists():
            return json.loads(CRM_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {
        "leads": {},
        "pipeline": {"hot": [], "warm": [], "cold": []},
        "stats": {
            "total_scored": 0, "outreach_sent": 0,
            "calls_booked": 0, "closed_won":    0, "closed_lost": 0,
        },
        "last_analytics_run": None,
    }


def save_crm(crm: Dict):
    try:
        CRM_FILE.write_text(json.dumps(crm, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"[CRM] Save failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT 1 — LEAD RESEARCHER
# ═══════════════════════════════════════════════════════════════════════════════

class LeadResearcherAgent:
    """
    Scores incoming leads using LeadScorer and routes by tier.
    Also surfaces content and affiliate opportunities from the lead data.

    NOTE: The LeadScorer's _llm_predictive_boost() calls Ollama internally.
    That call is NOT wrapped in _gpu_call() — the scorer is a separate module.
    If you want per-scorer-call GPU spacing, import GPU_COOLDOWN_SECONDS in scorer too.
    For now, we enforce spacing only on the 5 agent message-generation calls.
    """

    def __init__(self, scorer, crm: Dict):
        self.scorer = scorer
        self.crm    = crm

    def process(self, leads: List[Dict]) -> Dict[str, List[Dict]]:
        """Score all leads. Returns {HOT: [...], WARM: [...], COLD: [...]}"""
        log.info(f"[RESEARCHER] Scoring {len(leads)} leads...")
        results = self.scorer.score_leads(leads)
        routed  = {"HOT": [], "WARM": [], "COLD": []}

        for result in results:
            tier    = result["tier"]
            lead_id = result["lead_id"]

            routed[tier].append(result)
            self.crm["leads"][lead_id] = {
                **result,
                "status":       "NEW",
                "interactions": [],
            }
            if lead_id not in self.crm["pipeline"][tier.lower()]:
                self.crm["pipeline"][tier.lower()].append(lead_id)
            self.crm["stats"]["total_scored"] += 1

        save_crm(self.crm)
        log.info(
            f"[RESEARCHER] HOT={len(routed['HOT'])} "
            f"WARM={len(routed['WARM'])} COLD={len(routed['COLD'])}"
        )
        return routed

    def surface_opportunities(self, leads: List[Dict]) -> Dict:
        """Extract content topics + affiliate targets from lead signal."""
        content_topics = set()
        affiliate_targets: List[str] = []

        for lead in leads:
            text  = (lead.get("profile_text", "") + " ".join(lead.get("recent_posts", []))).lower()
            stars = lead.get("github_stars", 0)
            title = lead.get("linkedin_title", "").lower()

            if "crewai" in text or "langgraph" in text:
                content_topics.add("VeilPiercer vs CrewAI vs LangGraph: local debugging showdown")
            if "latency" in text or "slow" in text:
                content_topics.add("Why local AI agents outperform cloud orchestration in 2026")
            if "hallucination" in text or "rogue" in text:
                content_topics.add("How to detect rogue AI agents before they cause damage")
            if "cost" in text or "api bill" in text:
                content_topics.add("$0 API cost AI agent stack: Ollama + VeilPiercer full guide")
            if "vram" in text or "gpu" in text:
                content_topics.add("Running 11-agent AI swarms on an RTX 4060: what actually works")

            # Identify potential affiliates (devs with audience)
            if stars > 200 or "tutorial" in text or "youtube" in text or "newsletter" in text:
                name = lead.get("id", "unknown")
                affiliate_targets.append(f"{name} ({title}, {stars} stars)")

        return {
            "content_topics":    list(content_topics),
            "affiliate_targets": affiliate_targets,
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT 2 — OUTREACH AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class OutreachAgent:
    """
    Opens genuine, non-salesy conversations with HOT and WARM leads.

    SINGLE-Clarity: Talk WITH people, not AT them.
    - Every opener starts with THEIR situation, never with VeilPiercer
    - One insight or one specific question — not a pitch
    - VeilPiercer is never mentioned in the first message
    - Sound like a developer, not a marketer
    """

    PLATFORM_VOICE = {
        "github":   "technical peer-to-peer; reference the specific issue/file; under 60 words",
        "hn":       "analytical, insight-first; no product language; concrete numbers if possible; under 100 words",
        "discord":  "casual community member; 2-3 sentences max; conversational",
        "reddit":   "authentic subreddit tone; no product push; ask a specific question",
        "linkedin": "professional but direct; reference their specific role or post first; under 80 words",
        "twitter":  "brief and punchy; reference something they tweeted; under 40 words",
        "email":    "developer-to-developer; specific opening line; short paragraphs; under 120 words",
    }

    def __init__(self, crm: Dict):
        self.crm = crm

    def craft_opener(self, scored_lead: Dict, platform: str = "github") -> str:
        """
        Generate a genuine conversation opener via local LLM (GPU throttled).
        Does NOT mention VeilPiercer — just starts a real conversation.
        """
        lead_id   = scored_lead["lead_id"]
        angle     = scored_lead.get("talk_angle", "")
        breakdown = scored_lead.get("breakdown", {})
        lead_raw  = self.crm["leads"].get(lead_id, {})
        voice     = self.PLATFORM_VOICE.get(platform.lower(), "natural, developer-to-developer")

        safe_profile = {
            k: v for k, v in lead_raw.items()
            if k in ("profile_text", "recent_posts", "linkedin_title", "github_stars")
        }

        prompt = f"""You are Lauren, a developer. You are opening a conversation — NOT pitching anything.

Lead data:
{json.dumps(safe_profile, indent=2)}

Intent signals (their pain — for context, do not reference these numbers):
- Intent score: {breakdown.get('intent', 0)}/40
- Conversation angle: {angle}

Platform: {platform.upper()}
Voice: {voice}

Write a message that:
1. Opens with THEIR specific situation, something they built, or a pain they mentioned
2. Adds one genuine insight or asks one specific question about their AI/agent work
3. Does NOT mention VeilPiercer, any product, pricing, or anything to buy
4. Sounds like a developer who ran into the same problem, not a salesperson
5. Follows the voice/length guide above

Output ONLY the message text. No labels, no commentary."""

        message = _gpu_call(prompt, temperature=0.4) or f"[Opener generation failed for {lead_id}]"

        # Log to CRM
        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["interactions"].append({
                "type":      "OUTREACH_SENT",
                "platform":  platform,
                "message":   message[:500],
                "timestamp": datetime.utcnow().isoformat(),
                "status":    "SENT",
            })
            self.crm["leads"][lead_id]["status"] = "OUTREACH_SENT"
            self.crm["stats"]["outreach_sent"] += 1
            save_crm(self.crm)

        return message

    def batch_outreach(self, hot_leads: List[Dict], platform: str = "github") -> List[Dict]:
        """Generate openers for all HOT leads. GPU throttle applies between each."""
        results = []
        for i, lead in enumerate(hot_leads):
            log.info(f"[OUTREACH] Crafting opener {i+1}/{len(hot_leads)} for {lead['lead_id']}")
            msg = self.craft_opener(lead, platform)
            results.append({
                "lead_id":    lead["lead_id"],
                "platform":   platform,
                "tier":       lead["tier"],
                "score":      lead["final_score"],
                "message":    msg,
                "talk_angle": lead.get("talk_angle", ""),
            })
        return results


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT 3 — QUALIFIER AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class QualifierAgent:
    """
    Evaluates replies for genuine fit.
    Records outcomes back to LeadScorer for self-improvement.
    Generates value-add follow-ups (still not pitching, still human).
    """

    FIT_SIGNALS = [
        "agent", "swarm", "debugging", "hallucin", "local llm", "monitor",
        "trace", "log", "orchestrat", "crewai", "langgraph", "autogen",
        "vram", "ollama", "inference", "latency", "cost", "offline",
    ]

    BUYING_SIGNALS = [
        "how much", "pricing", "price", "buy", "purchase", "sign up",
        "interested", "demo", "show me", "try it", "link", "where can i",
        "how do i get", "want to try",
    ]

    NEGATIVE_SIGNALS = [
        "not interested", "unsubscribe", "stop", "leave me alone",
        "already have", "no thanks", "don't contact", "remove me",
    ]

    def __init__(self, scorer, crm: Dict):
        self.scorer = scorer
        self.crm    = crm

    def qualify(self, lead_id: str, reply_text: str) -> Dict:
        """
        Evaluate a reply. Returns qualification result + recommended next step.
        Also records outcome to scorer for retraining.
        """
        text = reply_text.lower()

        fit_hits         = sum(1 for s in self.FIT_SIGNALS    if s in text)
        has_buying_intent = any(s in text for s in self.BUYING_SIGNALS)
        is_negative       = any(s in text for s in self.NEGATIVE_SIGNALS)

        if is_negative:
            outcome   = "REJECTED"
            next_step = "CLOSE_LOST"
        elif has_buying_intent:
            outcome   = "REPLIED_INTERESTED"
            next_step = "SEND_TO_CLOSER"
        elif fit_hits >= 2:
            outcome   = "BOOKED_CALL"
            next_step = "NURTURE_WITH_VALUE"
        else:
            outcome   = "NO_REPLY_FIT"
            next_step = "CONTINUE_NURTURE"

        lead_data   = self.crm["leads"].get(lead_id, {})
        features    = lead_data.get("features", [])
        final_score = lead_data.get("final_score", 0.0)

        # Record to scorer (triggers retraining at milestones)
        if outcome in {"REJECTED", "REPLIED_INTERESTED", "BOOKED_CALL"}:
            self.scorer.record_outcome(
                lead_id=lead_id,
                outcome=outcome,
                features=features,
                final_score=final_score,
                notes=f"fit_hits={fit_hits} buying_intent={has_buying_intent}",
            )

        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["interactions"].append({
                "type":           "REPLY_QUALIFIED",
                "reply_snippet":  reply_text[:200],
                "fit_hits":       fit_hits,
                "buying_intent":  has_buying_intent,
                "outcome":        outcome,
                "timestamp":      datetime.utcnow().isoformat(),
            })
            self.crm["leads"][lead_id]["status"] = outcome
            if outcome == "BOOKED_CALL":
                self.crm["stats"]["calls_booked"] += 1
            save_crm(self.crm)

        log.info(f"[QUALIFIER] {lead_id}: {outcome} -> {next_step}")
        return {
            "lead_id":       lead_id,
            "is_fit":        fit_hits >= 2,
            "fit_hits":      fit_hits,
            "buying_intent": has_buying_intent,
            "outcome":       outcome,
            "next_step":     next_step,
        }

    def generate_follow_up(self, lead_id: str, context: str = "") -> str:
        """
        Value-add follow-up. Still human. Mentions VP only if it directly answers
        a problem they described.
        GPU throttled via _gpu_call().
        """
        lead_data    = self.crm["leads"].get(lead_id, {})
        interactions = lead_data.get("interactions", [])
        last         = interactions[-1] if interactions else {}

        prompt = f"""You are Lauren, continuing a developer conversation.

Previous interaction: {json.dumps(last, indent=2)[:400]}
Context: {context[:300]}

Write a follow-up message that:
1. References something specific from their reply (shows you read it)
2. Adds ONE concrete tip or insight about AI agent debugging, monitoring, or local LLM setup
3. Mentions VeilPiercer ONLY if they explicitly described a problem it solves
   - If you mention it: "I built something for exactly this — veil-piercer.com, $197 one-time" and stop
4. Does NOT say "just checking in", does NOT ask for a sale
5. No em-dashes, no emojis, no marketing language
6. Under 90 words

Output ONLY the message."""

        message = _gpu_call(prompt, temperature=0.3) or "[Follow-up generation failed]"

        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["interactions"].append({
                "type":      "FOLLOW_UP_SENT",
                "message":   message[:500],
                "timestamp": datetime.utcnow().isoformat(),
            })
            save_crm(self.crm)

        return message


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT 4 — CLOSER AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class CloserAgent:
    """
    Locks in the sale ONLY when a lead is genuinely qualified and shows buying intent.

    SINGLE-Clarity: Close is a natural next step, never a pressure move.
    - Confirm their problem in their own words first
    - State VP's value in one plain sentence
    - Give the price clearly: $197 one-time
    - Add a no-risk guarantee sentence
    - Under 120 words total
    """

    STRIPE_LINK    = "https://buy.stripe.com/00w5kv0Q1dcVgCkgHSbsc03"
    AFFILIATE_PAGE = "https://veil-piercer.com/affiliate.html"

    def __init__(self, scorer, crm: Dict):
        self.scorer = scorer
        self.crm    = crm

    def generate_close(self, lead_id: str, context: str = "") -> str:
        """
        Generate the closing message. GPU throttled.
        Only call when QualifierAgent returns next_step=SEND_TO_CLOSER.
        """
        lead_data   = self.crm["leads"].get(lead_id, {})
        breakdown   = lead_data.get("breakdown", {})
        interactions = lead_data.get("interactions", [])
        convo = " | ".join(
            i.get("reply_snippet", "")[:100]
            for i in interactions[-3:] if i.get("reply_snippet")
        )

        prompt = f"""You are Lauren. This developer has shown clear buying intent and their problem matches VeilPiercer exactly.

Conversation context: {convo or context}
Their pain breakdown: intent={breakdown.get('intent', 0)}/40

Write a closing message (under 120 words) that:
1. Opens by restating their specific problem in their own language (1 sentence)
2. States plainly: "VeilPiercer does exactly this — [logs every agent output, diffs runs, flags hallucinations, 100% local, zero cloud]"
3. Price: "$197 one-time, no subscription ever"
4. Link: {self.STRIPE_LINK}
5. Guarantee: "If it doesn't solve the problem in the first week, I'll refund you directly."
6. No hype, no emojis, no em-dashes, no pressure tactics
7. Sounds like a developer who built something useful, not a salesperson

Output ONLY the message."""

        message = _gpu_call(prompt, temperature=0.2) or (
            f"Based on what you described, VeilPiercer handles that exactly. "
            f"It logs every agent output, diffs runs, flags hallucinations, runs 100% locally. "
            f"$197 one-time, no subscription. {self.STRIPE_LINK} "
            f"If it doesn't solve the problem in the first week, I'll refund you directly."
        )

        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["interactions"].append({
                "type":        "CLOSE_SENT",
                "message":     message[:500],
                "stripe_link": self.STRIPE_LINK,
                "timestamp":   datetime.utcnow().isoformat(),
                "status":      "AWAITING_PAYMENT",
            })
            self.crm["leads"][lead_id]["status"] = "CLOSE_SENT"
            save_crm(self.crm)

        log.info(f"[CLOSER] Close sent to {lead_id}")
        return message

    def record_purchase(self, lead_id: str, notes: str = "") -> Dict:
        """Call when a lead buys. Records to scorer for retraining."""
        lead_data   = self.crm["leads"].get(lead_id, {})
        features    = lead_data.get("features", [])
        final_score = lead_data.get("final_score", 0.0)

        self.scorer.record_outcome(
            lead_id=lead_id, outcome="PURCHASED",
            features=features, final_score=final_score, notes=notes,
        )

        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["status"]  = "PURCHASED"
            self.crm["stats"]["closed_won"] += 1
            save_crm(self.crm)

        log.info(f"[CLOSER] PURCHASE recorded: {lead_id}")
        return {"ok": True, "lead_id": lead_id, "outcome": "PURCHASED"}

    def record_lost(self, lead_id: str, reason: str = "") -> Dict:
        lead_data   = self.crm["leads"].get(lead_id, {})
        features    = lead_data.get("features", [])
        final_score = lead_data.get("final_score", 0.0)

        self.scorer.record_outcome(
            lead_id=lead_id, outcome="REJECTED",
            features=features, final_score=final_score, notes=reason,
        )

        if lead_id in self.crm["leads"]:
            self.crm["leads"][lead_id]["status"] = "LOST"
            self.crm["stats"]["closed_lost"] += 1
            save_crm(self.crm)

        return {"ok": True, "lead_id": lead_id, "outcome": "REJECTED"}

    def pitch_affiliate(self, lead_id: str) -> str:
        """
        For rejected/lost leads with an audience: offer the affiliate program.
        Separate from the purchase close, GPU throttled.
        """
        lead_data = self.crm["leads"].get(lead_id, {})
        profile   = lead_data.get("profile_text", "")[:300]

        prompt = f"""You are Lauren. This developer didn't buy VeilPiercer but they have an audience.

Profile: {profile}

Write a very short message (under 70 words) that:
1. Acknowledges they may not need VP personally right now (1 sentence)
2. Mentions: "if you know devs building agents who hit this problem, there's an affiliate program"
3. Terms in one phrase: "30% recurring for 12 months, 20% lifetime, 90-day cookie"
4. Link: {self.AFFILIATE_PAGE}
5. No pressure. Friendly. Developer tone.

Output ONLY the message."""

        return _gpu_call(prompt, temperature=0.3) or (
            f"No worries if VP isn't a fit right now. If you know developers building "
            f"agents who hit this debugging problem, there's an affiliate program: "
            f"30% recurring for 12 months, 20% lifetime, 90-day cookie. {self.AFFILIATE_PAGE}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  AGENT 5 — ANALYTICS AGENT
# ═══════════════════════════════════════════════════════════════════════════════

class AnalyticsAgent:
    """
    Weekly improvement loop.
    - Triggers scorer.improve_weights()
    - Reports pipeline metrics
    - Surfaces best channel + recommendation
    - Pushes summary to swarm EH (non-blocking)
    """

    EH_BASE = "http://127.0.0.1:7701"

    def __init__(self, scorer, crm: Dict):
        self.scorer = scorer
        self.crm    = crm

    def run_weekly(self) -> Dict:
        log.info("[ANALYTICS] Running weekly improvement pass...")

        # Retrain scorer
        improvement = self.scorer.improve_weights()

        # Pipeline stats
        s          = self.crm["stats"]
        outreach   = s["outreach_sent"]
        calls      = s["calls_booked"]
        won        = s["closed_won"]
        lost       = s["closed_lost"]
        reply_rate = round(calls / outreach * 100, 1) if outreach > 0 else 0
        close_rate = round(won / (won + lost) * 100, 1) if (won + lost) > 0 else 0
        revenue    = won * 197

        # Best channel by wins
        channel_wins: Dict[str, int] = {}
        for lead in self.crm["leads"].values():
            if lead.get("status") == "PURCHASED":
                for i in lead.get("interactions", []):
                    if i.get("type") == "OUTREACH_SENT":
                        p = i.get("platform", "unknown")
                        channel_wins[p] = channel_wins.get(p, 0) + 1
        best_channel = max(channel_wins, key=channel_wins.get) if channel_wins else "not enough data"

        model_info = self.scorer.get_model_info()
        rec        = self._recommendation(reply_rate, close_rate, best_channel)

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "pipeline": {
                "total_scored":  s["total_scored"],
                "outreach_sent": outreach,
                "calls_booked":  calls,
                "closed_won":    won,
                "closed_lost":   lost,
                "reply_rate":    f"{reply_rate}%",
                "close_rate":    f"{close_rate}%",
                "revenue":       f"${revenue}",
            },
            "best_channel": best_channel,
            "model":        model_info,
            "improvement":  improvement,
            "recommendation": rec,
        }

        print(self.scorer.dashboard())
        self._print_report(report)
        self._push_to_swarm(report)

        self.crm["last_analytics_run"] = datetime.utcnow().isoformat()
        save_crm(self.crm)

        log.info("[ANALYTICS] Weekly run complete.")
        return report

    def _recommendation(self, reply_rate: float, close_rate: float, best_channel: str) -> str:
        if reply_rate < 5:
            return (
                f"Reply rate is {reply_rate}% — "
                f"try a different opener angle or switch from {best_channel}"
            )
        if close_rate < 20 and reply_rate >= 5:
            return "Replies are coming in but not closing — qualify harder before sending closes"
        if close_rate >= 20:
            return (
                f"Close rate {close_rate}% is strong — scale outreach on {best_channel}, "
                f"publish more content to increase inbound"
            )
        return "Continue current approach — not enough data yet for a specific recommendation"

    def _print_report(self, report: Dict):
        p = report["pipeline"]
        print("\n" + "=" * 58)
        print("  VEILPIERCER ACQUISITION — WEEKLY REPORT")
        print("=" * 58)
        print(f"  Leads scored    : {p['total_scored']}")
        print(f"  Outreach sent   : {p['outreach_sent']}")
        print(f"  Calls booked    : {p['calls_booked']}")
        print(f"  Closed won      : {p['closed_won']}")
        print(f"  Revenue         : {p['revenue']}")
        print(f"  Reply rate      : {p['reply_rate']}")
        print(f"  Close rate      : {p['close_rate']}")
        print(f"  Best channel    : {report['best_channel']}")
        print(f"  Active model    : {report['model']['active_model'].upper()}")
        print(f"  Recommendation  : {report['recommendation']}")
        print("=" * 58 + "\n")

    def _push_to_swarm(self, report: Dict):
        try:
            import requests
            p       = report["pipeline"]
            summary = (
                f"ACQUISITION WEEKLY: won={p['closed_won']} "
                f"reply_rate={p['reply_rate']} close_rate={p['close_rate']} "
                f"best_channel={report['best_channel']} "
                f"model={report['model']['active_model']} "
                f"rec={report['recommendation'][:80]}"
            )
            requests.post(
                f"{self.EH_BASE}/inject",
                json={"task": summary, "priority": 3},
                timeout=3,
            )
        except Exception:
            pass  # Non-critical


# ═══════════════════════════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class AcquisitionOrchestrator:
    """
    Ties all 5 agents together.
    Full lead lifecycle: score → outreach → qualify → close → analytics.
    """

    ANALYTICS_INTERVAL_DAYS = 7

    def __init__(self):
        from vp_lead_scorer import LeadScorer
        self.crm        = load_crm()
        self.scorer     = LeadScorer()
        self.researcher = LeadResearcherAgent(self.scorer, self.crm)
        self.outreach   = OutreachAgent(self.crm)
        self.qualifier  = QualifierAgent(self.scorer, self.crm)
        self.closer     = CloserAgent(self.scorer, self.crm)
        self.analytics  = AnalyticsAgent(self.scorer, self.crm)
        log.info(f"[ORCHESTRATOR] All 5 agents ready. GPU cooldown: {GPU_COOLDOWN_SECONDS}s")

    def ingest_leads(self, leads: List[Dict], platform: str = "github") -> Dict:
        """
        Full pipeline: score → route → craft openers for HOT leads.
        GPU-throttled: 13s minimum between each LLM call.
        """
        routed       = self.researcher.process(leads)
        opportunities = self.researcher.surface_opportunities(leads)

        outreach_results: List[Dict] = []
        if routed["HOT"]:
            log.info(f"[ORCHESTRATOR] Generating openers for {len(routed['HOT'])} HOT leads")
            outreach_results = self.outreach.batch_outreach(routed["HOT"], platform)

        self._maybe_run_analytics()

        return {
            "routed":          routed,
            "outreach_results": outreach_results,
            "opportunities":   opportunities,
        }

    def process_reply(self, lead_id: str, reply_text: str) -> Dict:
        """
        Handle a reply. Qualifies → routes to closer / nurture / lost.
        GPU-throttled: follow-up or close message has 13s gap.
        """
        qual   = self.qualifier.qualify(lead_id, reply_text)
        result = {"qualification": qual}

        if qual["next_step"] == "SEND_TO_CLOSER":
            result["close_message"] = self.closer.generate_close(lead_id, context=reply_text)

        elif qual["next_step"] == "NURTURE_WITH_VALUE":
            result["follow_up"] = self.qualifier.generate_follow_up(lead_id, context=reply_text)

        elif qual["next_step"] == "CLOSE_LOST":
            result["affiliate_pitch"] = self.closer.pitch_affiliate(lead_id)
            self.closer.record_lost(lead_id, reason="Rejected outreach")

        return result

    def record_purchase(self, lead_id: str) -> Dict:
        return self.closer.record_purchase(lead_id)

    def run_analytics(self) -> Dict:
        return self.analytics.run_weekly()

    def status(self) -> str:
        s          = self.crm["stats"]
        model_info = self.scorer.get_model_info()
        return (
            f"\n[PIPELINE STATUS]\n"
            f"  scored={s['total_scored']} outreach={s['outreach_sent']} "
            f"calls={s['calls_booked']} won={s['closed_won']} lost={s['closed_lost']}\n"
            f"  model={model_info['active_model']} "
            f"data_points={model_info['data_points']}\n"
            f"  gpu_cooldown={GPU_COOLDOWN_SECONDS}s\n"
        )

    def _maybe_run_analytics(self):
        last_run = self.crm.get("last_analytics_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                if datetime.utcnow() - last_dt < timedelta(days=self.ANALYTICS_INTERVAL_DAYS):
                    return
            except Exception:
                pass
        if len(self.scorer.conversion_history) >= 5:
            self.analytics.run_weekly()


# ═══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ═══════════════════════════════════════════════════════════════════════════════

def _run_demo(orch: AcquisitionOrchestrator):
    sample_leads = [
        {
            "id":             "gh_user_001",
            "profile_text":   "Building multi-agent AI workflows with LangGraph and Ollama. Frustrated with debugging agent loops and latency on local hardware.",
            "recent_posts":   [
                "Why does my LangGraph agent keep hallucinating on step 3?",
                "Need better observability for local LLM inference chains",
            ],
            "github_stars":   142,
            "team_size":      1,
            "linkedin_title": "AI Engineer / Founder",
            "engagement_score": 4,
            "timestamp":      datetime.utcnow().isoformat(),
        },
        {
            "id":             "hn_user_002",
            "profile_text":   "CTO at a small startup. Evaluating CrewAI and AutoGen. Main concerns: cloud cost and data leaks from API providers.",
            "recent_posts":   [
                "Show HN: agent orchestration layer on top of CrewAI",
                "Cloud costs for AI agents are insane. $800/month just in API calls.",
            ],
            "github_stars":   23,
            "team_size":      8,
            "linkedin_title": "CTO",
            "engagement_score": 3,
            "timestamp":      datetime.utcnow().isoformat(),
        },
        {
            "id":             "discord_user_003",
            "profile_text":   "Python developer building chatbots with GPT-4. Not interested in local AI.",
            "recent_posts":   ["Using OpenAI API for my Discord bot"],
            "github_stars":   5,
            "team_size":      50,
            "linkedin_title": "Developer",
            "engagement_score": 1,
            "timestamp":      "2020-06-01T00:00:00",
        },
    ]

    print("\n" + "=" * 60)
    print("  ACQUISITION AGI — DEMO RUN")
    print("=" * 60)

    result = orch.ingest_leads(sample_leads, platform="github")

    for tier, leads in result["routed"].items():
        for lead in leads:
            print(f"\n[{tier}] {lead['lead_id']} | score={lead['final_score']} | {lead['recommended_action']}")
            print(f"  breakdown: {lead['breakdown']}")
            print(f"  angle: {lead.get('talk_angle', '')}")

    if result["outreach_results"]:
        print("\n" + "-" * 60)
        print("GENERATED OPENERS (HOT leads only):")
        for r in result["outreach_results"]:
            print(f"\n[{r['lead_id']}] {r['platform'].upper()}")
            print(r["message"])

    if result["opportunities"]["content_topics"]:
        print("\n" + "-" * 60)
        print("CONTENT OPPORTUNITIES:")
        for t in result["opportunities"]["content_topics"]:
            print(f"  > {t}")

    if result["opportunities"]["affiliate_targets"]:
        print("\nAFFILIATE TARGETS:")
        for t in result["opportunities"]["affiliate_targets"]:
            print(f"  > {t}")

    print("\n" + orch.status())


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="VeilPiercer Client-Acquisition AGI")
    parser.add_argument("--score",    metavar="FILE",
                        help="Score leads from a JSON file (list of lead dicts)")
    parser.add_argument("--platform", default="github",
                        help="Platform for outreach (github/hn/discord/linkedin/email)")
    parser.add_argument("--reply",    nargs=2, metavar=("LEAD_ID", "REPLY"),
                        help="Process a reply: --reply lead123 'their reply text'")
    parser.add_argument("--purchase", metavar="LEAD_ID",
                        help="Record a purchase for a lead ID")
    parser.add_argument("--analytics", action="store_true",
                        help="Run the weekly analytics + improvement loop now")
    parser.add_argument("--dashboard", action="store_true",
                        help="Print the scoring model dashboard")
    parser.add_argument("--status",   action="store_true",
                        help="Print pipeline status")
    parser.add_argument("--demo",     action="store_true",
                        help="Run a demo with 3 sample leads")
    parser.add_argument("--gpu-cooldown", type=float, default=GPU_COOLDOWN_SECONDS,
                        help=f"Seconds between GPU calls (default: {GPU_COOLDOWN_SECONDS})")
    args = parser.parse_args()

    global GPU_COOLDOWN_SECONDS
    GPU_COOLDOWN_SECONDS = args.gpu_cooldown

    orch = AcquisitionOrchestrator()

    if args.dashboard:
        print(orch.scorer.dashboard())
        return

    if args.status:
        print(orch.status())
        return

    if args.analytics:
        orch.run_analytics()
        return

    if args.purchase:
        print(json.dumps(orch.record_purchase(args.purchase), indent=2))
        return

    if args.reply:
        lead_id, reply_text = args.reply
        result = orch.process_reply(lead_id, reply_text)
        print("\n" + "-" * 50)
        if "close_message" in result:
            print("[CLOSE]\n" + result["close_message"])
        elif "follow_up" in result:
            print("[FOLLOW-UP]\n" + result["follow_up"])
        elif "affiliate_pitch" in result:
            print("[AFFILIATE PITCH]\n" + result["affiliate_pitch"])
        print(f"\nQualification: {result['qualification']['outcome']}")
        return

    if args.score:
        try:
            leads = json.loads(Path(args.score).read_text(encoding="utf-8"))
            if not isinstance(leads, list):
                leads = [leads]
        except Exception as e:
            print(f"Error reading file: {e}")
            return
        result = orch.ingest_leads(leads, platform=args.platform)
        print(f"\nScored: {len(leads)} leads")
        print(f"HOT={len(result['routed']['HOT'])} | WARM={len(result['routed']['WARM'])} | COLD={len(result['routed']['COLD'])}")
        if result["outreach_results"]:
            print("\nOUTREACH OPENERS:")
            for r in result["outreach_results"]:
                print(f"\n[{r['lead_id']}]\n{r['message']}")
        return

    if args.demo:
        _run_demo(orch)
        return

    # Interactive mode
    print(f"\n[ACQUISITION AGI] Ready. GPU cooldown: {GPU_COOLDOWN_SECONDS}s")
    print("Commands: score <file> | reply <id> <text> | purchase <id> | analytics | status | quit\n")
    while True:
        try:
            cmd = input("> ").strip()
            if not cmd or cmd.lower() == "quit":
                break
            parts = cmd.split(None, 2)
            if parts[0] == "score" and len(parts) > 1:
                leads  = json.loads(Path(parts[1]).read_text(encoding="utf-8"))
                result = orch.ingest_leads(leads if isinstance(leads, list) else [leads], platform=args.platform)
                print(orch.status())
            elif parts[0] == "reply" and len(parts) > 2:
                result = orch.process_reply(parts[1], parts[2])
                msg    = result.get("close_message") or result.get("follow_up") or result.get("affiliate_pitch", "")
                if msg:
                    print(msg)
                print(f"  -> {result['qualification']['outcome']}")
            elif parts[0] == "analytics":
                orch.run_analytics()
            elif parts[0] == "status":
                print(orch.status())
            elif parts[0] == "purchase" and len(parts) > 1:
                orch.record_purchase(parts[1])
            elif parts[0] == "dashboard":
                print(orch.scorer.dashboard())
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            print("\nExiting.")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
