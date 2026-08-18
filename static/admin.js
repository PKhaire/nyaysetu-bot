"use strict";

const TERMINAL_STATUSES = new Set(["COMPLETED", "REFUNDED", "CANCELLED"]);
const ACTIVE_STATUSES = new Set([
  "UNASSIGNED", "ASSIGNED", "CONFIRMED", "RESCHEDULE_REQUIRED",
  "REFUND_REVIEW", "NO_SHOW",
]);

const state = { items: [], advocates: [], transitions: {}, selected: null };
const elements = {};

function byId(id) { return document.getElementById(id); }

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function displayStatus(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function formatDate(value) {
  if (!value) return "—";
  const parts = String(value).split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  }).format(new Date(parts[0], parts[1] - 1, parts[2]));
}

function formatTimestamp(value) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not set";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium", timeStyle: "short",
  }).format(date);
}

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

async function api(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD"].includes(options.method)) {
    headers.set("X-CSRF-Token", csrfToken());
  }
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401) {
    window.location.assign("/admin/login");
    throw new Error("Your session expired. Please sign in again.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Request failed (${response.status})`);
  }
  return body;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  window.setTimeout(() => elements.toast.classList.add("hidden"), 4000);
}

function showQueueError(message) {
  elements.queueError.textContent = message;
  elements.queueError.classList.toggle("hidden", !message);
}

function updateSummary() {
  const count = (status) => state.items.filter((item) => item.fulfillment_status === status).length;
  elements.countUnassigned.textContent = count("UNASSIGNED");
  elements.countAssigned.textContent = count("ASSIGNED");
  elements.countConfirmed.textContent = count("CONFIRMED");
  elements.countAttention.textContent = state.items.filter((item) =>
    ["RESCHEDULE_REQUIRED", "REFUND_REVIEW", "NO_SHOW"].includes(item.fulfillment_status)
  ).length;
}

function searchableText(item) {
  return [
    item.booking_id, item.case_id, item.name, item.category, item.subcategory,
    item.assigned_to, item.fulfillment_status,
  ].join(" ").toLowerCase();
}

function filteredItems() {
  const selectedStatus = elements.statusFilter.value;
  const query = elements.queueSearch.value.trim().toLowerCase();
  return state.items.filter((item) => {
    const statusMatches = selectedStatus === "ALL"
      || (selectedStatus === "ACTIVE" && ACTIVE_STATUSES.has(item.fulfillment_status))
      || item.fulfillment_status === selectedStatus;
    return statusMatches && (!query || searchableText(item).includes(query));
  });
}

function appendTwoLineCell(row, primary, secondary, className = "") {
  const cell = node("td", className);
  cell.append(node("span", "cell-primary", primary));
  if (secondary) cell.append(node("span", "cell-secondary", secondary));
  row.append(cell);
  return cell;
}

function appointmentRow(item) {
  const row = node("tr");
  appendTwoLineCell(
    row,
    `${formatDate(item.date)} · ${item.slot || "Time not set"}`,
    `Booking #${item.booking_id}${item.case_id ? ` · ${item.case_id}` : ""}`
  );
  appendTwoLineCell(row, item.name || "Client", item.contact_masked || "Contact not available");
  appendTwoLineCell(row, item.category || "Other legal issue", item.subcategory || "");
  appendTwoLineCell(
    row,
    item.advocate?.name || item.assigned_to || "Not assigned",
    `Payment: ${displayStatus(item.payment_status)}`
  );

  const statusCell = node("td");
  statusCell.append(node("span", `status status-${item.fulfillment_status}`, displayStatus(item.fulfillment_status)));
  if (item.operator_notes) statusCell.append(node("span", "cell-secondary", item.operator_notes));
  row.append(statusCell);

  const overdue = item.sla_due_at
    && new Date(item.sla_due_at).getTime() < Date.now()
    && !TERMINAL_STATUSES.has(item.fulfillment_status);
  appendTwoLineCell(
    row,
    formatTimestamp(item.sla_due_at),
    overdue ? "Attention overdue" : "",
    overdue ? "sla-overdue" : ""
  );

  const actionCell = node("td");
  const action = node("button", "button button-secondary", TERMINAL_STATUSES.has(item.fulfillment_status) ? "View" : "Update");
  action.type = "button";
  action.addEventListener("click", () => openDialog(item));
  actionCell.append(action);
  row.append(actionCell);
  return row;
}

function renderQueue() {
  const items = filteredItems();
  elements.rows.replaceChildren(...items.map(appointmentRow));
  elements.emptyState.classList.toggle("hidden", items.length !== 0);
}

function populateStatusOptions(item) {
  const current = item.fulfillment_status;
  const values = [current, ...(state.transitions[current] || [])];
  elements.dialogStatus.replaceChildren(...values.map((value) => {
    const option = node("option", "", value === current
      ? `${displayStatus(value)} (no status change)` : displayStatus(value));
    option.value = value;
    return option;
  }));
}

function populateAdvocateOptions(selectedId = null) {
  const options = [node("option", "", "Select a verified advocate")];
  options[0].value = "";
  for (const advocate of state.advocates.filter((item) => item.active)) {
    const option = node(
      "option", "",
      `${advocate.name} · ${advocate.bar_registration_number} · ${advocate.district}`
    );
    option.value = String(advocate.id);
    option.selected = Number(selectedId) === advocate.id;
    options.push(option);
  }
  elements.dialogAdvocate.replaceChildren(...options);
}

function updateDialogRequirements() {
  const status = elements.dialogStatus.value;
  elements.dialogNotes.required = [
    "COMPLETED", "NO_SHOW", "RESCHEDULE_REQUIRED", "REFUND_REVIEW",
    "REFUNDED", "CANCELLED",
  ].includes(status);
  elements.rescheduleFields.classList.toggle("hidden", status !== "RESCHEDULE_REQUIRED");
}

function setText(id, value) {
  elements[id].textContent = value || "Not provided";
}

function renderBrief(brief) {
  elements.briefEmpty.classList.toggle("hidden", Boolean(brief));
  elements.briefDetails.classList.toggle("hidden", !brief);
  if (!brief) return;
  setText("briefSummary", brief.issue_summary);
  setText("briefStage", brief.legal_stage ? displayStatus(brief.legal_stage) : null);
  setText("briefDates", brief.important_dates);
  setText("briefOutcome", brief.desired_outcome);
  setText("briefUrgency", [brief.urgency, brief.safety_concerns].filter(Boolean).join(" · "));
  setText("briefOpposingParty", brief.opposing_party);
  setText("briefDocuments", (brief.documents_available || []).join(", ") || "None declared");
  setText(
    "briefConsent",
    brief.consent_version
      ? `${brief.consent_version} · ${formatTimestamp(brief.consented_at)}`
      : "Not recorded"
  );
}

function renderContactHistory(events) {
  const items = (events || []).map((event) => {
    const item = node("li");
    item.append(node(
      "strong", "",
      `${displayStatus(event.audience)} · ${displayStatus(event.channel)} · ${displayStatus(event.outcome)}`
    ));
    item.append(node("span", "cell-secondary", `${formatTimestamp(event.contacted_at)} · ${event.operator_id}`));
    item.append(node("span", "cell-secondary", event.notes));
    if (event.follow_up_due_at) {
      item.append(node("span", "cell-secondary", `Follow-up: ${formatTimestamp(event.follow_up_due_at)}`));
    }
    return item;
  });
  elements.contactHistory.replaceChildren(...items);
  elements.contactHistory.classList.toggle("hidden", items.length === 0);
}

function clearRevealedContact() {
  elements.revealedClientContact.textContent = "";
  elements.revealedClientContact.classList.add("hidden");
  elements.contactRevealReason.value = "";
}

function openDialog(item) {
  state.selected = item;
  elements.dialogBookingId.value = item.booking_id;
  elements.dialogTitle.textContent = `Booking #${item.booking_id}`;
  elements.dialogContext.textContent = `${item.name || "Client"} · ${formatDate(item.date)} · ${item.slot || "Time not set"} · ${item.category || "Legal consultation"}`;
  populateAdvocateOptions(item.advocate_id);
  elements.dialogNotes.value = item.operator_notes || "";
  elements.dialogDate.value = "";
  elements.dialogSlot.value = "";
  elements.contactNotes.value = "";
  elements.contactFollowUp.value = "";
  elements.dialogError.textContent = "";
  elements.dialogError.classList.add("hidden");
  clearRevealedContact();
  renderBrief(item.case_brief);
  renderContactHistory(item.contact_events);
  populateStatusOptions(item);
  updateDialogRequirements();
  const terminal = TERMINAL_STATUSES.has(item.fulfillment_status);
  elements.dialogStatus.disabled = terminal;
  elements.dialogAdvocate.disabled = terminal;
  elements.dialogNotes.disabled = terminal;
  elements.dialogSubmit.classList.toggle("hidden", terminal);
  elements.revealAdvocateContact.disabled = !item.advocate_id;
  elements.dialog.showModal();
}

function closeDialog() {
  if (elements.dialog.open) elements.dialog.close();
  clearRevealedContact();
  state.selected = null;
}

async function saveAppointment(event) {
  event.preventDefault();
  const item = state.selected;
  if (!item) return;
  const status = elements.dialogStatus.value;
  const payload = {
    status,
    advocate_id: elements.dialogAdvocate.value || null,
    operator_notes: elements.dialogNotes.value.trim(),
  };
  if (status === "RESCHEDULE_REQUIRED" && (elements.dialogDate.value || elements.dialogSlot.value)) {
    payload.reschedule_date = elements.dialogDate.value;
    payload.reschedule_slot_code = elements.dialogSlot.value;
  }
  elements.dialogSubmit.disabled = true;
  elements.dialogError.classList.add("hidden");
  try {
    await api(`/admin/fulfillments/${item.booking_id}`, {
      method: "PATCH", body: JSON.stringify(payload),
    });
    closeDialog();
    await loadAppointments();
    showToast(`Booking #${item.booking_id} was updated.`);
  } catch (error) {
    elements.dialogError.textContent = String(error.message || error).replaceAll("_", " ");
    elements.dialogError.classList.remove("hidden");
  } finally {
    elements.dialogSubmit.disabled = false;
  }
}

async function revealClientContact() {
  const item = state.selected;
  if (!item) return;
  try {
    const result = await api(`/admin/fulfillments/${item.booking_id}/contact-reveal`, {
      method: "POST",
      body: JSON.stringify({ reason: elements.contactRevealReason.value.trim() }),
    });
    const digits = String(result.contact || "").replace(/\D/g, "");
    elements.revealedClientContact.replaceChildren();
    const text = node("span", "", result.contact || "Not available");
    elements.revealedClientContact.append(text);
    if (digits) {
      const message = `Hello ${item.name || ""}, this is NyaySetu regarding consultation booking #${item.booking_id} on ${formatDate(item.date)} at ${item.slot || "the selected time"}.`;
      const link = node("a", "contact-link", "Open WhatsApp");
      link.href = `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      elements.revealedClientContact.append(link);
    }
    elements.revealedClientContact.classList.remove("hidden");
    window.setTimeout(clearRevealedContact, Number(result.expires_in_seconds || 300) * 1000);
  } catch (error) {
    elements.dialogError.textContent = String(error.message || error).replaceAll("_", " ");
    elements.dialogError.classList.remove("hidden");
  }
}

async function revealAdvocateContact() {
  const item = state.selected;
  const reason = elements.contactRevealReason.value.trim();
  if (!item?.advocate_id) return;
  try {
    const result = await api(`/admin/advocates/${item.advocate_id}/contact-reveal`, {
      method: "POST", body: JSON.stringify({ reason }),
    });
    showToast(`Advocate contact: ${result.phone || "No phone"} · ${result.email || "No email"}`);
  } catch (error) {
    elements.dialogError.textContent = String(error.message || error).replaceAll("_", " ");
    elements.dialogError.classList.remove("hidden");
  }
}

async function recordContact() {
  const item = state.selected;
  if (!item) return;
  elements.recordContact.disabled = true;
  try {
    const result = await api(`/admin/fulfillments/${item.booking_id}/contact-events`, {
      method: "POST",
      body: JSON.stringify({
        audience: elements.contactAudience.value,
        channel: elements.contactChannel.value,
        outcome: elements.contactOutcome.value,
        notes: elements.contactNotes.value.trim(),
        follow_up_due_at: elements.contactFollowUp.value || null,
      }),
    });
    item.contact_events = [result.event, ...(item.contact_events || [])];
    elements.contactNotes.value = "";
    elements.contactFollowUp.value = "";
    renderContactHistory(item.contact_events);
    showToast("Manual contact event recorded.");
  } catch (error) {
    elements.dialogError.textContent = String(error.message || error).replaceAll("_", " ");
    elements.dialogError.classList.remove("hidden");
  } finally {
    elements.recordContact.disabled = false;
  }
}

async function registerAdvocate(event) {
  event.preventDefault();
  elements.advocateSubmit.disabled = true;
  elements.advocateError.classList.add("hidden");
  try {
    await api("/admin/advocates", {
      method: "POST",
      body: JSON.stringify({
        name: elements.advocateName.value.trim(),
        bar_registration_number: elements.advocateRegistration.value.trim(),
        email: elements.advocateEmail.value.trim(),
        phone: elements.advocatePhone.value.trim(),
        category: elements.advocateCategory.value.trim(),
        district: elements.advocateDistrict.value.trim(),
        languages: elements.advocateLanguages.value.trim(),
        operator_notes: elements.advocateNotes.value.trim(),
      }),
    });
    elements.advocateForm.reset();
    await loadAdvocates();
    showToast("Advocate registered and available for assignment.");
  } catch (error) {
    elements.advocateError.textContent = String(error.message || error).replaceAll("_", " ");
    elements.advocateError.classList.remove("hidden");
  } finally {
    elements.advocateSubmit.disabled = false;
  }
}

async function loadAdvocates() {
  const result = await api("/admin/advocates");
  state.advocates = result.items || [];
}

async function loadAppointments() {
  elements.refreshButton.disabled = true;
  showQueueError("");
  try {
    const [queue, workflow, advocates] = await Promise.all([
      api("/admin/fulfillments?limit=200"),
      Object.keys(state.transitions).length ? Promise.resolve(null) : api("/admin/fulfillment-workflow"),
      api("/admin/advocates"),
    ]);
    state.items = queue.items || [];
    state.advocates = advocates.items || [];
    if (workflow) state.transitions = workflow.transitions || {};
    updateSummary();
    renderQueue();
    elements.lastUpdated.textContent = `Last refreshed ${new Intl.DateTimeFormat("en-IN", { timeStyle: "short" }).format(new Date())} · ${state.items.length} records`;
  } catch (error) {
    showQueueError(error.message || "Unable to load appointments.");
  } finally {
    elements.refreshButton.disabled = false;
  }
}

function initialise() {
  Object.assign(elements, {
    rows: byId("appointment-rows"), emptyState: byId("empty-state"),
    statusFilter: byId("status-filter"), queueSearch: byId("queue-search"),
    refreshButton: byId("refresh-button"), lastUpdated: byId("last-updated"),
    queueError: byId("queue-error"), countUnassigned: byId("count-unassigned"),
    countAssigned: byId("count-assigned"), countConfirmed: byId("count-confirmed"),
    countAttention: byId("count-attention"), dialog: byId("appointment-dialog"),
    dialogTitle: byId("dialog-title"), dialogBookingId: byId("dialog-booking-id"),
    dialogContext: byId("dialog-context"), dialogStatus: byId("dialog-status"),
    dialogAdvocate: byId("dialog-advocate"), dialogNotes: byId("dialog-notes"),
    dialogDate: byId("dialog-date"), dialogSlot: byId("dialog-slot"),
    rescheduleFields: byId("reschedule-fields"), dialogError: byId("dialog-error"),
    dialogSubmit: byId("dialog-submit"), toast: byId("toast"),
    briefEmpty: byId("brief-empty"), briefDetails: byId("brief-details"),
    briefSummary: byId("brief-summary"), briefStage: byId("brief-stage"),
    briefDates: byId("brief-dates"), briefOutcome: byId("brief-outcome"),
    briefUrgency: byId("brief-urgency"), briefOpposingParty: byId("brief-opposing-party"),
    briefDocuments: byId("brief-documents"), briefConsent: byId("brief-consent"),
    contactRevealReason: byId("contact-reveal-reason"),
    revealClientContact: byId("reveal-client-contact"),
    revealedClientContact: byId("revealed-client-contact"),
    revealAdvocateContact: byId("reveal-advocate-contact"),
    contactAudience: byId("contact-audience"), contactChannel: byId("contact-channel"),
    contactOutcome: byId("contact-outcome"), contactFollowUp: byId("contact-follow-up"),
    contactNotes: byId("contact-notes"), recordContact: byId("record-contact"),
    contactHistory: byId("contact-history"), advocateForm: byId("advocate-form"),
    advocateName: byId("advocate-name"), advocateRegistration: byId("advocate-registration"),
    advocateEmail: byId("advocate-email"), advocatePhone: byId("advocate-phone"),
    advocateCategory: byId("advocate-category"), advocateDistrict: byId("advocate-district"),
    advocateLanguages: byId("advocate-languages"), advocateNotes: byId("advocate-notes"),
    advocateError: byId("advocate-error"), advocateSubmit: byId("advocate-submit"),
  });

  elements.statusFilter.addEventListener("change", renderQueue);
  elements.queueSearch.addEventListener("input", renderQueue);
  elements.refreshButton.addEventListener("click", loadAppointments);
  elements.dialogStatus.addEventListener("change", updateDialogRequirements);
  elements.revealClientContact.addEventListener("click", revealClientContact);
  elements.revealAdvocateContact.addEventListener("click", revealAdvocateContact);
  elements.recordContact.addEventListener("click", recordContact);
  elements.advocateForm.addEventListener("submit", registerAdvocate);
  byId("dialog-close").addEventListener("click", closeDialog);
  byId("dialog-cancel").addEventListener("click", closeDialog);
  byId("appointment-form").addEventListener("submit", saveAppointment);
  elements.dialog.addEventListener("click", (event) => {
    if (event.target === elements.dialog) closeDialog();
  });

  loadAppointments();
  window.setInterval(() => {
    if (!elements.dialog.open && document.visibilityState === "visible") loadAppointments();
  }, 60_000);
}

document.addEventListener("DOMContentLoaded", initialise);
