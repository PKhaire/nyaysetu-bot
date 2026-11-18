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
  const dialog = document.getElementById("advocate-detail-dialog");
  const detail = document.getElementById("advocate-detail-content");
  const detailError = document.getElementById("advocate-detail-error");
  const success = document.getElementById("advocate-directory-success");
  const filterState = document.getElementById("advocate-filter-state");
  let offset = 0;
  let sequence = 0;
  let applied = new URLSearchParams(new FormData(filters));
  let working = false;

  function setError(message) {
    error.textContent = message;
    error.classList.toggle("hidden", !message);
  }
  function paragraph(text) {
    const p = document.createElement("p");
    p.textContent = text;
    return p;
  }
  function displayTime(value) {
    if (!value) return "Not recorded";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Invalid timestamp; contact support";
    return `${new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(date)} IST`;
  }
  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.method === "POST") {
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-Token", document.querySelector('meta[name="csrf-token"]').content);
    }
    const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
    if (response.status === 401) {
      window.location.assign("/admin/login");
      throw new Error("Your session expired. Please sign in again.");
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }
  function render(item) {
    const card = document.createElement("div");
    card.className = "advocate-detail-section";
    card.append(paragraph(`Registration: ${item.bar_registration_number || "Not provided"}`));
    card.append(paragraph(`Status: ${item.verification_status} · ${item.active ? "Active" : "Inactive"}`));
    card.append(paragraph(`Category: ${item.category || "Not recorded"} · District: ${item.district || "Not recorded"}`));
    card.append(paragraph(`Languages: ${item.languages || "Not recorded"}`));
    card.append(paragraph(`Email: ${item.email || "Not recorded"} · Phone: ${item.contact_masked}`));
    card.append(paragraph(`Verification reference: ${item.verification_reference || "Not recorded"}`));
    card.append(paragraph(`Verified at: ${displayTime(item.verified_at)}`));
    const historyButton = document.createElement("button");
    historyButton.type = "button";
    historyButton.className = "button button-secondary";
    historyButton.textContent = "Show registration and verification history";
    const history = document.createElement("div");
    historyButton.addEventListener("click", async () => {
      historyButton.disabled = true;
      try {
        const body = await request(`/admin/advocates/${item.id}/verification-history`);
        history.replaceChildren(paragraph("Most recent 25 registration and verification events. Ask an administrator if older history is needed:"),
          ...body.items.map((event) => paragraph(`${event.action} | ${event.operator_id} | ${displayTime(event.created_at)}`)));
        if (!body.items.length) history.append(paragraph("No matching audit events found."));
      } catch (err) {
        detailError.textContent = String(err.message || err).replaceAll("_", " ");
        detailError.classList.remove("hidden");
      } finally {
        historyButton.disabled = false;
      }
    });
    card.append(historyButton, history);
    const issues = Array.isArray(item.verification_issues) ? item.verification_issues : ["details unavailable"];
    if (item.active && item.verification_status === "PENDING" && issues.length) {
      const warning = paragraph(`Verification unavailable. Correct or review these required fields first: ${issues.join(", ").replaceAll("_", " ")}. Contact an authorized administrator; do not edit the database directly.`);
      warning.className = "alert alert-error";
      card.append(warning);
    }
    if (item.active && item.verification_status === "PENDING" && !issues.length) {
      const form = document.createElement("form");
      form.className = "advocate-verification-form advocate-detail-section";
      const title = document.createElement("h3");
      title.textContent = "Record verification";
      const note = paragraph("Only verify after independently checking credentials and eligibility. Use a non-sensitive evidence reference.");
      note.className = "muted small";
      const refLabel = document.createElement("label");
      refLabel.textContent = "Non-sensitive verification evidence reference";
      const reference = document.createElement("input");
      reference.required = true;
      reference.minLength = 3;
      reference.maxLength = 160;
      refLabel.append(reference);
      const checkLabel = document.createElement("label");
      checkLabel.className = "advocate-confirm-label";
      const checked = document.createElement("input");
      checked.type = "checkbox";
      checked.required = true;
      const checkText = document.createElement("span");
      checkText.textContent = "I independently checked this advocate's credentials and eligibility.";
      checkLabel.append(checked, checkText);
      const button = document.createElement("button");
      button.type = "submit";
      button.className = "button button-primary";
      button.textContent = "Record verification";
      form.append(title, note, refLabel, checkLabel, button);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!window.confirm(`Record ${item.name} as verified? This records your independent decision and may make them eligible for matching assignments. The system does not check credentials automatically.`)) return;
        working = true;
        button.disabled = true;
        detailError.classList.add("hidden");
        try {
          await request(`/admin/advocates/${item.id}/verify`, { method: "POST", body: JSON.stringify({ verification_reference: reference.value.trim(), independent_checks_confirmed: checked.checked }) });
          working = false;
          dialog.close();
          success.textContent = "Verification recorded. Refresh the appointment queue before assigning this advocate.";
          success.classList.remove("hidden");
          await load();
        } catch (err) {
          working = false;
          detailError.textContent = String(err.message || err).replaceAll("_", " ");
          detailError.classList.remove("hidden");
          button.disabled = false;
        }
      });
      card.append(form);
    }
    const listing = document.createElement("article");
    listing.className = "advocate-card";
    const info = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = item.name;
    const badges = document.createElement("div");
    badges.className = "advocate-card-badges";
    const status = document.createElement("span");
    status.className = `advocate-badge ${item.verification_status === "VERIFIED" ? "advocate-badge-verified" : "advocate-badge-pending"}`;
    status.textContent = item.verification_status;
    const active = document.createElement("span");
    active.className = "advocate-badge";
    active.textContent = item.active ? "Active" : "Inactive";
    badges.append(status, active);
    const scope = paragraph(`${item.bar_registration_number ? `Registration: ${item.bar_registration_number} · ` : "Registration not recorded · "}${item.category || "Category not set"} · ${item.district || "District not set"} · ${item.languages || "Languages not set"}`);
    scope.className = "muted small";
    info.append(heading, badges, scope);
    const open = document.createElement("button");
    open.type = "button";
    open.className = "button button-secondary";
    open.textContent = "View details";
    open.setAttribute("aria-label", `View details for ${item.name}`);
    open.addEventListener("click", () => {
      detailError.classList.add("hidden");
      document.getElementById("advocate-detail-title").textContent = item.name;
      detail.replaceChildren(card);
      dialog.showModal();
    });
    listing.append(info, open);
    return listing;
  }
  async function load() {
    const id = ++sequence;
    const params = new URLSearchParams(applied);
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
      const cards = [["All advocates", body.counts.total], ["Pending", body.counts.pending], ["Verified", body.counts.verified], ["Inactive", body.counts.inactive]].map(([label, value]) => {
        const box = document.createElement("div");
        box.className = "advocate-stat";
        const name = document.createElement("span");
        name.textContent = label;
        const number = document.createElement("strong");
        number.textContent = String(value);
        box.append(name, number);
        return box;
      });
      summary.replaceChildren(...cards);
      count.textContent = `${body.total} matching advocates; showing ${body.items.length ? offset + 1 : 0}–${offset + body.items.length}`;
      if (!body.items.length) results.append(paragraph("No advocates match the applied filters."));
      previous.disabled = offset === 0;
      next.disabled = offset + body.items.length >= body.total;
    } catch (err) {
      if (id !== sequence) return;
      count.textContent = "Directory unavailable";
      summary.textContent = "Directory summary unavailable";
      setError(String(err.message || err).replaceAll("_", " "));
    }
  }
  function applyFilters() {
    applied = new URLSearchParams(new FormData(filters));
    const selected = [...applied.entries()].filter(([key, value]) => value && !(key === "status" && value === "ALL") && !(key === "active" && value === "ALL"));
    filterState.textContent = selected.length ? `Applied filters: ${selected.map(([key, value]) => `${key}: ${value}`).join(" · ")}` : "No filters applied.";
    success.classList.add("hidden");
    offset = 0;
    load();
  }
  panel.addEventListener("toggle", () => { if (panel.open) applyFilters(); });
  filters.addEventListener("submit", (event) => { event.preventDefault(); applyFilters(); });
  filters.addEventListener("input", () => { filterState.textContent = "Filters changed. Select Apply filters to update results."; });
  filters.addEventListener("change", () => { filterState.textContent = "Filters changed. Select Apply filters to update results."; });
  document.getElementById("advocate-directory-clear").addEventListener("click", () => { filters.reset(); applyFilters(); });
  previous.addEventListener("click", () => { offset = Math.max(0, offset - 50); load(); });
  next.addEventListener("click", () => { offset += 50; load(); });
  document.getElementById("advocate-detail-close").addEventListener("click", () => { if (!working) dialog.close(); });
  document.getElementById("advocate-detail-cancel").addEventListener("click", () => { if (!working) dialog.close(); });
  dialog.addEventListener("cancel", (event) => { if (working) event.preventDefault(); });
});
