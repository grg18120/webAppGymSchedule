(function () {
  var picker = document.querySelector(".timeline-week-picker");
  if (!picker) return;

  var toggle = picker.querySelector("[data-week-picker-toggle]");
  var panel = picker.querySelector("[data-week-picker-panel]");
  var grid = picker.querySelector("[data-week-picker-grid]");
  var label = picker.querySelector("[data-week-picker-label]");
  var prev = picker.querySelector("[data-week-picker-prev]");
  var next = picker.querySelector("[data-week-picker-next]");
  var months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function parseDay(raw) {
    var parts = String(raw || "").split("-");
    if (parts.length !== 3) return new Date();
    return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  }

  function ymd(date) {
    var month = String(date.getMonth() + 1);
    var day = String(date.getDate());
    if (month.length === 1) month = "0" + month;
    if (day.length === 1) day = "0" + day;
    return date.getFullYear() + "-" + month + "-" + day;
  }

  function mondayOf(date) {
    var copy = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    var weekday = copy.getDay();
    var offset = weekday === 0 ? -6 : 1 - weekday;
    copy.setDate(copy.getDate() + offset);
    return copy;
  }

  function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  var weekStart = mondayOf(parseDay(picker.getAttribute("data-week-start")));
  var weekEnd = new Date(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate() + 6);
  var today = parseDay(picker.getAttribute("data-today"));
  var view = new Date(weekStart.getFullYear(), weekStart.getMonth(), 1);

  function inCurrentWeek(date) {
    return date >= weekStart && date <= weekEnd;
  }

  function render() {
    if (label) {
      label.textContent = months[view.getMonth()] + " " + view.getFullYear();
    }
    if (!grid) return;
    grid.innerHTML = "";
    var first = new Date(view.getFullYear(), view.getMonth(), 1);
    var cursor = mondayOf(first);
    for (var i = 0; i < 42; i += 1) {
      var day = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate());
      var link = document.createElement("a");
      link.className = "timeline-week-picker__day";
      link.href = "/timeline?start=" + ymd(day);
      link.textContent = String(day.getDate());
      if (day.getMonth() !== view.getMonth()) {
        link.classList.add("is-muted");
      }
      if (inCurrentWeek(day)) {
        link.classList.add("is-week");
      }
      if (sameDay(day, today)) {
        link.classList.add("is-today");
      }
      if (inCurrentWeek(day) && day.getDay() === 1) {
        link.setAttribute("aria-current", "date");
      }
      grid.appendChild(link);
      cursor.setDate(cursor.getDate() + 1);
    }
  }

  function setOpen(open) {
    if (!panel || !toggle) return;
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function isOpen() {
    return Boolean(panel) && !panel.hidden;
  }

  if (toggle) {
    toggle.addEventListener("click", function (event) {
      event.preventDefault();
      setOpen(!isOpen());
    });
  }
  if (prev) {
    prev.addEventListener("click", function () {
      view = new Date(view.getFullYear(), view.getMonth() - 1, 1);
      render();
    });
  }
  if (next) {
    next.addEventListener("click", function () {
      view = new Date(view.getFullYear(), view.getMonth() + 1, 1);
      render();
    });
  }
  document.addEventListener("click", function (event) {
    if (!isOpen()) return;
    if (picker.contains(event.target)) return;
    setOpen(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && isOpen()) {
      setOpen(false);
      if (toggle) toggle.focus();
    }
  });

  render();
})();
