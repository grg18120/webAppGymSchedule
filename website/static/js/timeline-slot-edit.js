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
  var addButton = modalEl.querySelector("[data-slot-add-client]");
  var clientsList = modalEl.querySelector("[data-slot-clients]");
  var clientIdsBox = modalEl.querySelector("[data-slot-client-ids]");
  var startHour = modalEl.querySelector("#slot_start_hour");
  var startMinute = modalEl.querySelector("#slot_start_minute");
  var endHour = modalEl.querySelector("#slot_end_hour");
  var endMinute = modalEl.querySelector("#slot_end_minute");
  var positionInput = modalEl.querySelector("#slot_position_count");
  var saveBtn = modalEl.querySelector("[data-slot-save]");
  var bookForm = modalEl.querySelector("[data-slot-book-form]");
  var cancelOwnForm = modalEl.querySelector("[data-slot-cancel-own-form]");
  var interestForm = modalEl.querySelector("[data-slot-interest-form]");
  var interestRemoveForm = modalEl.querySelector("[data-slot-interest-remove-form]");
  var interestedBox = modalEl.querySelector("[data-slot-interested]");
  var interestedList = modalEl.querySelector("[data-slot-interested-list]");
  var deleteForm = modalEl.querySelector("[data-slot-delete-form]");
  var cancelAllForm = modalEl.querySelector("[data-slot-cancel-all-form]");
  var deleteBookedForm = modalEl.querySelector("[data-slot-delete-booked-form]");
  var flashEl = modalEl.querySelector("[data-slot-flash]");
  var dialogEl = modalEl.querySelector(".modal-dialog");
  var currentTrigger = null;
  var currentSlot = null;
  var draftClients = [];

  function setHidden(node, hidden) {
    if (!node) return;
    node.hidden = hidden;
  }

  function timelineNext() {
    return modalEl.getAttribute("data-timeline-next") || "";
  }

  function showFlash(message, kind) {
    if (!flashEl) return;
    if (!message) {
      flashEl.hidden = true;
      flashEl.textContent = "";
      flashEl.className = "slot-edit-modal__flash alert mb-3";
      return;
    }
    flashEl.hidden = false;
    flashEl.textContent = message;
    flashEl.className =
      "slot-edit-modal__flash alert mb-3 " +
      (kind === "success" ? "alert-success" : "alert-danger");
  }

  function fieldMap() {
    return {
      start_hour: startHour,
      start_minute: startMinute,
      end_hour: endHour,
      end_minute: endMinute,
      position_count: positionInput,
      client_id: addSelect,
    };
  }

  function clearInvalid() {
    modalEl.querySelectorAll(".is-invalid").forEach(function (el) {
      el.classList.remove("is-invalid");
      el.removeAttribute("aria-invalid");
    });
  }

  function markInvalid(name) {
    var el = fieldMap()[name];
    if (el) {
      el.classList.add("is-invalid");
      el.setAttribute("aria-invalid", "true");
    }
    if (
      name === "start_hour" ||
      name === "start_minute" ||
      name === "end_hour" ||
      name === "end_minute"
    ) {
      var fieldset = modalEl.querySelector("[data-slot-time-fields]");
      if (fieldset) fieldset.classList.add("is-invalid");
    }
  }

  function shake(fields) {
    clearInvalid();
    (fields || []).forEach(markInvalid);
    if (!dialogEl) return;
    dialogEl.classList.remove("is-shake");
    void dialogEl.offsetWidth;
    dialogEl.classList.add("is-shake");
    dialogEl.addEventListener(
      "animationend",
      function () {
        dialogEl.classList.remove("is-shake");
      },
      { once: true }
    );
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

  function clockMinutes(hourEl, minuteEl) {
    var hour = Number(hourEl && hourEl.value);
    var minute = Number(minuteEl && minuteEl.value);
    if (hour === 24) return 24 * 60;
    return hour * 60 + minute;
  }

  function positionCount() {
    var count = positionInput ? Number(positionInput.value) : NaN;
    return Number.isInteger(count) ? count : NaN;
  }

  function updatePositionMin() {
    if (!positionInput) return;
    positionInput.min = String(Math.max(1, draftClients.length));
  }

  function writeClientIds() {
    if (!clientIdsBox) return;
    clientIdsBox.innerHTML = "";
    draftClients.forEach(function (client) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "client_id";
      input.value = String(client.id);
      clientIdsBox.appendChild(input);
    });
  }

  function renderClients() {
    if (!clientsList) return;
    clientsList.innerHTML = "";
    if (!draftClients.length) {
      var empty = document.createElement("li");
      empty.className = "slot-edit-clients__empty";
      empty.textContent =
        currentSlot && currentSlot.is_past
          ? "No client has made a reservation"
          : "No client yet";
      clientsList.appendChild(empty);
      return;
    }
    draftClients.forEach(function (client) {
      var item = document.createElement("li");
      item.className = "slot-edit-clients__item";
      var name = document.createElement("span");
      name.textContent = client.name;
      item.appendChild(name);
      if (currentSlot && currentSlot.can_manage && !currentSlot.is_past) {
        var removeWrap = document.createElement("div");
        removeWrap.className = "slot-edit-clients__remove";
        var button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-outline-danger tap-target";
        button.textContent = "Remove";
        button.setAttribute("aria-label", "Remove " + client.name);
        button.addEventListener("click", function () {
          draftClients = draftClients.filter(function (row) {
            return row.id !== client.id;
          });
          clearInvalid();
          showFlash("");
          renderClients();
          filterAddClients();
          writeClientIds();
          updatePositionMin();
        });
        removeWrap.appendChild(button);
        item.appendChild(removeWrap);
        item.addEventListener("mouseenter", function () {
          item.classList.add("is-hover");
        });
        item.addEventListener("mouseleave", function () {
          item.classList.remove("is-hover");
        });
      }
      clientsList.appendChild(item);
    });
  }

  function filterAddClients() {
    if (!addSelect) return;
    var booked = {};
    draftClients.forEach(function (client) {
      booked[String(client.id)] = true;
    });
    var available = 0;
    var current = addSelect.value;
    Array.prototype.forEach.call(addSelect.options, function (option) {
      if (!option.value) return;
      var taken = Boolean(booked[option.value]);
      option.disabled = taken;
      if (!taken) available += 1;
    });
    if (!current || booked[current]) addSelect.value = "";
    var count = positionCount();
    var full = Number.isInteger(count) && draftClients.length >= count;
    var locked = !currentSlot || !currentSlot.can_manage || currentSlot.is_past;
    setHidden(addForm, locked || full || !available);
    setHidden(
      addHint,
      !(full && currentSlot && currentSlot.can_manage && !currentSlot.is_past)
    );
  }

  function addDraftClient() {
    if (!addSelect || !addSelect.value) {
      showFlash("Choose a client.", "error");
      shake(["client_id"]);
      return;
    }
    var count = positionCount();
    if (Number.isInteger(count) && draftClients.length >= count) {
      showFlash("Increase positions before adding another client.", "error");
      shake(["position_count", "client_id"]);
      return;
    }
    var option = addSelect.options[addSelect.selectedIndex];
    draftClients.push({
      id: Number(option.value),
      name: option.textContent.replace(/^\s+|\s+$/g, ""),
    });
    showFlash("");
    clearInvalid();
    renderClients();
    filterAddClients();
    writeClientIds();
    updatePositionMin();
  }

  function validateSave() {
    var fields = [];
    if (
      startHour &&
      endHour &&
      !(clockMinutes(endHour, endMinute) > clockMinutes(startHour, startMinute))
    ) {
      fields.push("end_hour", "end_minute");
    }
    var count = positionCount();
    if (!Number.isInteger(count) || count < 1 || count > 20) {
      fields.push("position_count");
    } else if (count < draftClients.length) {
      fields.push("position_count");
    }
    return fields;
  }

  function invalidMessage(fields) {
    if (fields.indexOf("end_hour") !== -1 || fields.indexOf("end_minute") !== -1) {
      return "End time must be after start time.";
    }
    if (fields.indexOf("position_count") !== -1) {
      if (Number.isInteger(positionCount()) && positionCount() < draftClients.length) {
        return "Positions cannot be fewer than clients already booked.";
      }
      return "Positions must be a number from 1 to 20.";
    }
    if (fields.indexOf("client_id") !== -1) return "Choose a client.";
    return "Check the highlighted fields.";
  }

  function fillModal(slot) {
    currentSlot = slot;
    draftClients = (slot.clients || []).map(function (client) {
      return { id: client.id, name: client.name };
    });
    var nextInput = timelineNext();
    if (meta) meta.textContent = slot.date_label + " · " + slot.time_label;
    if (statusEl) {
      if (slot.viewer_is_client) {
        statusEl.textContent = slot.display_status_label || slot.status_label || "";
      } else {
        statusEl.textContent =
          slot.status_label + " · Positions: " + slot.booked_count + "/" + slot.position_count;
      }
    }
    if (instructorEl) instructorEl.textContent = "Instructor: " + slot.instructor;
    setHidden(staffEl, !slot.can_manage);
    setHidden(clientEl, slot.can_manage);
    setHidden(saveBtn, !slot.can_manage);
    if (clientCopy) {
      if (slot.booked_by_me) {
        clientCopy.textContent = "You booked this session.";
      } else if (slot.can_book) {
        clientCopy.textContent = "You have not booked this session.";
      } else if (slot.interested_by_me) {
        clientCopy.textContent = "This session is full. You registered interest.";
      } else if (slot.can_interest) {
        clientCopy.textContent = "This session is fully booked. You can register interest so staff can see you want a place.";
      } else {
        clientCopy.textContent = "This session is not available to book.";
      }
    }
    setFormAction(editForm, slot.edit_url);
    setFormAction(bookForm, slot.book_url);
    setFormAction(cancelOwnForm, slot.cancel_url);
    setFormAction(interestForm, slot.interest_url);
    setFormAction(interestRemoveForm, slot.interest_remove_url);
    setFormAction(deleteForm, slot.remove_url);
    setFormAction(cancelAllForm, slot.cancel_url);
    setFormAction(deleteBookedForm, slot.delete_url);
    ensureOption(startHour, slot.start_hour);
    ensureOption(startMinute, slot.start_minute);
    ensureOption(endHour, slot.end_hour);
    ensureOption(endMinute, slot.end_minute);
    if (positionInput) {
      positionInput.value = slot.position_count;
    }
    updatePositionMin();
    writeClientIds();
    renderClients();
    filterAddClients();
    renderInterested(slot);
    setHidden(bookForm, !slot.can_book);
    setHidden(cancelOwnForm, !slot.can_cancel_own);
    setHidden(interestForm, !(slot.can_interest && !slot.interested_by_me));
    setHidden(interestRemoveForm, !slot.interested_by_me);
    setHidden(deleteForm, !slot.can_delete);
    setHidden(cancelAllForm, !slot.can_cancel_all);
    setHidden(deleteBookedForm, !slot.can_delete_booked);
    modalEl.querySelectorAll('input[name="next"]').forEach(function (input) {
      input.value = nextInput;
    });
  }

  function renderInterested(slot) {
    if (!interestedList) return;
    interestedList.innerHTML = "";
    var rows = (slot && slot.interested) || [];
    rows.forEach(function (person) {
      var item = document.createElement("li");
      item.className = "slot-edit-clients__item";
      item.textContent = person.name;
      interestedList.appendChild(item);
    });
    setHidden(interestedBox, !(slot && slot.can_manage && rows.length));
  }

  function positionsShort(slot) {
    return String(slot.booked_count || 0) + "/" + String(slot.position_count || 1);
  }

  function renderSeats(trigger, slot) {
    var seats = trigger.querySelector("[data-slot-seats]");
    if (!seats) return;
    seats.innerHTML = "";
    var booked = slot.booked_count || 0;
    var total = slot.position_count || 1;
    for (var i = 0; i < total; i += 1) {
      var icon = document.createElement("i");
      icon.className =
        "fas fa-user timeline__seat " +
        (i < booked ? "timeline__seat--booked" : "timeline__seat--open");
      icon.setAttribute("aria-hidden", "true");
      seats.appendChild(icon);
    }
  }

  function fillTip(trigger, slot) {
    var tip = trigger.querySelector("[data-slot-tip]");
    if (!tip) return;
    var time = tip.querySelector("[data-slot-tip-time]");
    var instructor = tip.querySelector("[data-slot-tip-instructor]");
    var clients = tip.querySelector("[data-slot-tip-clients]");
    if (time) time.textContent = slot.time_label || "";
    if (instructor) instructor.textContent = slot.instructor || "";
    if (clients) {
      if (slot.clients && slot.clients.length) {
        clients.textContent = slot.clients
          .map(function (client) {
            return client.name;
          })
          .join(", ");
      } else {
        clients.textContent = slot.is_past
          ? "No client has made a reservation"
          : "No client yet";
      }
    }
  }

  function updateTrigger(slot, block) {
    if (!currentTrigger) return;
    currentTrigger.setAttribute("data-slot", JSON.stringify(slot));
    currentTrigger.classList.remove(
      "timeline__block--available",
      "timeline__block--booked",
      "timeline__block--cancelled",
      "timeline__block--partial"
    );
    var kind = slot.display_status || slot.status;
    if (kind) {
      currentTrigger.classList.add("timeline__block--" + kind);
    }
    var booked = slot.booked_count || 0;
    var total = slot.position_count || 1;
    if (!slot.viewer_is_client && booked > 0 && booked < total) {
      currentTrigger.classList.add("timeline__block--partial");
      var pct =
        typeof slot.booked_percent === "number"
          ? slot.booked_percent
          : (100 * booked) / total;
      currentTrigger.style.setProperty("--booked-pct", pct + "%");
    } else {
      currentTrigger.style.removeProperty("--booked-pct");
    }
    if (block && typeof block.top === "number") {
      currentTrigger.style.top = block.top + "%";
    }
    if (block && typeof block.height === "number") {
      currentTrigger.style.height = block.height + "%";
    }
    renderSeats(currentTrigger, slot);
    fillTip(currentTrigger, slot);
    var positions = currentTrigger.querySelector(".timeline__block-positions");
    if (positions && currentTrigger.querySelector("[data-slot-seats]")) {
      positions.textContent = slot.positions_short || positionsShort(slot);
    } else if (positions) {
      positions.textContent = slot.positions_label ||
        "Positions: " + slot.booked_count + "/" + slot.position_count;
    }
    var state = currentTrigger.querySelector("[data-slot-state]");
    if (state) {
      if (slot.booked_by_me) state.textContent = "Your booking";
      else if (slot.display_status_label === "Full" || (slot.is_full && !slot.booked_by_me))
        state.textContent = "Full";
      else state.textContent = "Open";
    }
    currentTrigger.classList.toggle("timeline__block--has-interest", Boolean(slot.has_interest));
    var flag = currentTrigger.querySelector("[data-interest-flag]");
    var panel = currentTrigger.querySelector("[data-interest-panel]");
    var list = currentTrigger.querySelector("[data-interest-list]");
    if (flag) flag.hidden = !slot.has_interest;
    if (panel && list) {
      list.innerHTML = "";
      (slot.interested || []).forEach(function (person) {
        var item = document.createElement("li");
        item.textContent = person.name;
        list.appendChild(item);
      });
      if (!slot.has_interest) panel.hidden = true;
    }
    var hit = currentTrigger.querySelector(".timeline__block-hit") || currentTrigger;
    var time = String(slot.time_label || "").replace(" – ", " to ");
    hit.setAttribute(
      "aria-label",
      (slot.display_status_label || slot.status_label) + " " + time + ". Click to open."
    );
  }

  modalEl.addEventListener("show.bs.modal", function (event) {
    var trigger = event.relatedTarget;
    if (!trigger) return;
    currentTrigger = trigger.closest(".timeline__block") || trigger;
    var raw = trigger.getAttribute("data-slot");
    if (!raw) return;
    var slot;
    try {
      slot = JSON.parse(raw);
    } catch (err) {
      return;
    }
    showFlash("");
    clearInvalid();
    fillModal(slot);
  });

  modalEl.addEventListener("hidden.bs.modal", function () {
    currentTrigger = null;
    currentSlot = null;
    draftClients = [];
    showFlash("");
    clearInvalid();
  });

  document.querySelectorAll(".timeline__block").forEach(function (block) {
    block.addEventListener("mouseenter", function () {
      block.classList.add("is-hover");
    });
    block.addEventListener("mouseleave", function () {
      block.classList.remove("is-hover");
    });
  });

  document.querySelectorAll("[data-interest-flag]").forEach(function (flag) {
    flag.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      var block = flag.closest(".timeline__block");
      var panel = block && block.querySelector("[data-interest-panel]");
      if (!panel) return;
      var open = panel.hidden;
      document.querySelectorAll("[data-interest-panel]").forEach(function (other) {
        other.hidden = true;
      });
      document.querySelectorAll("[data-interest-flag]").forEach(function (other) {
        other.setAttribute("aria-expanded", "false");
      });
      panel.hidden = !open;
      flag.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });

  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-interest-flag], [data-interest-panel]")) return;
    document.querySelectorAll("[data-interest-panel]").forEach(function (panel) {
      panel.hidden = true;
    });
    document.querySelectorAll("[data-interest-flag]").forEach(function (flag) {
      flag.setAttribute("aria-expanded", "false");
    });
  });


  if (addButton) {
    addButton.addEventListener("click", addDraftClient);
  }

  if (positionInput) {
    positionInput.addEventListener("input", function () {
      clearInvalid();
      filterAddClients();
    });
  }

  [startHour, startMinute, endHour, endMinute].forEach(function (el) {
    if (!el) return;
    el.addEventListener("change", function () {
      clearInvalid();
    });
  });

  if (editForm) {
    editForm.addEventListener("submit", function (event) {
      event.preventDefault();
      writeClientIds();
      var invalid = validateSave();
      if (invalid.length) {
        showFlash(invalidMessage(invalid), "error");
        shake(invalid);
        return;
      }
      var submitBtn = saveBtn || editForm.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      fetch(editForm.action, {
        method: "POST",
        body: new FormData(editForm),
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      })
        .then(function (response) {
          return response.json().then(function (data) {
            return data;
          });
        })
        .then(function (data) {
          if (!data.ok) {
            showFlash(data.message || "Could not save this session.", "error");
            shake(data.fields || []);
            return;
          }
          clearInvalid();
          if (data.slot) {
            updateTrigger(data.slot, data.block);
          }
          if (data.redirect) {
            window.location.assign(data.redirect);
            return;
          }
          closeModal();
        })
        .catch(function () {
          showFlash("Could not save this session. Try again.", "error");
          shake([]);
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }

  function closeModal() {
    if (window.bootstrap && bootstrap.Modal) {
      var instance =
        bootstrap.Modal.getInstance(modalEl) ||
        bootstrap.Modal.getOrCreateInstance(modalEl);
      instance.hide();
      return;
    }
    var closer = modalEl.querySelector("[data-bs-dismiss='modal']");
    if (closer) closer.click();
  }
})();
