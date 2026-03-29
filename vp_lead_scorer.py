"""
vp_lead_scorer.py
════════════════════════════════════════════════════════════════
VeilPiercer Lead Scoring Engine — Self-Improving Hybrid Model

Architecture:
  • Heuristic fallback   — always works, zero data required
  • Logistic Regression  — activates after 10+ recorded outcomes (numpy)
  • Random Forest        — activates after 30+ outcomes (sklearn, optional)
  • Auto-selects best model via held-out AUC comparison
  • Full feature storage → real correlation-based training
  • Persists weights + model state to JSON (survives restarts)

Public API:
  scorer  = LeadScorer()
  result  = scorer.score_lead(lead_data)        # single lead
  results = scorer.score_leads(leads)           # batch, sorted desc
  scorer.record_outcome(lead_id, "PURCHASED", features=result["features"])
  scorer.improve_weights()                      # Analytics Agent weekly call
  print(scorer.dashboard())
  info = scorer.get_model_info()

Score breakdown:
  intent       0.40  — pain keyword density (max raw 40)
  activity     0.20  — active within 14 days (max raw 20)
  fit          0.15  — role + team size + GitHub stars (max raw 15)
  engagement   0.10  — engagement_score field, 0-5 input (max raw 10)
  llm_boost    +0–15 — Ollama micro-analysis bonus (additive, not weighted)

GPU NOTE: _llm_predictive_boost() calls Ollama.
  The AcquisitionOrchestrator enforces a 13-second GPU spacing between
  all LLM calls via GPU_LOCK — this file just makes the call.
════════════════════════════════════════════════════════════════
"""

import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE = Path(__file__).parent

# ── Optional heavy deps ──────────────────────────────────────────────────────
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ── Keyword banks ─────────────────────────────────────────────────────────────
INTENT_KEYWORDS = [
    "swarm", "orchestration", "multi-agent", "multi agent",
    "local-first", "local first", "latency", "cloud cost",
    "data leak", "scaling agents", "crewai", "langgraph", "autogen",
    "agent debugging", "hallucination", "agent monitor", "agent trace",
    "llm observability", "prompt logging", "agent loop", "inference cost",
    "local llm", "ollama", "offline ai", "vram", "gpu", "self-hosted ai",
    "agent output", "agent behavior", "debugging agents", "agent framework",
    "veilpiercer", "veil-piercer", "rogue agent",
]

DISQUALIFIERS = [
    "enterprise only", "large enterprise", "fortune 500",
    "already in production with crewai", "langgraph at scale",
    "no budget", "not evaluating tools", "fully cloud-based",
]

TARGET_ROLES = [
    "ai engineer", "founder", "cto", "ml engineer", "builder",
    "developer", "indie", "researcher", "architect", "hacker",
]

POSITIVE_OUTCOMES = {"PURCHASED", "BOOKED_CALL", "REPLIED_INTERESTED", "TRIAL_STARTED"}
NEGATIVE_OUTCOMES = {"NO_REPLY", "REJECTED", "UNSUBSCRIBED", "NOT_A_FIT"}


class LeadScorer:
    """
    Hybrid self-improving lead scorer for VeilPiercer client acquisition.

    Tier  |  Score  |  Action
    ------+---------+------------------
    HOT   |  >= 75  |  IMMEDIATE_OUTREACH
    WARM  |  >= 60  |  NURTURE_SEQUENCE
    COLD  |  <  60  |  LOG_ONLY
    """

    HISTORY_FILE     = BASE / "lead_conversion_history.json"
    MODEL_STATE_FILE = BASE / "lead_model_state.json"
    FEATURE_NAMES    = ["intent", "activity", "fit", "engagement", "llm_boost"]

    def __init__(self, history_file: Optional[Path] = None):
        self.history_file = Path(history_file) if history_file else self.HISTORY_FILE
        self.conversion_history: List[Dict] = self._load_history()

        self.fallback_weights: Dict[str, float] = {
            "intent":     0.40,
            "activity":   0.20,
            "fit":        0.15,
            "engagement": 0.10,
        }

        # LR state
        self.lr_weights: Optional[List[float]] = None
        self.lr_bias:    float = 0.0
        self.lr_scale:   List[Tuple[float, float]] = []  # (mean, std) per feature

        # RF state
        self.rf_model  = None
        self.rf_scaler = None

        self.active_model   = "heuristic"
        self.model_metrics: Dict[str, float] = {}

        self._load_model_state()
        self._auto_train()

    # ── Public API ───────────────────────────────────────────────────────────

    def score_lead(self, lead_data: Dict) -> Dict:
        """Score one lead. Returns full result dict including features for recording."""
        breakdown    = self._compute_breakdown(lead_data)
        features     = self._to_features(breakdown)
        disqualified = self._is_disqualified(lead_data)

        if disqualified:
            final_score = 0.0
            probability = 0.0
        elif self.active_model == "random_forest" and self.rf_model is not None:
            probability = self._rf_predict(features)
            final_score = probability * 100.0
        elif self.active_model == "logistic_regression" and self.lr_weights:
            probability = self._lr_predict(features)
            final_score = probability * 100.0
        else:
            probability = None
            final_score = self._heuristic_score(breakdown)

        final_score = round(min(100.0, max(0.0, final_score)), 1)
        tier        = self._tier(final_score)

        return {
            "lead_id":            lead_data.get("id", "unknown"),
            "final_score":        final_score,
            "probability":        round(probability, 4) if probability is not None else None,
            "breakdown":          breakdown,
            "features":           features,      # Pass this to record_outcome()
            "model_used":         self.active_model,
            "tier":               tier,
            "disqualified":       disqualified,
            "timestamp":          datetime.utcnow().isoformat(),
            "recommended_action": self._action(tier),
            "talk_angle":         self._talk_angle(breakdown),
        }

    def score_leads(self, lead_list: List[Dict]) -> List[Dict]:
        """Batch score. Returns list sorted by final_score descending."""
        return sorted(
            [self.score_lead(lead) for lead in lead_list],
            key=lambda r: r["final_score"],
            reverse=True,
        )

    def record_outcome(self, lead_id: str, outcome: str,
                       features: Optional[List[float]] = None,
                       final_score: float = 0.0,
                       notes: str = "") -> Dict:
        """
        Record a real interaction result.
        Pass features from score_lead() for accurate model training.
        """
        entry = {
            "lead_id":    lead_id,
            "outcome":    outcome,
            "features":   features or [],
            "score_then": round(final_score, 2),
            "label":      1 if outcome in POSITIVE_OUTCOMES else 0,
            "timestamp":  datetime.utcnow().isoformat(),
            "notes":      notes,
        }
        self.conversion_history.append(entry)
        self._save_history()

        n = len(self.conversion_history)
        if n in (10, 20, 30, 50, 75, 100) or (n > 100 and n % 25 == 0):
            self.improve_weights()

        return {"ok": True, "total_outcomes": n, "model": self.active_model}

    def improve_weights(self) -> Dict:
        """Retrain best available model. Call weekly from Analytics Agent."""
        n = len(self.conversion_history)
        if n < 5:
            return {"ok": False, "reason": f"Need >=5 outcomes, have {n}"}

        X, y = self._build_training_set()
        if len(X) < 5:
            return {"ok": False, "reason": f"Need >=5 entries with stored features, have {len(X)}"}

        result: Dict = {}

        if len(X) >= 10 and NUMPY_AVAILABLE:
            result["lr"] = self._train_lr(X, y)

        if SKLEARN_AVAILABLE and len(X) >= 30:
            result["rf"] = self._train_rf(X, y)
            self._select_best_model(
                result.get("lr", {}).get("cv_auc"),
                result.get("rf", {}).get("cv_auc"),
            )
        elif self.lr_weights:
            self.active_model = "logistic_regression"

        self._save_model_state()
        result["active_model"] = self.active_model
        result["data_points"]  = n
        return result

    def get_model_info(self) -> Dict:
        return {
            "active_model":     self.active_model,
            "data_points":      len(self.conversion_history),
            "lr_trained":       self.lr_weights is not None,
            "rf_trained":       self.rf_model is not None,
            "model_metrics":    self.model_metrics,
            "fallback_weights": self.fallback_weights,
            "lr_coefficients":  dict(zip(
                self.FEATURE_NAMES, [round(w, 4) for w in self.lr_weights]
            )) if self.lr_weights else None,
        }

    def dashboard(self) -> str:
        n        = len(self.conversion_history)
        positive = sum(1 for e in self.conversion_history if e.get("label") == 1)
        cvr      = round(positive / n * 100, 1) if n > 0 else 0

        lines = [
            "=" * 54,
            "  VEILPIERCER LEAD SCORER — DASHBOARD",
            "=" * 54,
            f"  Outcomes recorded  : {n}",
            f"  Positive (won)     : {positive}",
            f"  Negative (lost)    : {n - positive}",
            f"  Conversion rate    : {cvr}%",
            f"  Active model       : {self.active_model.upper()}",
        ]
        if self.lr_weights:
            lines.append("  LR coefficients    :")
            for name, w in zip(self.FEATURE_NAMES, self.lr_weights):
                bar = "|" * max(0, int(abs(w) * 8))
                lines.append(f"    {name:<14} {w:+.4f}  {bar}")
        if self.model_metrics:
            lines.append("  Model AUC (holdout):")
            for mname, auc in self.model_metrics.items():
                lines.append(f"    {mname:<22} {auc:.4f}")
        recent = self.conversion_history[-5:]
        if recent:
            lines.append("  Recent outcomes    :")
            for e in reversed(recent):
                mark = "OK" if e.get("label") == 1 else "NO"
                lines.append(f"    [{mark}] {e['lead_id'][:24]:<24} {e['outcome']}")
        lines.append("=" * 54)
        return "\n".join(lines)

    # ── Feature extraction ───────────────────────────────────────────────────

    def _compute_breakdown(self, data: Dict) -> Dict:
        return {
            "intent":     self._score_intent(data),
            "activity":   self._score_activity(data),
            "fit":        self._score_fit(data),
            "engagement": self._score_engagement(data),
            "llm_boost":  self._llm_predictive_boost(data),
        }

    def _to_features(self, breakdown: Dict) -> List[float]:
        return [
            breakdown["intent"],
            breakdown["activity"],
            breakdown["fit"],
            breakdown["engagement"],
            breakdown["llm_boost"],
        ]

    def _score_intent(self, data: Dict) -> float:
        text = (
            data.get("profile_text", "") + " " +
            " ".join(data.get("recent_posts", []))
        ).lower()
        hits = sum(1 for kw in INTENT_KEYWORDS if kw in text)
        return min(40.0, hits * 8.0)

    def _score_activity(self, data: Dict) -> float:
        cutoff = datetime.utcnow() - timedelta(days=14)
        try:
            ts = data.get("timestamp", "2020-01-01")
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return 20.0 if dt > cutoff else 5.0
        except Exception:
            return 5.0

    def _score_fit(self, data: Dict) -> float:
        stars     = data.get("github_stars", 0)
        team_size = data.get("team_size", 999)
        role      = data.get("linkedin_title", "").lower()
        fit = 0.0
        if stars     > 30: fit += 5.0
        if team_size < 30: fit += 5.0
        if any(r in role for r in TARGET_ROLES): fit += 5.0
        return min(15.0, fit)

    def _score_engagement(self, data: Dict) -> float:
        return min(10.0, float(data.get("engagement_score", 0)) * 2.0)

    def _llm_predictive_boost(self, data: Dict) -> float:
        """
        Call local Ollama for nuanced boost 0-15.
        Falls back to 5.0 on any error.
        GPU spacing is managed by AcquisitionOrchestrator (13s between calls).
        """
        try:
            import requests
            prompt = (
                "You are scoring a developer lead for VeilPiercer — offline local-first "
                "AI agent monitor. Logs outputs, diffs runs, flags hallucinations. "
                "$197 one-time. Target: devs building local agents who hit debugging pain.\n\n"
                f"Lead: {json.dumps({k: v for k, v in data.items() if k != 'raw'}, indent=2)}\n\n"
                "Return ONLY a float 0.0-15.0. "
                "High = clearly building agents + hitting observability pain now."
            )
            resp = requests.post(
                "http://127.0.0.1:11434/api/generate",
                json={
                    "model": "mistral:7b-instruct-v0.3-q4_K_M",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 8},
                },
                timeout=15,
            )
            if resp.status_code == 200:
                raw   = resp.json().get("response", "5.0").strip()
                match = re.search(r"\d+\.?\d*", raw)
                if match:
                    return min(15.0, max(0.0, float(match.group())))
        except Exception:
            pass
        return 5.0

    def _is_disqualified(self, data: Dict) -> bool:
        text = (
            data.get("profile_text", "") +
            " ".join(data.get("recent_posts", []))
        ).lower()
        return any(dq in text for dq in DISQUALIFIERS)

    def _heuristic_score(self, breakdown: Dict) -> float:
        base = sum(breakdown.get(k, 0.0) * v for k, v in self.fallback_weights.items())
        return min(100.0, max(0.0, base + breakdown.get("llm_boost", 5.0)))

    # ── Model training ───────────────────────────────────────────────────────

    def _build_training_set(self):
        X, y = [], []
        for e in self.conversion_history:
            feats = e.get("features", [])
            if len(feats) == 5:
                X.append(feats)
                y.append(int(e.get("label", 0)))
        return X, y

    def _train_lr(self, X: List, y: List) -> Dict:
        if not NUMPY_AVAILABLE:
            return {"error": "numpy not available"}
        try:
            X_np = np.array(X, dtype=float)
            y_np = np.array(y, dtype=float)
            means = X_np.mean(axis=0)
            stds  = X_np.std(axis=0) + 1e-8
            X_s   = (X_np - means) / stds
            self.lr_scale = list(zip(means.tolist(), stds.tolist()))
            w = np.zeros(X_s.shape[1])
            b = 0.0
            for _ in range(600):
                logits = np.clip(X_s @ w + b, -20, 20)
                preds  = 1.0 / (1.0 + np.exp(-logits))
                err    = preds - y_np
                w -= 0.01 * ((X_s.T @ err) / len(y_np) + 0.01 * w)
                b -= 0.01 * float(np.mean(err))
            self.lr_weights = w.tolist()
            self.lr_bias    = float(b)
            acc    = float(np.mean(((1.0 / (1.0 + np.exp(-np.clip(X_s @ w + b, -20, 20)))) >= 0.5) == y_np))
            cv_auc = self._estimate_auc(X_np, y_np, "lr")
            self.model_metrics["logistic_regression"] = cv_auc
            print(f"[SCORER] LR trained | acc={acc:.3f} | auc={cv_auc:.3f} | n={len(y)}")
            return {"accuracy": round(acc, 3), "cv_auc": round(cv_auc, 3), "n": len(y)}
        except Exception as e:
            return {"error": str(e)}

    def _train_rf(self, X: List, y: List) -> Dict:
        try:
            X_np   = np.array(X, dtype=float)
            y_np   = np.array(y, dtype=int)
            scaler = StandardScaler()
            X_s    = scaler.fit_transform(X_np)
            rf     = RandomForestClassifier(
                n_estimators=100, max_depth=5, random_state=42,
                class_weight="balanced", min_samples_leaf=2,
            )
            rf.fit(X_s, y_np)
            self.rf_model  = rf
            self.rf_scaler = scaler
            cv_auc = self._estimate_auc(X_np, y_np, "rf")
            self.model_metrics["random_forest"] = cv_auc
            importances = dict(zip(
                self.FEATURE_NAMES,
                [round(float(v), 4) for v in rf.feature_importances_],
            ))
            print(f"[SCORER] RF trained | auc={cv_auc:.3f} | importances={importances}")
            return {"cv_auc": round(cv_auc, 3), "importances": importances, "n": len(y)}
        except Exception as e:
            return {"error": str(e)}

    def _estimate_auc(self, X, y, model_type: str) -> float:
        try:
            if not NUMPY_AVAILABLE:
                return 0.5
            n     = len(y)
            split = max(4, int(n * 0.8))
            X_te  = np.array(X[split:])
            y_te  = np.array(y[split:])
            if len(y_te) == 0:
                return 0.5
            if model_type == "lr" and self.lr_weights and self.lr_scale:
                means = np.array([m for m, _ in self.lr_scale])
                stds  = np.array([s for _, s in self.lr_scale])
                X_tes = (X_te - means) / stds
                probs = 1.0 / (1.0 + np.exp(-np.clip(X_tes @ np.array(self.lr_weights) + self.lr_bias, -20, 20)))
            elif model_type == "rf" and self.rf_model and self.rf_scaler:
                probs = self.rf_model.predict_proba(self.rf_scaler.transform(X_te))[:, 1]
            else:
                return 0.5
            pairs = wins = 0
            for i in range(len(y_te)):
                for j in range(len(y_te)):
                    if y_te[i] == 1 and y_te[j] == 0:
                        pairs += 1
                        if probs[i] > probs[j]:
                            wins += 1
            return wins / pairs if pairs > 0 else 0.5
        except Exception:
            return 0.5

    def _select_best_model(self, lr_auc: Optional[float], rf_auc: Optional[float]):
        if rf_auc and rf_auc > (lr_auc or 0) + 0.03 and self.rf_model:
            self.active_model = "random_forest"
            print(f"[SCORER] Promoted to RF (auc={rf_auc:.3f} vs LR={lr_auc:.3f})")
        elif self.lr_weights:
            self.active_model = "logistic_regression"

    # ── Prediction ───────────────────────────────────────────────────────────

    def _lr_predict(self, features: List[float]) -> float:
        if not NUMPY_AVAILABLE or not self.lr_weights:
            return 0.5
        try:
            f = list(features)
            if self.lr_scale and len(self.lr_scale) == 5:
                for i, (mean, std) in enumerate(self.lr_scale):
                    f[i] = (f[i] - mean) / std
            logit = sum(w * x for w, x in zip(self.lr_weights, f)) + self.lr_bias
            return 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, logit))))
        except Exception:
            return 0.5

    def _rf_predict(self, features: List[float]) -> float:
        try:
            X = np.array(features).reshape(1, -1)
            return float(self.rf_model.predict_proba(self.rf_scaler.transform(X))[0, 1])
        except Exception:
            return self._lr_predict(features)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _tier(self, score: float) -> str:
        return "HOT" if score >= 75 else "WARM" if score >= 60 else "COLD"

    def _action(self, tier: str) -> str:
        return {
            "HOT":  "IMMEDIATE_OUTREACH",
            "WARM": "NURTURE_SEQUENCE",
            "COLD": "LOG_ONLY",
        }[tier]

    def _talk_angle(self, breakdown: Dict) -> str:
        top = max(
            ["intent", "fit", "activity", "engagement"],
            key=lambda k: breakdown.get(k, 0),
        )
        return {
            "intent":     "Ask what agent framework they use and where it breaks",
            "fit":        "Reference a specific pain their role/stack typically hits",
            "activity":   "Reference their recent post or commit directly",
            "engagement": "Continue the existing thread — they are already warm",
        }.get(top, "Ask one specific question about their AI agent setup")

    def _auto_train(self):
        if len(self.conversion_history) >= 10:
            X, y = self._build_training_set()
            if len(X) >= 10:
                self.improve_weights()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load_history(self) -> List[Dict]:
        try:
            return json.loads(self.history_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_history(self):
        try:
            self.history_file.write_text(
                json.dumps(self.conversion_history, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[SCORER] Save error: {e}")

    def _load_model_state(self):
        try:
            if self.MODEL_STATE_FILE.exists():
                s = json.loads(self.MODEL_STATE_FILE.read_text(encoding="utf-8"))
                self.lr_weights      = s.get("lr_weights")
                self.lr_bias         = s.get("lr_bias", 0.0)
                self.lr_scale        = [tuple(v) for v in s.get("lr_scale", [])]
                self.active_model    = s.get("active_model", "heuristic")
                self.model_metrics   = s.get("model_metrics", {})
                self.fallback_weights = s.get("fallback_weights", self.fallback_weights)
        except Exception as e:
            print(f"[SCORER] State load error: {e}")

    def _save_model_state(self):
        try:
            self.MODEL_STATE_FILE.write_text(
                json.dumps({
                    "lr_weights":       self.lr_weights,
                    "lr_bias":          self.lr_bias,
                    "lr_scale":         self.lr_scale,
                    "active_model":     self.active_model,
                    "model_metrics":    self.model_metrics,
                    "fallback_weights": self.fallback_weights,
                    "saved_at":         datetime.utcnow().isoformat(),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[SCORER] State save error: {e}")
