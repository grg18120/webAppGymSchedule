(function () {
  var modalEl = document.getElementById("slotEditModal");
  if (!modalEl) return;

  var meta = modalEl.querySelector("[data-slot-meta]");
  var statusEl = modalEl.querySelector("[data-slot-status]");
  var instructorEl = modalEl.querySelector("[data-slot-instructor]");
  var staffEl = modalEl.querySelector("[data-slot-staff]");
  var clientEl = modalEl.querySelector("[data-slot-client]");
  var clientCopy = modalEl.querySelector("[data-slot-client-copy]");
  var editForm = modalEl.querySelector("[data-slot-edit-form]");
  var addForm = modalEl.querySelector("[data-slot-add-form]");
  var addHint = modalEl.querySelector("[data-slot-add-hint]");
  var addSelect = modalEl.querySelector("#slot_add_client");
  var clientsList = modalEl.querySelector("[data-slot-clients]");
  var startHour = modalEl.querySelector("#slot_start_hour");
  var startMinute = modalEl.querySelector("#slot_start_minute");
  var endHour = modalEl.querySelector("#slot_end_hour");
  var endMinute = modalEl.querySelector("#slot_end_minute");
  var positionInput = modalEl.querySelector("#slot_position_count");
  var bookForm = modalEl.querySelector("[data-slot-book-form]");
  var cancelOwnForm = modalEl.querySelector("[data-slot-cancel-own-form]");
  var deleteForm = modalEl.querySelector("[data-slot-delete-form]");
  var cancelAllForm = modalEl.querySelector("[data-slot-cancel-all-form]");
  var deleteBookedForm = modalEl.querySelector("[data-slot-delete-booked-form]");

  function setHidden(node, hidden) {
    if (!node) return;
    node.hidden = hidden;
  }

  function timelineNext() {
    return modalEl.getAttribute("data-timeline-next") || "";
  }

  function ensureOption(select, value) {
    if (!select) return;
    var raw = String(value);
    for (var i = 0; i < select.options.length; i += 1) {
      if (select.options[i].value === raw) {
        select.value = raw;
        return;
      }
    }
    var option = document.createElement("option");
    option.value = raw;
    option.textContent = raw.length === 1 ? "0" + raw : raw;
    select.appendChild(option);
    select.value = raw;
  }

  function setFormAction(form, path) {
    if (!form || !path) return;
    form.action = path;
  }

  function renderClients(slot) {
    if (!clientsList) return;
    clientsList.innerHTML = "";
    if (!slot.clients || !slot.clients.length) {
      var empty = document.createElement("li");
      empty.className = "slot-edit-clients__empty";
      empty.textContent = slot.is_past
        ? "No client has made a reservation"
        : "No client yet";
      clientsList.appendChild(empty);
      return;
    }
    slot.clients.forEach(function (client) {
      var item = document.createElement("li");
      item.className = "slot-edit-clients__item";
      var name = document.createElement("span");
      name.textContent = client.name;
      item.appendChild(name);
      if (slot.can_manage && !slot.is_past) {
        var form = document.createElement("form");
        form.method = "POST";
        form.action = slot.unassign_url;
        form.className = "slot-edit-clients__remove";
        var next = document.createElement("input");
        next.type = "hidden";
        next.name = "next";
        next.value = timelineNext();
        var clientId = document.createElement("input");
        clientId.type = "hidden";
        clientId.name = "client_id";
        clientId.value = String(client.id);
        var button = document.createElement("button");
        button.type = "submit";
        button.className = "btn btn-outline-danger tap-target";
        button.textContent = "Remove";
        form.appendChild(next);
        form.appendChild(clientId);
        form.appendChild(button);
        item.appendChild(form);
      }
      clientsList.appendChild(item);
    });
  }

  function filterAddClients(slot) {
    if (!addSelect) return;
    var booked = {};
    (slot.clients || []).forEach(function (client) {
      booked[String(client.id)] = true;
    });
    var available = 0;
    Array.prototype.forEach.call(addSelect.options, function (option) {
      if (!option.value) return;
      var taken = Boolean(booked[option.value]);
      option.hidden = taken;
      option.disabled = taken;
      if (!taken) available += 1;
    });
    addSelect.value = "";
    var full = slot.booked_count >= slot.position_count;
    setHidden(addForm, full || slot.is_past || !slot.can_manage);
    setHidden(addHint, !(full && slot.can_manage && !slot.is_past));
    if (!available) {
      setHidden(addForm, true);
    }
  }

  modalEl.addEventListener("show.bs.modal", function (event) {
    var trigger = event.relatedTarget;
    if (!trigger) return;
    var raw = trigger.getAttribute("data-slot");
    if (!raw) return;
    var slot;
    try {
      slot = JSON.parse(raw);
    } catch (err) {
      return;
    }
    var nextInput = timelineNext();
    if (meta) meta.textContent = slot.date_label + " · " + slot.time_label;
    if (statusEl) {
      statusEl.textContent =
        slot.status_label + " · Positions: " + slot.booked_count + "/" + slot.position_count;
    }
    if (instructorEl) instructorEl.textContent = "Instructor: " + slot.instructor;
    setHidden(staffEl, !slot.can_manage);
    setHidden(clientEl, slot.can_manage);
    if (clientCopy) {
      clientCopy.textContent = slot.can_book
        ? "This session has a free position."
        : slot.can_cancel_own
          ? "You have a place on this session."
          : "This session is full or already on your list.";
    }
    setFormAction(editForm, slot.edit_url);
    setFormAction(addForm, slot.assign_url);
    setFormAction(bookForm, slot.book_url);
    setFormAction(cancelOwnForm, slot.cancel_url);
    setFormAction(deleteForm, slot.remove_url);
    setFormAction(cancelAllForm, slot.cancel_url);
    setFormAction(deleteBookedForm, slot.delete_url);
    ensureOption(startHour, slot.start_hour);
    ensureOption(startMinute, slot.start_minute);
    ensureOption(endHour, slot.end_hour);
    ensureOption(endMinute, slot.end_minute);
    if (positionInput) {
      positionInput.value = slot.position_count;
      positionInput.min = String(Math.max(1, slot.booked_count || 0));
    }
    renderClients(slot);
    filterAddClients(slot);
    setHidden(bookForm, !slot.can_book);
    setHidden(cancelOwnForm, !slot.can_cancel_own);
    setHidden(deleteForm, !slot.can_delete);
    setHidden(cancelAllForm, !slot.can_cancel_all);
    setHidden(deleteBookedForm, !slot.can_delete_booked);
    modalEl.querySelectorAll('input[name="next"]').forEach(function (input) {
      input.value = nextInput;
    });
  });
})();
