(function () {
  const toggle = document.getElementById("enabledToggle");
  const enabledField = document.getElementById("enabledField");
  const status = document.getElementById("enabledStatus");

  const wrap = document.getElementById("controlsWrap");
  const mode = document.getElementById("alert_mode");
  const days = document.getElementById("days_before");
  const saveBtn = document.getElementById("saveBtn");

  function applyUI() {
    const isOn = !!toggle.checked;

    wrap.classList.toggle("opacity-60", !isOn);
    wrap.classList.toggle("pointer-events-none", !isOn);

    mode.disabled = !isOn;

    const allowDays = isOn && mode.value === "before_and_due";
    days.readOnly = !allowDays;

    days.classList.toggle("bg-slate-100", !allowDays);
    days.classList.toggle("opacity-60", !allowDays);

    saveBtn.disabled = !isOn;
    saveBtn.classList.toggle("opacity-60", !isOn);
    saveBtn.classList.toggle("cursor-not-allowed", !isOn);
  }

  async function saveEnabled(value) {
    try {
      toggle.disabled = true;
      status.textContent = "Salvando...";

      const fd = new FormData();
      fd.append("enabled", value ? "on" : "off");

      const res = await fetch(ALERTAS_URLS.enabled, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });

      if (!res.ok) throw new Error("HTTP " + res.status);

      enabledField.value = value ? "on" : "off";
      status.textContent = "Salvo ✅";
      setTimeout(() => (status.textContent = ""), 1200);
    } catch (e) {
      toggle.checked = !toggle.checked;
      status.textContent = "Erro ao salvar. Tente novamente.";
    } finally {
      toggle.disabled = false;
      applyUI();
    }
  }

  toggle.addEventListener("change", () => {
    applyUI();
    saveEnabled(toggle.checked);
  });

  mode.addEventListener("change", applyUI);

  applyUI();
})();

(function () {
  const addBtn = document.getElementById("addRecipientBtn");
  const emailInput = document.getElementById("newRecipientEmail");
  const err = document.getElementById("recipientError");
  const list = document.getElementById("recipientsList");

  if (!addBtn || !emailInput || !err || !list) return;

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function rowHtml(r) {
    const email = escapeHtml(r.email);
    return `
      <div class="flex items-center justify-between border rounded-lg px-3 py-2" data-id="${r.id}">
        <div class="text-sm">
          <div class="font-medium">${email}</div>
          <div class="text-xs text-slate-500">${r.enabled ? "Ativo" : "Inativo"}</div>
        </div>
        <div class="flex items-center gap-3">
          <label class="inline-flex items-center gap-2 select-none">
            <input class="recipientToggle w-5 h-5" type="checkbox" ${r.enabled ? "checked" : ""}>
            <span class="text-sm">Ativo</span>
          </label>
          <button type="button" class="removeRecipient text-sm px-3 py-1 border rounded-lg">Remover</button>
        </div>
      </div>
    `;
  }

  addBtn.addEventListener("click", async () => {
    err.textContent = "";
    const email = (emailInput.value || "").trim();

    try {
      const fd = new FormData();
      fd.append("email", email);

      const res = await fetch(ALERTAS_URLS.addRecipient, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });

      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Erro ao adicionar.");

      const existing = list.querySelector(`[data-id="${data.id}"]`);
      if (existing) {
        const chk = existing.querySelector(".recipientToggle");
        if (chk) chk.checked = true;
        const statusLine = existing.querySelector(".text-xs");
        if (statusLine) statusLine.textContent = "Ativo";
      } else {
        if (list.children.length === 1 && list.firstElementChild && list.firstElementChild.classList.contains("text-slate-500")) {
          list.innerHTML = "";
        }
        list.insertAdjacentHTML("afterbegin", rowHtml(data));
      }

      emailInput.value = "";
    } catch (e) {
      err.textContent = e.message || "Erro ao adicionar.";
    }
  });

  list.addEventListener("click", async (ev) => {
    const row = ev.target.closest("[data-id]");
    if (!row) return;
    const rid = row.getAttribute("data-id");

    if (ev.target.classList.contains("removeRecipient")) {
      try {
        const url = ALERTAS_URLS.deleteRecipient.replace("/0", "/" + rid);

        const res = await fetch(url, {
          method: "DELETE",
          credentials: "same-origin",
        });

        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error("Erro ao remover.");

        row.remove();

        if (list.children.length === 0) {
          list.innerHTML = `<div class="text-sm text-slate-500">
            Nenhum destinatário extra cadastrado. (Por padrão, envia para <b>${escapeHtml(CURRENT_USER_EMAIL)}</b>.)
          </div>`;
        }
      } catch (e) {
        err.textContent = "Erro ao remover.";
      }
    }
  });

  list.addEventListener("change", async (ev) => {
    const row = ev.target.closest("[data-id]");
    if (!row) return;
    const rid = row.getAttribute("data-id");

    if (ev.target.classList.contains("recipientToggle")) {
      const enabled = ev.target.checked;
      try {
        const fd = new FormData();
        fd.append("enabled", enabled ? "on" : "off");

        const url = ALERTAS_URLS.toggleRecipient.replace("/0/", "/" + rid + "/");

        const res = await fetch(url, {
          method: "POST",
          body: fd,
          credentials: "same-origin",
        });

        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error("Erro ao salvar.");

        const statusLine = row.querySelector(".text-xs");
        if (statusLine) statusLine.textContent = enabled ? "Ativo" : "Inativo";
      } catch (e) {
        ev.target.checked = !enabled;
        err.textContent = "Erro ao salvar status.";
      }
    }
  });
})();
