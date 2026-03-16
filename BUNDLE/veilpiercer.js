
/**
 * VeilPiercer — AI Agent Observatory SDK (Node.js)
 * Connects your AI Agents to the NEXUS ULTRA Control Plane.
 */
class Observatory {
  constructor(token, apiUrl = "http://127.0.0.1:3000") {
    this.token = token;
    this.apiUrl = apiUrl.replace(/\/$/, "");
  }

  /**
   * Sends a telemetry signal to the VeilPiercer Hub.
   */
  async sendSignal({ agent, node, scores, detail = "", impact = "NOMINAL" }) {
    const payload = {
      token: this.token,
      command: `LOG_SIGNAL: ${detail}`,
      protocol: impact,
      scores: {
        vis: scores.vis || 50,
        saf: scores.saf || 50,
        priv: scores.priv || 50
      },
      useCase: agent
    };

    try {
      const response = await fetch(`${this.apiUrl}/veilpiercer/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      return await response.json();
    } catch (err) {
      console.error(`VeilPiercer SDK Error: ${err.message}`);
      return { ok: false, error: err.message };
    }
  }

  /**
   * Runs an AI-assisted audit on a specific query via the Command Hub.
   */
  async quickAudit(query) {
    try {
      const response = await fetch(`${this.apiUrl}/veilpiercer/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: this.token,
          command: query,
          protocol: "NOMINAL"
        })
      });
      return await response.json();
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }
}

module.exports = Observatory;
