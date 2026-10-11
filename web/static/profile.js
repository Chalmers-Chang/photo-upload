function photoCredit(nickname, caption, tpl) {
  const n = (nickname || "").trim();
  const c = (caption || "").trim();
  if (n && c) {
    return (tpl || "{name}：{caption}").replaceAll("{name}", n).replaceAll("{caption}", c);
  }
  return n || c;
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
  input.focus();
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.hidden = true;
    const body = JSON.stringify({ nickname: input.value });
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
    modal.hidden = true;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  ensureNickname().catch(() => {});
});
