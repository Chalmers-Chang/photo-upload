(function () {
  const RING = 2 * Math.PI * 45;

  function veilEls() {
    return {
      veil: document.getElementById("progress"),
      fill: document.getElementById("pie-fill"),
      pctEl: document.getElementById("pie-pct"),
      label: document.getElementById("progress-label"),
    };
  }

  function setPct(n) {
    const { fill, pctEl } = veilEls();
    const v = Math.max(0, Math.min(100, n));
    fill.style.strokeDashoffset = String(RING * (1 - v / 100));
    pctEl.textContent = Math.round(v) + "%";
  }

  async function shrinkFile(file, maxEdge, keepPng) {
    if (!file || !file.type.startsWith("image/")) return file;
    let bmp;
    try {
      bmp = await createImageBitmap(file);
    } catch (err) {
      return file;
    }
    const w = bmp.width;
    const h = bmp.height;
    const scale = Math.min(1, maxEdge / Math.max(w, h));
    if (scale >= 1 && file.size < 3 * 1024 * 1024) {
      bmp.close();
      return file;
    }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(w * scale));
    canvas.height = Math.max(1, Math.round(h * scale));
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
    const png = keepPng && (file.type === "image/png" || /\.png$/i.test(file.name));
    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, png ? "image/png" : "image/jpeg", png ? undefined : 0.8)
    );
    if (!blob || blob.size >= file.size) return file;
    const name = file.name.replace(/\.[^.]+$/, png ? ".png" : ".jpg");
    return new File([blob], name, { type: blob.type });
  }

  window.postFormWithPie = async function (form, opts) {
    const { veil, label } = veilEls();
    const input = form.querySelector('input[type="file"]');
    const files = [...(input && input.files ? input.files : [])];
    if (!files.length) return;
    const uploading = opts.uploading;
    const processing = opts.processing;
    const failed = opts.failed;
    const maxEdge = opts.maxEdge || 2560;
    document.body.appendChild(veil);
    veil.hidden = false;
    veil.classList.add("is-on");
    setPct(0);
    label.textContent = processing;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const body = new FormData(form);
    body.delete(input.name);
    for (const file of files) {
      body.append(input.name, await shrinkFile(file, maxEdge, !!opts.keepPng));
    }
    label.textContent = uploading;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action || location.href);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    xhr.upload.addEventListener("progress", (ev) => {
      if (!ev.lengthComputable) return;
      const p = ev.loaded / ev.total;
      setPct(p * 100);
      if (p >= 1) label.textContent = processing;
    });
    xhr.addEventListener("load", () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch (err) {}
      if (xhr.status >= 400 || data.error) {
        veil.classList.remove("is-on");
        veil.hidden = true;
        alert(data.error || failed);
        return;
      }
      setPct(100);
      if (data.message) sessionStorage.setItem("uploadFlash", data.message);
      if (typeof opts.onSuccess === "function") opts.onSuccess(form, data);
      location.reload();
    });
    xhr.addEventListener("error", () => {
      veil.classList.remove("is-on");
      veil.hidden = true;
      alert(failed);
    });
    xhr.send(body);
  };
})();
