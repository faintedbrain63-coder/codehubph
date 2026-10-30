/* Chunked uploads for large private files (staff forms).
   Before a form with [data-chunked-upload] file inputs is submitted, each selected file is sent
   to /manage/uploads/ in pieces small enough for Cloudflare/Nginx request limits, while a modal
   reports progress. The form is then submitted with only a hidden token per file. Interrupted
   uploads resume from the last stored byte. Without JavaScript the plain file upload still works. */
(function () {
  "use strict";

  const MAX_ATTEMPTS = 6;
  const ready = new WeakSet();
  const busy = new WeakSet();

  function csrf(form) {
    const field = form.querySelector('input[name="csrfmiddlewaretoken"]');
    return field ? field.value : "";
  }

  function wait(ms, signal) {
    return new Promise(function (resolve, reject) {
      const timer = setTimeout(resolve, ms);
      if (signal) signal.addEventListener("abort", function () { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
    });
  }

  function size(bytes) {
    if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function duration(seconds) {
    if (!isFinite(seconds) || seconds <= 0) return "Calculating…";
    if (seconds < 60) return Math.max(1, Math.round(seconds)) + " s left";
    if (seconds < 3600) return "About " + Math.round(seconds / 60) + " min left";
    return "About " + (seconds / 3600).toFixed(1) + " h left";
  }

  function iconFor(name) {
    const ext = (name.split(".").pop() || "").toLowerCase();
    if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return "file-earmark-zip";
    if (["apk", "aab", "ipa"].includes(ext)) return "phone";
    if (["exe", "msi", "dmg", "pkg", "deb", "rpm", "jar"].includes(ext)) return "file-earmark-binary";
    if (ext === "pdf") return "file-earmark-pdf";
    if (["doc", "docx"].includes(ext)) return "file-earmark-word";
    if (ext === "pptx") return "file-earmark-slides";
    return "file-earmark";
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function icon(name) {
    const i = el("i", "bi bi-" + name);
    i.setAttribute("aria-hidden", "true");
    return i;
  }

  function bar(label) {
    const track = el("div", "um-track");
    track.setAttribute("role", "progressbar");
    track.setAttribute("aria-label", label);
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "100");
    track.setAttribute("aria-valuenow", "0");
    track.appendChild(el("div", "um-fill"));
    return track;
  }

  function setBar(track, pct, text) {
    track.setAttribute("aria-valuenow", String(pct));
    if (text) track.setAttribute("aria-valuetext", text);
    track.firstChild.style.width = pct + "%";
  }

  /* ----- Progress modal --------------------------------------------------- */
  const STATE_LABELS = { waiting: "Waiting", uploading: "Uploading", retrying: "Retrying", done: "Uploaded", failed: "Failed" };

  function UploadModal(files, saveLabel) {
    const totalBytes = files.reduce(function (sum, f) { return sum + f.size; }, 0);
    const dialog = el("dialog", "upload-modal");
    dialog.tabIndex = -1;
    dialog.setAttribute("aria-labelledby", "um-title");
    dialog.setAttribute("aria-describedby", "um-subtitle");

    const head = el("header", "um-head");
    const badge = el("span", "um-badge"); badge.appendChild(icon("cloud-arrow-up"));
    const titles = el("div", "um-titles");
    const title = el("h2", "um-title", "Uploading " + (files.length === 1 ? "file" : files.length + " files"));
    title.id = "um-title";
    const subtitle = el("p", "um-subtitle", "Keep this page open. Files are sent in parts and resume automatically if the connection drops.");
    subtitle.id = "um-subtitle";
    titles.append(title, subtitle);
    head.append(badge, titles);

    const summary = el("section", "um-summary");
    const top = el("div", "um-summary-top");
    const percent = el("strong", "um-percent", "0%");
    const transferred = el("span", "um-transferred", "0 KB of " + size(totalBytes));
    top.append(percent, transferred);
    const overall = bar("Overall upload progress");
    overall.classList.add("um-track-lg");
    const metrics = el("dl", "um-metrics");
    function metric(iconName, label, value) {
      const wrap = el("div", "um-metric");
      const dt = el("dt"); dt.append(icon(iconName), document.createTextNode(label));
      const dd = el("dd", "", value);
      wrap.append(dt, dd); metrics.appendChild(wrap);
      return dd;
    }
    const remaining = metric("clock", "Time left", "Calculating…");
    const speed = metric("speedometer2", "Speed", "–");
    const part = metric("grid-3x3-gap", "Part", "–");
    summary.append(top, overall, metrics);

    const list = el("ul", "um-files");
    list.setAttribute("aria-label", "Files");
    const rows = files.map(function (file) {
      const li = el("li", "um-file is-waiting");
      const fileIcon = el("span", "um-file-icon"); fileIcon.appendChild(icon(iconFor(file.name)));
      const body = el("div", "um-file-body");
      const line = el("div", "um-file-line");
      const name = el("span", "um-file-name", file.name); name.title = file.name;
      const pill = el("span", "um-pill", STATE_LABELS.waiting);
      line.append(name, pill);
      const meta = el("div", "um-file-meta");
      const detail = el("span", "", size(file.size));
      const pct = el("span", "um-file-pct", "0%");
      meta.append(detail, pct);
      const track = bar("Progress for " + file.name);
      body.append(line, meta, track);
      li.append(fileIcon, body);
      list.appendChild(li);
      return { li: li, pill: pill, detail: detail, pct: pct, track: track, size: file.size, sent: 0 };
    });

    const alert = el("div", "um-alert");
    alert.setAttribute("role", "alert");
    alert.hidden = true;

    const foot = el("footer", "um-foot");
    const note = el("span", "um-note"); note.append(icon("shield-lock"), document.createTextNode("Stored privately · never publicly linked"));
    const actions = el("div", "um-actions");
    const cancel = el("button", "btn btn-outline-danger", "Cancel upload"); cancel.type = "button";
    const close = el("button", "btn btn-soft", "Close"); close.type = "button"; close.hidden = true;
    const retry = el("button", "btn btn-primary", "Resume upload"); retry.type = "button"; retry.hidden = true;
    actions.append(cancel, close, retry);
    foot.append(note, actions);

    const confirmBar = el("div", "um-confirm");
    confirmBar.hidden = true;
    const confirmText = el("p", "", "Stop uploading? Parts already sent are discarded and nothing is saved.");
    const keep = el("button", "btn btn-soft btn-sm", "Keep uploading"); keep.type = "button";
    const stop = el("button", "btn btn-danger btn-sm", "Stop upload"); stop.type = "button";
    const confirmActions = el("div", "um-actions"); confirmActions.append(keep, stop);
    confirmBar.append(confirmText, confirmActions);

    const live = el("p", "visually-hidden");
    live.setAttribute("aria-live", "polite");

    dialog.append(head, summary, list, alert, confirmBar, foot, live);
    document.body.appendChild(dialog);

    let active = true;
    let lastAnnounced = -1;
    const samples = [];  // [time, bytes] over a sliding window for speed/ETA

    // Esc must not silently abandon a long upload: route it to the cancel confirmation.
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (active) askCancel(); else api.close();
    });
    function askCancel() { confirmBar.hidden = false; foot.hidden = true; keep.focus(); }
    keep.addEventListener("click", function () { confirmBar.hidden = true; foot.hidden = false; cancel.focus(); });

    const api = {
      onCancel: null,
      onRetry: null,
      open: function () {
        if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", "");
        dialog.focus();  // announce the dialog without putting focus on a destructive action
      },
      fileState: function (index, state, text) {
        const row = rows[index];
        row.li.className = "um-file is-" + state;
        row.pill.textContent = STATE_LABELS[state];
        if (text) row.detail.textContent = text;
        if (state === "done") { row.sent = row.size; this.progress(index, row.size); }
      },
      progress: function (index, sent, partNo, partTotal) {
        const row = rows[index];
        row.sent = sent;
        const filePct = row.size ? Math.floor((sent / row.size) * 100) : 100;
        setBar(row.track, filePct, filePct + " percent");
        row.pct.textContent = filePct + "%";
        if (row.li.classList.contains("is-uploading")) row.detail.textContent = size(sent) + " of " + size(row.size);

        const done = rows.reduce(function (sum, r) { return sum + r.sent; }, 0);
        const pct = totalBytes ? Math.floor((done / totalBytes) * 100) : 100;
        percent.textContent = pct + "%";
        transferred.textContent = size(done) + " of " + size(totalBytes);
        setBar(overall, pct, pct + " percent, " + size(done) + " of " + size(totalBytes));
        if (partNo) part.textContent = partNo + " of " + partTotal;

        const now = performance.now();
        samples.push([now, done]);
        while (samples.length > 2 && now - samples[0][0] > 8000) samples.shift();
        const span = (now - samples[0][0]) / 1000;
        if (span >= 1) {
          const rate = (done - samples[0][1]) / span;
          speed.textContent = rate > 0 ? size(rate) + "/s" : "–";
          remaining.textContent = rate > 0 ? duration((totalBytes - done) / rate) : "Calculating…";
        }
        const milestone = Math.floor(pct / 25) * 25;
        if (milestone > lastAnnounced && milestone < 100) {
          lastAnnounced = milestone;
          live.textContent = "Upload " + milestone + " percent complete.";
        }
      },
      retrying: function (index, message) {
        this.fileState(index, "retrying");
        samples.length = 0;
        speed.textContent = "–";
        remaining.textContent = "Paused";
        showAlert("warning", "exclamation-triangle", message);
      },
      clearAlert: function () { alert.hidden = true; },
      complete: function () {
        active = false;
        alert.hidden = true;
        dialog.classList.add("is-complete");
        badge.replaceChildren(icon("check2-circle"));
        title.textContent = files.length === 1 ? "Upload complete" : "All files uploaded";
        subtitle.textContent = "Verifying and saving. This usually takes a few seconds.";
        percent.textContent = "100%";
        remaining.textContent = "Done";
        cancel.hidden = true;
        const saving = el("span", "um-saving");
        const spinner = el("span", "spinner-border spinner-border-sm"); spinner.setAttribute("aria-hidden", "true");
        saving.append(spinner, document.createTextNode(saveLabel));
        actions.appendChild(saving);
        live.textContent = "Upload complete. " + saveLabel;
      },
      // kind: "resumable" (connection dropped, progress kept), "restart" (server discarded it), "refused".
      fail: function (index, message, kind, sent) {
        active = false;
        dialog.classList.add("is-failed");
        const copy = {
          resumable: ["Upload paused", "Nothing has been saved yet. Parts already sent are kept, so you can resume where you stopped.", "Resume upload", sent ? size(sent) + " sent · resumable" : undefined],
          restart: ["Upload stopped", "The server no longer has this upload. Nothing has been saved; start again to upload the file from the beginning.", "Start again", "Needs a fresh upload"],
          refused: ["Upload not accepted", "Nothing has been saved. Check the message below, then try again.", "Try again", undefined],
        }[kind] || [];
        if (index !== null) this.fileState(index, "failed", copy[3]);
        badge.replaceChildren(icon("cloud-slash"));
        title.textContent = copy[0];
        subtitle.textContent = copy[1];
        retry.textContent = copy[2];
        remaining.textContent = "–";
        speed.textContent = "–";
        showAlert("danger", "x-octagon", message);
        cancel.hidden = true;
        close.hidden = false;
        retry.hidden = false;
        retry.focus();
      },
      close: function () {
        if (dialog.open && typeof dialog.close === "function") dialog.close();
        dialog.remove();
      },
    };

    function showAlert(kind, iconName, message) {
      alert.className = "um-alert is-" + kind;
      alert.replaceChildren(icon(iconName), el("span", "", message));
      alert.hidden = false;
    }

    cancel.addEventListener("click", askCancel);
    stop.addEventListener("click", function () { active = false; if (api.onCancel) api.onCancel(); api.close(); });
    close.addEventListener("click", function () { api.close(); });
    retry.addEventListener("click", function () { api.close(); if (api.onRetry) api.onRetry(); });
    return api;
  }

  /* ----- Transport --------------------------------------------------------- */
  async function request(url, options) {
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options));
    let body = {};
    try { body = await response.json(); } catch (e) { /* non-JSON error page from a proxy */ }
    return { ok: response.ok, status: response.status, body: body };
  }

  function tokenFor(input) { return input.parentElement.querySelector("[data-upload-token]"); }

  async function startOrResume(input, file, form, signal) {
    const startUrl = tokenFor(input).getAttribute("data-upload-url");
    const key = [file.name, file.size, file.lastModified].join(":");
    if (input.dataset.chunkKey === key && input.dataset.chunkId) {
      const state = await request(startUrl + input.dataset.chunkId + "/", { signal: signal });
      if (state.ok && state.body.size === file.size) return state.body;
    }
    const created = await request(startUrl, {
      method: "POST", signal: signal,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(form) },
      body: JSON.stringify({ target: input.getAttribute("data-chunked-upload"), filename: file.name, size: file.size }),
    });
    if (!created.ok) throw new Error(created.body.error || "The upload could not be started (HTTP " + created.status + ").");
    input.dataset.chunkKey = key;
    input.dataset.chunkId = created.body.id;
    return created.body;
  }

  async function uploadFile(input, index, form, modal, signal) {
    const file = input.files[0];
    let state = await startOrResume(input, file, form, signal);
    const url = tokenFor(input).getAttribute("data-upload-url") + state.id + "/";
    const parts = Math.max(1, Math.ceil(file.size / state.chunk_size));
    let received = state.received;
    let attempts = 0;
    modal.fileState(index, "uploading");
    modal.progress(index, received, Math.min(parts, Math.floor(received / state.chunk_size) + 1), parts);
    while (!state.complete && received < file.size) {
      const end = Math.min(received + state.chunk_size, file.size);
      let result;
      try {
        result = await request(url, {
          method: "POST", signal: signal,
          headers: {
            "Content-Type": "application/octet-stream",
            "Content-Range": "bytes " + received + "-" + (end - 1) + "/" + file.size,
            "X-CSRFToken": csrf(form),
          },
          body: file.slice(received, end),
        });
      } catch (error) {
        if (signal.aborted) throw error;
        result = { ok: false, status: 0, body: {} };  // network drop: retry below
      }
      if (result.ok) {
        state = result.body;
        received = state.received;
        if (attempts) { modal.clearAlert(); modal.fileState(index, "uploading"); }
        attempts = 0;
        modal.progress(index, received, Math.min(parts, Math.ceil(received / state.chunk_size)), parts);
        continue;
      }
      if (result.status === 409 && typeof result.body.received === "number") {
        received = result.body.received;  // the server's offset differs: continue from it
        continue;
      }
      if ([400, 403, 404, 410, 413].includes(result.status) && !(result.status === 400 && typeof result.body.received === "number")) {
        if (result.status === 404 || result.status === 410) delete input.dataset.chunkId;
        const error = new Error(result.body.error || (result.status === 413
          ? "The server rejected the part size. Lower UPLOAD_CHUNK_MB or raise Nginx client_max_body_size."
          : "The server refused the upload (HTTP " + result.status + ")."));
        error.received = received;
        error.kind = result.status === 404 || result.status === 410 ? "restart" : "refused";
        throw error;
      }
      attempts += 1;
      if (attempts >= MAX_ATTEMPTS) {
        const error = new Error("The connection kept dropping. Your progress is saved, so select Resume upload to continue from " + size(received) + ".");
        error.received = received;
        error.kind = "resumable";
        throw error;
      }
      const delay = Math.min(1000 * Math.pow(2, attempts - 1), 15000);
      modal.retrying(index, "Connection interrupted. Retrying in " + Math.round(delay / 1000) + " s (attempt " + attempts + " of " + (MAX_ATTEMPTS - 1) + ").");
      await wait(delay, signal);
    }
    tokenFor(input).value = state.id;
    modal.fileState(index, "done", size(file.size));
  }

  function setButtons(form, disabled) {
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (b) { b.disabled = disabled; });
  }

  function saveLabelFor(submitter) {
    return (submitter && submitter.getAttribute("data-loading-text")) || "Saving…";
  }

  async function run(form, submitter, inputs) {
    busy.add(form);
    setButtons(form, true);
    const controller = new AbortController();
    const modal = UploadModal(inputs.map(function (input) { return input.files[0]; }), saveLabelFor(submitter));
    modal.onCancel = function () {
      controller.abort();
      inputs.forEach(function (input) {
        if (!input.dataset.chunkId) return;
        fetch(tokenFor(input).getAttribute("data-upload-url") + input.dataset.chunkId + "/", {
          method: "DELETE", credentials: "same-origin", headers: { "X-CSRFToken": csrf(form) },
        }).catch(function () {});
        delete input.dataset.chunkId;
      });
      busy.delete(form);
      setButtons(form, false);
    };
    modal.onRetry = function () { run(form, submitter, inputs); };
    modal.open();

    let index = 0;
    try {
      for (; index < inputs.length; index++) await uploadFile(inputs[index], index, form, modal, controller.signal);
    } catch (error) {
      if (controller.signal.aborted) return;
      if (!error.kind && error instanceof TypeError) {  // fetch() could not reach the server at all
        error.kind = "resumable";
        error.message = "The server could not be reached. Check your connection, then resume the upload.";
      }
      busy.delete(form);
      setButtons(form, false);
      modal.fail(index < inputs.length ? index : null, error.message, error.kind || "refused", error.received);
      return;
    }
    // Every file now lives on the server; submit only the tokens.
    inputs.forEach(function (input) { input.value = ""; input.required = false; });
    modal.complete();
    busy.delete(form);
    setButtons(form, false);
    ready.add(form);
    if (submitter && submitter.form === form) form.requestSubmit(submitter);
    else form.requestSubmit();
  }

  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form || form.tagName !== "FORM" || event.defaultPrevented) return;
    if (ready.has(form)) { ready.delete(form); return; }
    const inputs = Array.from(form.querySelectorAll('input[type="file"][data-chunked-upload]'))
      .filter(function (input) { return input.files && input.files.length; });
    if (!inputs.length || !window.fetch || !window.Blob || !Blob.prototype.slice) return;
    // Let normal validation report invalid fields before spending time on uploads.
    if (form.classList.contains("needs-validation") && !form.checkValidity()) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (busy.has(form)) return;
    run(form, event.submitter, inputs);
  }, true);
})();
