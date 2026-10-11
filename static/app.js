"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { date: "", rooms: [], bookings: [], mobileRoom: 1, selected: null,
  serverEpoch: Date.now(), syncedAt: performance.now(), loading: true, failed: false,
  request: 0, pending: false, controller: null };
const icon = (name) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`); svg.append(use); svg.setAttribute("aria-hidden", "true"); return svg;
};
const el = (tag, className, text) => {
  const element = document.createElement(tag); if (className) element.className = className;
  if (text !== undefined) element.textContent = text; return element;
};
const toMinutes = (time) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3, 5));
const hhmm = (minute) => `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
const currentTime = () => new Date(state.serverEpoch + performance.now() - state.syncedAt);
const seoul = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).formatToParts(currentTime()).map(p => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minute: Number(parts.hour) * 60 + Number(parts.minute), second: Number(parts.second), clock: `${parts.hour}:${parts.minute}` };
};
const dateObject = (day) => new Date(`${day}T12:00:00+09:00`);
const dateLabel = (day) => new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(dateObject(day));
const shiftDate = (day, offset) => {
  const date = dateObject(day); date.setUTCDate(date.getUTCDate() + offset);
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
};
const isPast = (day, minute) => new Date(`${day}T${hhmm(minute)}:00+09:00`).getTime() < currentTime().getTime();

async function api(path, options = {}) {
  const controller = new AbortController();
  const externalSignal = options.signal;
  const abort = () => controller.abort();
  if (externalSignal?.aborted) controller.abort();
  externalSignal?.addEventListener("abort", abort, { once: true });
  const timer = setTimeout(abort, 12000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal, headers: { "Content-Type": "application/json", ...options.headers } });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) { const error = new Error(typeof data.detail === "string" ? data.detail : "입력 내용을 다시 확인해 주세요."); error.status = response.status; throw error; }
    return data;
  } catch (error) {
    if (!error.status && !externalSignal?.aborted) error.message = "서버에 연결하지 못했어요. 연결 상태를 확인하고 다시 시도해 주세요.";
    throw error;
  } finally { clearTimeout(timer); externalSignal?.removeEventListener("abort", abort); }
}

function statusMessage(message, type = "", retry = false) {
  const area = $("#status-area"); area.replaceChildren();
  if (!message) return;
  const box = el("div", `status-message ${type}`); box.append(el("span", "", message));
  if (retry) { const button = el("button", "", "다시 불러오기"); button.type = "button"; button.addEventListener("click", () => loadSchedule(state.date)); box.append(button); }
  area.append(box);
}
let toastTimer;
function toast(message, error = false) {
  const box = $("#toast"); box.textContent = message; box.className = `toast${error ? " error" : ""}`; box.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, 6000);
}
function option(value, text) { const item = el("option", "", text); item.value = value; return item; }

async function loadSchedule(day = "", quiet = false) {
  const sequence = ++state.request;
  state.controller?.abort(); const controller = new AbortController(); state.controller = controller;
  if (day && day !== state.date && !quiet) {
    $("#board").replaceChildren(el("div", "initial-loading", "회의실 일정을 불러오고 있어요."));
    $("#booking-count").textContent = "";
  }
  if (day) { state.date = day; $("#selected-date").value = day; $("#schedule-title").textContent = dateLabel(day); }
  if (!quiet) {
    state.loading = true; $("#board").classList.add("is-loading"); $("#board").inert = true;
    $("#board").setAttribute("aria-busy", "true"); $("#add-booking").disabled = true;
    statusMessage("최신 일정을 불러오고 있어요.", "loading");
  }
  try {
    const data = await api(`/api/schedule${day ? `?date=${encodeURIComponent(day)}` : ""}`, { signal: controller.signal });
    if (sequence !== state.request) return;
    state.serverEpoch = Date.parse(data.server_time); state.syncedAt = performance.now();
    state.date = data.date; state.rooms = data.rooms; state.bookings = data.reservations; state.failed = false;
    $("#selected-date").value = data.date; $("#schedule-title").textContent = dateLabel(data.date);
    $("#booking-count").textContent = `예약 ${state.bookings.length}건`;
    if (!state.rooms.some(r => r.id === state.mobileRoom)) state.mobileRoom = state.rooms[0].id;
    const mobile = $("#mobile-room"); mobile.replaceChildren(...state.rooms.map(r => option(r.id, `${r.name} · ${r.capacity}인실`))); mobile.value = state.mobileRoom;
    if (!$("#booking-dialog").open) $("#form-room").replaceChildren(...state.rooms.map(r => option(r.id, `${r.name} · 최대 ${r.capacity}명`)));
    const signature = JSON.stringify([data.date, data.reservations, state.mobileRoom]);
    if (!quiet || signature !== state.renderSignature || !$(".board-body")) { renderBoard(); state.renderSignature = signature; }
    statusMessage(state.bookings.length ? "" : "아직 예약이 없는 날이에요. 원하는 공간과 시간을 먼저 골라보세요.");
    updateClock();
  } catch (error) {
    if (sequence !== state.request || controller.signal.aborted) return;
    state.failed = true; statusMessage(error.message, "error", true);
    if (!$(".board-body")) $("#board").replaceChildren(el("div", "initial-loading", "연결이 복구되면 회의실 일정을 확인할 수 있어요."));
  } finally {
    if (sequence === state.request) {
      state.loading = false; $("#board").classList.toggle("is-loading", state.failed);
      $("#board").inert = state.failed; $("#board").setAttribute("aria-busy", "false");
      $("#add-booking").disabled = state.failed || !state.rooms.length;
    }
  }
}

function focusKey(element) {
  if (element?.dataset.booking) return `[data-booking="${element.dataset.booking}"]`;
  if (element?.dataset.slotRoom) return `[data-slot-room="${element.dataset.slotRoom}"][data-minute="${element.dataset.minute}"]`;
  return element?.id ? `#${element.id}` : null;
}
function renderBoard() {
  const active = document.activeElement; const key = focusKey(active); const hadBoardFocus = $("#board").contains(active);
  const board = $("#board"); const header = el("div", "board-header"); header.append(el("div", "time-heading", "TIME"));
  const body = el("div", "board-body"); const times = el("div", "time-column"); times.setAttribute("aria-hidden", "true");
  for (let minute = 540; minute <= 1080; minute += 60) {
    const label = el("span", `time-label${minute === 540 ? " first" : ""}`, hhmm(minute)); label.style.top = `${(minute - 540) / 540 * 100}%`; times.append(label);
  }
  body.append(times);
  for (const room of state.rooms) {
    const classes = `room-${room.color}${room.id === state.mobileRoom ? " mobile-active" : ""}`;
    const roomHeader = el("div", `room-header ${classes}`); roomHeader.append(el("div", "room-number", `2F · MEETING ROOM 0${room.id}`));
    const row = el("div", "room-title-row"); row.append(el("h3", "", room.name));
    const capacity = el("span", "capacity"); capacity.append(icon("user"), document.createTextNode(`${room.capacity}인실`)); row.append(capacity); roomHeader.append(row);
    roomHeader.append(el("p", "room-description", room.description));
    const facilities = el("div", "facilities"); room.facilities.forEach(f => facilities.append(el("span", "facility", f))); roomHeader.append(facilities); header.append(roomHeader);
    const track = el("div", `room-track ${classes}`); track.setAttribute("aria-label", `${room.name} 하루 일정`);
    const bookings = state.bookings.filter(b => b.room_id === room.id);
    for (let minute = 540; minute < 1080; minute += 30) {
      const slot = el("button", `slot${minute % 60 === 0 ? " hour-start" : ""}`); slot.type = "button";
      slot.style.top = `${(minute - 540) / 540 * 100}%`; slot.dataset.slotRoom = room.id; slot.dataset.minute = minute;
      const occupied = bookings.some(b => toMinutes(b.start_time) <= minute && toMinutes(b.end_time) > minute);
      slot.dataset.occupied = String(occupied); slot.disabled = occupied || isPast(state.date, minute);
      if (occupied) { slot.setAttribute("aria-hidden", "true"); slot.tabIndex = -1; }
      slot.setAttribute("aria-label", `${room.name} ${hhmm(minute)}~${hhmm(minute + 30)} 예약${isPast(state.date, minute) ? " (지난 시간)" : ""}`);
      slot.classList.toggle("past", isPast(state.date, minute));
      const label = el("span", "slot-label"); label.append(icon("plus"), document.createTextNode("예약하기")); slot.append(label);
      slot.addEventListener("click", () => openBooking(room.id, minute)); track.append(slot);
    }
    for (const booking of bookings) {
      const start = toMinutes(booking.start_time), end = toMinutes(booking.end_time);
      const button = el("button", `booking${end - start === 30 ? " compact" : ""}`); button.type = "button";
      button.style.top = `calc(${(start - 540) / 540 * 100}% + 3px)`;
      button.style.height = `calc(${(end - start) / 540 * 100}% - 6px)`;
      button.dataset.booking = booking.id; button.setAttribute("aria-pressed", String(state.selected === booking.id));
      button.setAttribute("aria-label", `${room.name}, ${booking.start_time}부터 ${booking.end_time}, ${booking.title}, ${booking.organizer}, ${booking.attendees}명. 예약 상세 보기`);
      button.append(el("span", "booking-time", `${booking.start_time} – ${booking.end_time}`), el("span", "booking-title", booking.title));
      if (end - start >= 60) button.append(el("span", "booking-person", `${booking.organizer} · ${booking.attendees}명`));
      button.addEventListener("click", () => openDetail(booking)); track.append(button);
    }
    body.append(track);
  }
  const nowLine = el("div", "now-line"); nowLine.id = "now-line"; nowLine.append(el("span", "now-label")); nowLine.setAttribute("aria-hidden", "true"); body.append(nowLine);
  board.replaceChildren(header, body); updateClock();
  if (hadBoardFocus && key) $(key)?.focus({ preventScroll: true });
}

function updateClock() {
  const now = seoul(); $("#seoul-clock").textContent = `서울 ${now.clock}`;
  const line = $("#now-line");
  if (line) {
    line.hidden = state.date !== now.date || now.minute < 540 || now.minute >= 1080;
    line.style.top = `${(now.minute + now.second / 60 - 540) / 540 * 100}%`;
    line.firstChild.textContent = now.clock;
  }
  document.querySelectorAll(".slot").forEach(slot => {
    const past = isPast(state.date, Number(slot.dataset.minute)); slot.classList.toggle("past", past);
    slot.disabled = past || slot.dataset.occupied === "true";
  });
}

function showDialog(dialog) {
  dialog.returnKey = focusKey(document.activeElement); dialog.returnElement = document.activeElement;
  dialog.showModal();
}
document.querySelectorAll("dialog").forEach(dialog => {
  dialog.addEventListener("cancel", event => { if (state.pending) event.preventDefault(); });
  dialog.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const controls = [...dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]')].filter(control => control.getClientRects().length);
    if (!controls.length) { event.preventDefault(); return; }
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  dialog.addEventListener("close", () => {
    if (dialog.id === "detail-dialog") {
      state.selected = null; document.querySelectorAll(".booking").forEach(b => b.setAttribute("aria-pressed", "false"));
    }
    const target = dialog.returnElement?.isConnected ? dialog.returnElement : (dialog.returnKey ? $(dialog.returnKey) : null);
    if (target && !target.disabled) target.focus({ preventScroll: true });
    else if (!document.querySelector("dialog[open]")) $("#add-booking").focus({ preventScroll: true });
  });
});
document.querySelectorAll(".close-dialog").forEach(button => button.addEventListener("click", () => { if (!state.pending) button.closest("dialog").close(); }));
document.querySelectorAll(".guide-trigger").forEach(button => button.addEventListener("click", () => showDialog($("#guide-dialog"))));

function setPending(pending, dialog) {
  state.pending = pending;
  dialog.querySelectorAll("button,input,select").forEach(control => { control.disabled = pending; });
  dialog.setAttribute("aria-busy", String(pending));
}
function setError(target, message) { target.textContent = message; target.hidden = !message; }
function updateCapacity() {
  const room = state.rooms.find(r => r.id === Number($("#form-room").value));
  if (room) { $("#form-attendees").max = room.capacity; $("#capacity-hint").textContent = `${room.facilities.join(" · ")} / 최대 ${room.capacity}명`; }
}
function updateEnds(preferred) {
  const start = $("#form-start").value, end = $("#form-end"); const previous = preferred ?? end.value; end.replaceChildren();
  if (!start) { end.append(option("", "시간을 선택해 주세요")); return; }
  for (let minute = toMinutes(start) + 30; minute <= Math.min(1080, toMinutes(start) + 120); minute += 30) end.append(option(hhmm(minute), `${hhmm(minute)} (${minute - toMinutes(start)}분)`));
  if ([...end.options].some(o => o.value === previous)) end.value = previous;
}
function updateStarts(preferred) {
  const day = $("#form-date").value, start = $("#form-start"); const previous = preferred ?? start.value; start.replaceChildren();
  if (day) for (let minute = 540; minute < 1080; minute += 30) if (!isPast(day, minute)) start.append(option(hhmm(minute), hhmm(minute)));
  if (!start.options.length) start.append(option("", "예약 가능한 시간 없음"));
  if ([...start.options].some(o => o.value === previous)) start.value = previous;
  updateEnds();
}
function openBooking(roomId = state.mobileRoom, minute = null) {
  if (state.loading || state.failed || !state.rooms.length) return;
  const form = $("#booking-form"); form.reset(); setError($("#form-error"), "");
  $("#form-room").replaceChildren(...state.rooms.map(r => option(r.id, `${r.name} · 최대 ${r.capacity}명`)));
  $("#form-room").value = roomId; const now = seoul(); let day = state.date < now.date ? now.date : state.date;
  if (minute === null && day === now.date && isPast(day, 1050)) day = shiftDate(day, 1);
  $("#form-date").min = now.date; $("#form-date").value = day;
  updateCapacity(); updateStarts(minute !== null ? hhmm(minute) : "");
  if (minute !== null) updateEnds(hhmm(minute + 30));
  showDialog($("#booking-dialog")); $("#form-title").focus();
}
$("#form-room").addEventListener("change", updateCapacity);
$("#form-date").addEventListener("change", () => updateStarts());
$("#form-start").addEventListener("change", () => updateEnds());
$("#add-booking").addEventListener("click", () => openBooking());
$("#booking-form").addEventListener("submit", async event => {
  event.preventDefault(); if (state.pending) return;
  const form = event.currentTarget; const payload = Object.fromEntries(new FormData(form));
  payload.room_id = Number(payload.room_id); payload.attendees = Number(payload.attendees);
  payload.title = payload.title.trim(); payload.organizer = payload.organizer.trim();
  if (!payload.title || !payload.organizer) { setError($("#form-error"), "회의 제목과 예약자 이름을 입력해 주세요."); $("#form-error").focus(); return; }
  if (isPast(payload.date, toMinutes(payload.start_time))) { setError($("#form-error"), "이미 지난 시간이에요. 앞으로의 시간을 선택해 주세요."); updateStarts(); return; }
  const dialog = $("#booking-dialog"); setPending(true, dialog); setError($("#form-error"), ""); $("#submit-booking").textContent = "예약 중…";
  try {
    const booking = await api("/api/reservations", { method: "POST", body: JSON.stringify(payload) });
    state.selected = booking.id;
    setPending(false, dialog); dialog.close();
    await loadSchedule(payload.date);
    toast(`${payload.start_time} 예약이 완료되었어요.`);
    $(`[data-booking="${booking.id}"]`)?.focus({ preventScroll: true });
  } catch (error) {
    setError($("#form-error"), error.message);
    if (error.status === 409) await loadSchedule(state.date, true);
    $("#form-error").focus();
  } finally {
    setPending(false, dialog); $("#submit-booking").replaceChildren(document.createTextNode("예약하기"), icon("arrow"));
  }
});

function openDetail(booking) {
  state.selected = booking.id;
  document.querySelectorAll(".booking").forEach(b => b.setAttribute("aria-pressed", String(Number(b.dataset.booking) === booking.id)));
  const room = state.rooms.find(r => r.id === booking.room_id);
  $("#detail-room").textContent = `${room.name} · ${room.capacity}인실`;
  $("#detail-heading").textContent = booking.title; $("#confirm-title").textContent = `${booking.title} · ${booking.start_time}–${booking.end_time}`;
  const list = $("#detail-list"); list.replaceChildren();
  for (const [label, value] of [["예약 날짜", dateLabel(booking.date)], ["이용 시간", `${booking.start_time} – ${booking.end_time} (${toMinutes(booking.end_time) - toMinutes(booking.start_time)}분)`], ["예약자", booking.organizer], ["참석 인원", `${booking.attendees}명`], ["시설", room.facilities.join(" · ")]]) list.append(el("dt", "", label), el("dd", "", value));
  setError($("#detail-error"), ""); showDialog($("#detail-dialog"));
}
$("#cancel-booking").addEventListener("click", () => { setError($("#cancel-error"), ""); showDialog($("#confirm-dialog")); });
$("#confirm-cancel").addEventListener("click", async () => {
  if (state.pending || state.selected === null) return;
  const id = state.selected; const cancelled = state.bookings.find(booking => booking.id === id);
  const dialog = $("#confirm-dialog"); setPending(true, dialog); setError($("#cancel-error"), ""); $("#confirm-cancel").textContent = "취소 중…";
  try {
    await api(`/api/reservations/${id}`, { method: "DELETE" });
    setPending(false, dialog); dialog.close(); $("#detail-dialog").close();
    await loadSchedule(state.date); toast("예약이 취소되었어요. 이 시간을 다시 예약할 수 있어요.");
    const freedSlot = cancelled && $(`[data-slot-room="${cancelled.room_id}"][data-minute="${toMinutes(cancelled.start_time)}"]`);
    if (freedSlot && !freedSlot.disabled) freedSlot.focus({ preventScroll: true });
    else $("#add-booking").focus({ preventScroll: true });
  } catch (error) {
    if (error.status === 404) {
      setPending(false, dialog); dialog.close(); $("#detail-dialog").close(); await loadSchedule(state.date); toast(error.message);
    } else setError($("#cancel-error"), error.message);
  } finally { setPending(false, dialog); $("#confirm-cancel").textContent = "예약 취소하기"; }
});

$("#prev-day").addEventListener("click", () => { if (state.date) loadSchedule(shiftDate(state.date, -1)); });
$("#next-day").addEventListener("click", () => { if (state.date) loadSchedule(shiftDate(state.date, 1)); });
$("#today").addEventListener("click", () => loadSchedule(seoul().date));
$("#selected-date").addEventListener("change", event => { if (event.target.value) loadSchedule(event.target.value); else event.target.value = state.date; });
$("#mobile-room").addEventListener("change", event => { state.mobileRoom = Number(event.target.value); renderBoard(); });
setInterval(updateClock, 10000);
setInterval(() => { if (!document.hidden && !state.pending && !state.loading) loadSchedule(state.date, true); }, 30000);
document.addEventListener("visibilitychange", () => { if (!document.hidden && !state.pending) loadSchedule(state.date, true); });
loadSchedule();
