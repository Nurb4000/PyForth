(function () {
  "use strict";

  var log = document.getElementById("log");
  var input = document.getElementById("input");
  var prompt = document.getElementById("prompt");
  var status = document.getElementById("status");
  var screen = document.getElementById("screen");

  var busy = false;

  function esc(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function addLine(cls, promptText, text) {
    var row = document.createElement("div");
    row.className = "line " + cls;
    if (promptText) {
      var p = document.createElement("span");
      p.className = "prompt";
      p.innerHTML = esc(promptText);
      row.appendChild(p);
    }
    if (text !== undefined && text !== null) {
      var body = document.createElement("span");
      body.className = "command";
      body.innerHTML = esc(text);
      row.appendChild(body);
    }
    log.appendChild(row);
  }

  function addOutput(text) {
    if (!text) return;
    var row = document.createElement("div");
    row.className = "line output";
    row.textContent = text;
    log.appendChild(row);
  }

  function scrollDown() {
    screen.scrollTop = screen.scrollHeight;
  }

  function focusInput() {
    input.focus();
  }

  function setStatus(cls, msg) {
    if (msg) {
      status.textContent = msg;
      status.className = "status " + (cls || "");
    } else {
      status.textContent = "";
      status.className = "status";
    }
  }

  function autoGrow() {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  }

  async function submit() {
    if (busy) return;
    var code = input.value;
    if (!code.trim() && !code) {
      return;
    }
    busy = true;
    setStatus("", "");

    // Render the prompt + command that was typed.
    addLine("command", prompt.textContent.replace(">", ""), code);

    input.value = "";
    autoGrow();

    try {
      var resp = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code }),
      });
      var data = await resp.json();
      if (data.output) {
        addOutput(data.output);
      }
      if (data.error) {
        addLine("error", "", data.error);
        setStatus("failed", "error");
      } else {
        addLine("ok", "", "ok");
      }
    } catch (err) {
      addLine("error", "", String(err));
      setStatus("failed", "offline");
    }

    busy = false;
    scrollDown();
    focusInput();
  }

  function clearScreen() {
    log.innerHTML = "";
  }

  async function resetInterpreter() {
    if (busy) return;
    busy = true;
    try {
      await fetch("/api/reset", { method: "POST" });
      addLine("ok", "", "-- interpreter reset --");
    } catch (err) {
      addLine("error", "", String(err));
    }
    clearScreen();
    busy = false;
    scrollDown();
    focusInput();
  }

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  });

  input.addEventListener("input", autoGrow);

  document.getElementById("clear-btn").addEventListener("click", clearScreen);
  document.getElementById("reset-btn").addEventListener("click", resetInterpreter);

  document.addEventListener("click", function (event) {
    if (event.target.closest("#toolbar")) return;
    focusInput();
  });

  // Keep focus on the input so typing is immediate.
  window.addEventListener("load", function () {
    autoGrow();
    focusInput();
  });
})();
