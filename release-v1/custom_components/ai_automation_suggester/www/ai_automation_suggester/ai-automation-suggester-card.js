const LitElement = Object.getPrototypeOf(customElements.get("ha-panel-lovelace")); const html = LitElement.prototype.html; const css = LitElement.prototype.css;

class AiAutomationSuggesterCard extends LitElement {
  static properties = {
    hass: { attribute: false },
    suggestions: { state: true },
    loading: { state: true },
    error: { state: true },
    validationResults: { state: true },
    approvals: { state: true },
  };

  static styles = css`
    :host {
      display: block;
    }
    ha-card {
      padding: 16px;
    }
    .toolbar {
      align-items: center;
      display: flex;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    ul {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    li {
      border-top: 1px solid var(--divider-color, #ddd);
      padding: 12px 0;
    }
    li:first-child {
      border-top: 0;
    }
    pre {
      background: var(--code-editor-background-color, #f5f5f5);
      border-radius: 6px;
      overflow-x: auto;
      padding: 12px;
      white-space: pre-wrap;
    }
    .meta {
      color: var(--secondary-text-color);
      font-size: 0.9em;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .approval-panel { margin-top:14px; padding:12px; border:1px solid var(--divider-color); border-radius:10px; }
    .validation-result {
      padding: 12px;
      margin-top: 10px;
      border-radius: 8px;
      background: var(--secondary-background-color);
    }
    .validation-error {
      color: var(--error-color, #b00020);
    }
    .error {
      color: var(--error-color, #b00020);
    }
  `;

  constructor() {
    super();
    this.suggestions = [];
    this.loading = true;
    this.error = null;
    this.validationResults = {};
    this.approvals = {};
  }

  connectedCallback() {
    super.connectedCallback();
    this.fetchData();
  }

  setConfig(config) {
    this.config = config;
  }

  async fetchData() {
    if (!this.hass) {
      return;
    }
    this.loading = true;
    this.error = null;
    try {
      this.suggestions = await this.hass.callApi("GET", "ai_automation_suggester/suggestions");

      if (this.hass.user?.is_admin) {
        const response = await this.hass.callApi(
          "GET", "ai_automation_suggester/approvals"
        ).catch(err => {
          console.warn("Approval restoration unavailable:", err);
          return {success:true, approvals:[]};
        });
        if (response.success !== true || !Array.isArray(response.approvals))
          throw Error("Unable to restore approval records");

        const ids = new Set(this.suggestions.map(s => s.id));
        const restored = {};
        for (const record of response.approvals) {
          const id = record.suggestion_id;
          if (!id || !ids.has(id)) continue;
          const previous = restored[id];
          if (!previous ||
              String(record.created_at || "") >
              String(previous.created_at || "")) {
            restored[id] = {...record, busy:false};
          }
        }
        this.approvals = restored;
      }

    } catch (err) {
      this.error = err.message || "Failed to fetch suggestions.";
    } finally {
      this.loading = false;
    }
  }

  async copyYaml(yaml) {
    await navigator.clipboard.writeText(yaml || "");
    this.dispatchEvent(
      new CustomEvent("hass-notification", {
        detail: { type: "info", message: "YAML copied to clipboard." },
        bubbles: true,
        composed: true,
      }),
    );
  }

  async handleSuggestionAction(suggestionId, action) {
    try {
      const response = await this.hass.callApi(
        "POST",
        `ai_automation_suggester/${action}/${suggestionId}`,
      );
      if (response.success) {
        await this.fetchData();
      } else {
        this.error = response.error || `Failed to ${action} suggestion.`;
      }
    } catch (err) {
      this.error = err.message || `Failed to ${action} suggestion.`;
    }
  }


  async validateSuggestion(suggestion) {
    this.validationResults = {
      ...this.validationResults,
      [suggestion.id]: { loading: true }
    };
    try {
      const response = await this.hass.callApi(
        "POST", "ai_automation_suggester/approval",
        { action: "validate_suggestion", suggestion_id: suggestion.id }
      );
      this.validationResults = {
        ...this.validationResults,
        [suggestion.id]: response
      };
    } catch (error) {
      this.validationResults = {
        ...this.validationResults,
        [suggestion.id]: { error: error.message || String(error) }
      };
    }
  }

  renderValidation(suggestion) {
    const result = this.validationResults[suggestion.id];
    if (!result) return "";
    if (result.loading) return html`<p class="meta">Validating...</p>`;
    if (result.error || result.success === false) {
      return html`<div class="validation-error">
        Validation request failed: ${result.error || "Unknown error"}
      </div>`;
    }
    const validation = result.validation || {};
    const errors = validation.errors || [];
    const warnings = validation.warnings || [];
    return html`<div class="validation-result">
      <strong>${validation.valid ? "Validation passed" : "Validation failed"}</strong>
      <p>${errors.length} errors · ${warnings.length} warnings</p>
      ${errors.map(e => html`<p class="validation-error">${typeof e === "string" ? e : JSON.stringify(e)}</p>`)}
      ${warnings.map(w => html`<p>${typeof w === "string" ? w : JSON.stringify(w)}</p>`)}
      <p class="meta">Approval required · Deployment disabled</p>
    </div>`;
  }


  async approvalAction(suggestion, action) {
    if (!this.hass?.user?.is_admin) return;
    const id = suggestion.id;
    const previous = this.approvals[id] || {};
    if (previous.busy) return;

    const needsId = action !== "prepare_suggestion";
    if (needsId && !previous.approval_id) return;

    if (action === "approve_suggestion" &&
        !confirm("Approve proposal? No deployment will occur.")) return;
    if (action === "reject_approval" &&
        !confirm("Reject this approval?")) return;

    const payload = {action, suggestion_id:id};
    if (previous.approval_id)
      payload.approval_id = previous.approval_id;

    this.approvals = {
      ...this.approvals, [id]: {...previous, busy:true}
    };

    try {
      const result = await this.hass.callApi(
        "POST", "ai_automation_suggester/approval", payload
      );
      if (result.success === false)
        throw Error(result.error || "Approval request failed");

      const record = result.approval || {};
      this.approvals = {...this.approvals, [id]:{
        ...previous, ...record,
        approval_id: result.approval_id ||
          record.approval_id || previous.approval_id,
        status: result.status || record.status || previous.status,
        expires_at: result.expires_at ||
          record.expires_at || previous.expires_at,
        message: "Action completed: " + action,
        busy:false
      }};
    } catch(error) {
      this.approvals = {...this.approvals, [id]:{
        ...previous,
        message: "Error: " + (error.message || String(error)),
        busy:false
      }};
    }
  }


  renderApproval(suggestion) {
    if (!this.hass?.user?.is_admin) return "";
    const a = this.approvals[suggestion.id] || {};
    const pending = a.status === "pending" &&
      !!a.expires_at && Date.now() < Date.parse(a.expires_at);
    return html`
      <div class="approval-panel">
        <strong>Administrator approval</strong>
        <p class="meta">Approval only — deployment disabled.</p>
        ${a.status ? html`<p>Status: ${a.status}</p>` : ""}
        ${a.expires_at ? html`<p class="meta">Expires: ${a.expires_at}</p>` : ""}
        ${a.message ? html`<p>${a.message}</p>` : ""}
        <div class="actions">
          <ha-button .disabled=${!!a.busy || pending || a.status === "approved"}
            @click=${() => this.approvalAction(suggestion,"prepare_suggestion")}>
            Prepare
          </ha-button>
          <ha-button .disabled=${!!a.busy || !pending}
            @click=${() => this.approvalAction(suggestion,"approve_suggestion")}>
            Approve
          </ha-button>
          <ha-button .disabled=${!!a.busy || !pending}
            @click=${() => this.approvalAction(suggestion,"reject_approval")}>
            Reject
          </ha-button>
          <ha-button .disabled=${!!a.busy || !a.approval_id}
            @click=${() => this.approvalAction(suggestion,"approval_status")}>
            Check status
          </ha-button>
        </div>
      </div>`;
  }

  renderSuggestion(suggestion) {
    const yamlCode = suggestion.yamlCode || suggestion.yaml_block || "";
    return html`
      <li>
        <h3>${suggestion.title || "AI automation suggestion"}</h3>
        <p>${suggestion.shortDescription || suggestion.description || "No description returned."}</p>
        <p class="meta">
          ${suggestion.provider || "Unknown provider"} - ${suggestion.model || "Unknown model"} -
          ${suggestion.status || "new"}
        </p>
        ${yamlCode ? html`<details><summary>View proposed automation YAML</summary><pre><code>${yamlCode}</code></pre></details>` : html`<p class="meta">No YAML was returned.</p>`}
        ${(suggestion.warnings || []).length
          ? html`<p class="meta">${suggestion.warnings.join(" ")}</p>`
          : ""}
        <div class="actions">
          <ha-button @click=${() => this.validateSuggestion(suggestion)}>Validate Automation</ha-button>

          <ha-button @click=${() => this.copyYaml(yamlCode)} .disabled=${!yamlCode}>Copy YAML</ha-button>
          <ha-button @click=${() => this.handleSuggestionAction(suggestion.id, "accept")}>Accept</ha-button>
          <ha-button @click=${() => this.handleSuggestionAction(suggestion.id, "decline")}>Decline</ha-button>
          <ha-button @click=${() => this.handleSuggestionAction(suggestion.id, "dismiss")}>Dismiss</ha-button>
        </div>
        ${this.renderValidation(suggestion)}
        ${this.renderApproval(suggestion)}
      </li>
    `;
  }

  render() {
    return html`
      <ha-card>
        <div class="toolbar">
          <h2>AI Automation Suggestions</h2>
          <ha-button @click=${this.fetchData}>Refresh</ha-button>
        </div>
        ${this.loading
          ? html`<p>Loading suggestions...</p>`
          : this.error
            ? html`<p class="error">${this.error}</p>`
            : this.suggestions.length
              ? html`<ul>${this.suggestions.map((suggestion) => this.renderSuggestion(suggestion))}</ul>`
              : html`<p>No stored suggestions yet.</p>`}
      </ha-card>
    `;
  }
}

if (!customElements.get("ai-automation-suggester-card")) customElements.define("ai-automation-suggester-card", AiAutomationSuggesterCard);