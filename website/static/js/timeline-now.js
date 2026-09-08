(function () {
  var line = document.querySelector("[data-timeline-now]");
  if (!line) return;

  var timezone = line.getAttribute("data-timezone") || "Europe/Athens";
  var lineDate = line.getAttribute("data-date") || "";
  var startHour = Number(line.getAttribute("data-start-hour") || 6);
  var endHour = Number(line.getAttribute("data-end-hour") || 23);

  function gymNow() {
    var parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(new Date());
    var values = {};
    parts.forEach(function (part) {
      if (part.type !== "literal") values[part.type] = part.value;
    });
    return {
      date: values.year + "-" + values.month + "-" + values.day,
      seconds:
        Number(values.hour) * 3600 +
        Number(values.minute) * 60 +
        Number(values.second),
    };
  }

  function updateNowLine() {
    var now = gymNow();
    var start = startHour * 3600;
    var end = endHour * 3600;
    if (now.date !== lineDate || now.seconds < start || now.seconds > end) {
      line.hidden = true;
      return;
    }
    var percent = ((now.seconds - start) / (end - start)) * 100;
    line.style.top = percent + "%";
    line.hidden = false;
  }

  updateNowLine();
  setInterval(updateNowLine, 15000);
})();
