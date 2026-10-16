function photoCredit(nickname, caption, tpl) {
  const n = (nickname || "").trim();
  const c = (caption || "").trim();
  if (n && c) {
    return (tpl || "{name}：{caption}").replaceAll("{name}", n).replaceAll("{caption}", c);
  }
  return n || c;
}

function nicknameCopy() {
  const el = document.getElementById("name-modal-copy");
  if (!el) return { zh: {}, en: {} };
  try {
    return JSON.parse(el.textContent);
  } catch (err) {
    return { zh: {}, en: {} };
  }
}

function applyNicknameLang(lang) {
  const copy = nicknameCopy()[lang] || nicknameCopy().zh || {};
  const title = document.getElementById("name-modal-title");
  const lead = document.getElementById("name-modal-lead");
  const input = document.getElementById("name-input");
  const ok = document.getElementById("name-modal-ok");
  const modal = document.getElementById("name-modal");
  if (title && copy.title) title.textContent = copy.title;
  if (lead && copy.lead) lead.textContent = copy.lead;
  if (input && copy.placeholder) input.placeholder = copy.placeholder;
  if (ok && copy.ok) ok.textContent = copy.ok;
  if (modal && copy.saveError) modal.dataset.saveError = copy.saveError;
}

async function ensureNickname() {
  const modal = document.getElementById("name-modal");
  const form = document.getElementById("name-form");
  const input = document.getElementById("name-input");
  const err = document.getElementById("name-modal-error");
  if (!modal || !form) return;
  const res = await fetch("/api/profile", { cache: "no-store" });
  const data = await res.json();
  if (data.nickname) return;
  modal.hidden = false;
  const picked = form.querySelector('input[name="ui-lang"]:checked');
  applyNicknameLang(picked ? picked.value : "zh");
  form.querySelectorAll('input[name="ui-lang"]').forEach((el) => {
    el.addEventListener("change", () => applyNicknameLang(el.value));
  });
  input.focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const langEl = form.querySelector('input[name="ui-lang"]:checked');
    const body = JSON.stringify({
      nickname: input.value,
      lang: langEl ? langEl.value : undefined,
    });
    const save = await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    const out = await save.json();
    if (!save.ok) {
      err.textContent = out.error || modal.dataset.saveError;
      err.hidden = false;
      return;
    }
    location.reload();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  ensureNickname().catch(() => {});
});
