"use strict";

const TERMINAL_STATUSES = new Set(["COMPLETED", "REFUNDED", "CANCELLED"]);
const ACTIVE_STATUSES = new Set([
  "UNASSIGNED",
  "ASSIGNED",
  "CONFIRMED",
  "RESCHEDULE_REQUIRED",
  "REFUND_REVIEW",
  "NO_SHOW",
]);

const state = {
  items: [],
  transitions: {},
  selected: null,
};

const elements = {};

function byId(id) {
  return document.getElementById(id);
}

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function displayStatus(value) {
  return String(value || "UNKNOWN").replaceAll("_", " ");
}

function maskPhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  if (!digits) return "Not available";
  return `••••••${digits.slice(-4)}`;
}

function formatDate(value) {
  if (!value) return "—";
  const parts = String(value).split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(parts[0], parts[1] - 1, parts[2]));
}

function formatTimestamp(value) {
  if (!value) return "Not set";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not set";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
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
  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "same-origin",
  });
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
    item.booking_id,
    item.case_id,
    item.name,
    item.category,
    item.subcategory,
    item.assigned_to,
    item.fulfillment_status,
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

  const clientCell = appendTwoLineCell(row, item.name || "Client", maskPhone(item.whatsapp_id));
  const digits = String(item.whatsapp_id || "").replace(/\D/g, "");
  if (digits) {
    const message = `Hello ${item.name || ""}, this is NyaySetu regarding your consultation booking #${item.booking_id} on ${formatDate(item.date)} at ${item.slot || "the selected time"}.`;
    const contact = node("a", "contact-link", "Open WhatsApp");
    contact.href = `https://wa.me/${digits}?text=${encodeURIComponent(message)}`;
    contact.target = "_blank";
    contact.rel = "noopener noreferrer";
    clientCell.append(contact);
  }

  appendTwoLineCell(row, item.category || "Other legal issue", item.subcategory || "");
  appendTwoLineCell(row, item.assigned_to || "Not assigned", `Payment: ${displayStatus(item.payment_status)}`);

  const statusCell = node("td");
  statusCell.append(node("span", `status status-${item.fulfillment_status}`, displayStatus(item.fulfillment_status)));
  if (item.operator_notes) statusCell.append(node("span", "cell-secondary", item.operator_notes));
  row.append(statusCell);

  const overdue = item.sla_due_at && new Date(item.sla_due_at).getTime() < Date.now() && !TERMINAL_STATUSES.has(item.fulfillment_status);
  appendTwoLineCell(row, formatTimestamp(item.sla_due_at), overdue ? "Attention overdue" : "", overdue ? "sla-overdue" : "");

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
    const option = node("option", "", value === current ? `${displayStatus(value)} (no status change)` : displayStatus(value));
    option.value = value;
    return option;
  }));
}

function updateDialogRequirements() {
  const status = elements.dialogStatus.value;
  const notesRequired = ["COMPLETED", "NO_SHOW", "RESCHEDULE_REQUIRED", "REFUND_REVIEW", "REFUNDED", "CANCELLED"].includes(status);
  elements.dialogNotes.required = notesRequired;
  const rescheduling = status === "RESCHEDULE_REQUIRED";
  elements.rescheduleFields.classList.toggle("hidden", !rescheduling);
}

function openDialog(item) {
  state.selected = item;
  elements.dialogBookingId.value = item.booking_id;
  elements.dialogTitle.textContent = `Booking #${item.booking_id}`;
  elements.dialogContext.textContent = `${item.name || "Client"} · ${formatDate(item.date)} · ${item.slot || "Time not set"} · ${item.category || "Legal consultation"}`;
  elements.dialogAssignedTo.value = item.assigned_to || "";
  elements.dialogNotes.value = item.operator_notes || "";
  elements.dialogDate.value = "";
  elements.dialogSlot.value = "";
  elements.dialogError.textContent = "";
  elements.dialogError.classList.add("hidden");
  populateStatusOptions(item);
  updateDialogRequirements();
  elements.dialogStatus.disabled = TERMINAL_STATUSES.has(item.fulfillment_status);
  elements.dialogAssignedTo.disabled = TERMINAL_STATUSES.has(item.fulfillment_status);
  elements.dialogNotes.disabled = TERMINAL_STATUSES.has(item.fulfillment_status);
  elements.dialogSubmit.classList.toggle("hidden", TERMINAL_STATUSES.has(item.fulfillment_status));
  elements.dialog.showModal();
}

function closeDialog() {
  if (elements.dialog.open) elements.dialog.close();
  state.selected = null;
}

async function saveAppointment(event) {
  event.preventDefault();
  const item = state.selected;
  if (!item) return;

  const status = elements.dialogStatus.value;
  const payload = {
    status,
    assigned_to: elements.dialogAssignedTo.value.trim(),
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
      method: "PATCH",
      body: JSON.stringify(payload),
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

async function loadAppointments() {
  elements.refreshButton.disabled = true;
  showQueueError("");
  try {
    const [queue, workflow] = await Promise.all([
      api("/admin/fulfillments?limit=200"),
      Object.keys(state.transitions).length ? Promise.resolve(null) : api("/admin/fulfillment-workflow"),
    ]);
    state.items = queue.items || [];
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
    rows: byId("appointment-rows"),
    emptyState: byId("empty-state"),
    statusFilter: byId("status-filter"),
    queueSearch: byId("queue-search"),
    refreshButton: byId("refresh-button"),
    lastUpdated: byId("last-updated"),
    queueError: byId("queue-error"),
    countUnassigned: byId("count-unassigned"),
    countAssigned: byId("count-assigned"),
    countConfirmed: byId("count-confirmed"),
    countAttention: byId("count-attention"),
    dialog: byId("appointment-dialog"),
    dialogTitle: byId("dialog-title"),
    dialogBookingId: byId("dialog-booking-id"),
    dialogContext: byId("dialog-context"),
    dialogStatus: byId("dialog-status"),
    dialogAssignedTo: byId("dialog-assigned-to"),
    dialogNotes: byId("dialog-notes"),
    dialogDate: byId("dialog-date"),
    dialogSlot: byId("dialog-slot"),
    rescheduleFields: byId("reschedule-fields"),
    dialogError: byId("dialog-error"),
    dialogSubmit: byId("dialog-submit"),
    toast: byId("toast"),
  });

  elements.statusFilter.addEventListener("change", renderQueue);
  elements.queueSearch.addEventListener("input", renderQueue);
  elements.refreshButton.addEventListener("click", loadAppointments);
  elements.dialogStatus.addEventListener("change", updateDialogRequirements);
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
