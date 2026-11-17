"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const panel = document.getElementById("advocate-directory-panel");
  const filters = document.getElementById("advocate-directory-filters");
  const results = document.getElementById("advocate-directory-results");
  const error = document.getElementById("advocate-directory-error");
  const count = document.getElementById("advocate-directory-count");
  const summary = document.getElementById("advocate-directory-summary");
  const previous = document.getElementById("advocate-directory-previous");
  const next = document.getElementById("advocate-directory-next");
  let offset = 0;
  let sequence = 0;

  function setError(message) {
    error.textContent = message;
    error.classList.toggle("hidden", !message);
  }
  function paragraph(text) {
    const p = document.createElement("p");
    p.textContent = text;
    return p;
  }
  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.method === "POST") {
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-Token", document.querySelector('meta[name="csrf-token"]').content);
    }
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }
  function render(item) {
    const card = document.createElement("article");
    const heading = document.createElement("h3");
    heading.textContent = item.name;
    card.append(heading);
    card.append(paragraph(`Registration: ${item.bar_registration_number || "Not provided"} | Status: ${item.verification_status} | ${item.active ? "Active" : "Inactive"}`));
    card.append(paragraph(`Category: ${item.category || "—"} | District: ${item.district || "—"} | Languages: ${item.languages || "—"}`));
    card.append(paragraph(`Email: ${item.email || "—"} | Phone: ${item.contact_masked}`));
    card.append(paragraph(`Verification reference: ${item.verification_reference || "Not recorded"} | Verified at: ${item.verified_at || "Not recorded"}`));
    const historyButton = document.createElement("button");
    historyButton.type = "button";
    historyButton.className = "button button-secondary";
    historyButton.textContent = "Show registration and verification history";
    const history = document.createElement("div");
    historyButton.addEventListener("click", async () => {
      historyButton.disabled = true;
      try {
        const body = await request(`/admin/advocates/${item.id}/verification-history`);
        history.replaceChildren(paragraph("Most recent 25 registration and verification events:"),
          ...body.items.map((event) => paragraph(`${event.action} | ${event.operator_id} | ${event.created_at}`)));
        if (!body.items.length) history.append(paragraph("No matching audit events found."));
      } catch (err) {
        setError(String(err.message || err).replaceAll("_", " "));
      } finally {
        historyButton.disabled = false;
      }
    });
    card.append(historyButton, history);
    if (item.active && item.verification_status === "PENDING") {
      const form = document.createElement("form");
      const refLabel = document.createElement("label");
      refLabel.textContent = "Non-sensitive verification evidence reference";
      const reference = document.createElement("input");
      reference.required = true;
      reference.minLength = 3;
      reference.maxLength = 160;
      refLabel.append(reference);
      const checkLabel = document.createElement("label");
      const checked = document.createElement("input");
      checked.type = "checkbox";
      checked.required = true;
      checkLabel.append(checked, document.createTextNode(" I independently checked this advocate's credentials and eligibility."));
      const button = document.createElement("button");
      button.type = "submit";
      button.className = "button button-primary";
      button.textContent = "Record verification";
      form.append(refLabel, checkLabel, button);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!window.confirm("Record this advocate as verified and eligible for matching assignments?")) return;
        button.disabled = true;
        try {
          await request(`/admin/advocates/${item.id}/verify`, { method: "POST", body: JSON.stringify({ verification_reference: reference.value.trim(), independent_checks_confirmed: checked.checked }) });
          await load();
        } catch (err) {
          setError(String(err.message || err).replaceAll("_", " "));
          button.disabled = false;
        }
      });
      card.append(form);
    }
    return card;
  }
  async function load() {
    const id = ++sequence;
    const params = new URLSearchParams(new FormData(filters));
    params.set("offset", String(offset));
    previous.disabled = true;
    next.disabled = true;
    results.replaceChildren();
    count.textContent = "Loading…";
    summary.textContent = "Directory summary loading…";
    setError("");
    try {
      const body = await request(`/admin/advocate-directory?${params}`);
      if (id !== sequence) return;
      results.replaceChildren(...body.items.map(render));
      summary.textContent = `All advocates: ${body.counts.total} | Pending: ${body.counts.pending} | Verified: ${body.counts.verified} | Inactive: ${body.counts.inactive} (counts may overlap; independent of filters)`;
      count.textContent = `${body.total} matching advocates; showing ${body.items.length ? offset + 1 : 0}–${offset + body.items.length}`;
      previous.disabled = offset === 0;
      next.disabled = offset + body.items.length >= body.total;
    } catch (err) {
      if (id !== sequence) return;
      count.textContent = "Directory unavailable";
      summary.textContent = "Directory summary unavailable";
      setError(String(err.message || err).replaceAll("_", " "));
    }
  }
  panel.addEventListener("toggle", () => { if (panel.open) { offset = 0; load(); } });
  filters.addEventListener("submit", (event) => { event.preventDefault(); offset = 0; load(); });
  previous.addEventListener("click", () => { offset = Math.max(0, offset - 50); load(); });
  next.addEventListener("click", () => { offset += 50; load(); });
});
