/* Optional zero-dependency rendering check. Uses only fake snapshots on localhost
   and a fresh headless Chrome profile, never the user's running browser/session.
   Generate snapshots and start the preview server as documented in README. */
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const http = require("node:http");

const root = path.resolve(__dirname, "..");
const origin = "http://127.0.0.1:8766";
const chrome = process.env.CHROME_BINARY || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const artifacts = path.join(root, ".qa");
const matrixName = process.env.CODEHUB_RENDER_NAME || 'matrix';
let browser, socket;

async function run() {
  const status = await new Promise((resolve, reject) => {
    http.get(origin + "/previews/overview.html", response => { response.resume(); resolve(response.statusCode); }).on("error", reject);
  });
  assert.equal(status, 200, "Start the isolated preview server first");
  await fs.mkdir(artifacts, { recursive: true });
  browser = spawn(chrome, ["--headless", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--remote-debugging-port=0", "--disable-renderer-backgrounding",
    "--user-data-dir=" + path.join(artifacts, process.env.CODEHUB_RENDER_CONTROLS === '1' ? 'render-profile-controls' : process.env.CODEHUB_RENDER_NAME ? 'render-profile-' + matrixName : 'render-profile'), "about:blank"],
    { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] });
  const endpoint = await new Promise((resolve, reject) => {
    let stderr = "";
    const timer = setTimeout(() => reject(new Error("Headless Chrome startup timed out")), 20000);
    browser.once("error", error => { clearTimeout(timer); reject(error); });
    browser.stderr.on("data", chunk => {
      stderr += chunk.toString();
      const match = stderr.match(/DevTools listening on (ws:\/\/127\.0\.0\.1:\d+\/devtools\/browser\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
  });
  socket = new WebSocket(endpoint);
  await once(socket, "open");
  let sequence = 0;
  const pending = new Map(), events = new Map(), exceptions = [];
  socket.addEventListener("message", event => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const task = pending.get(data.id); pending.delete(data.id); clearTimeout(task.timer);
      if (data.error) task.reject(new Error(JSON.stringify(data.error))); else task.resolve(data.result);
    } else {
      if (data.method === "Runtime.exceptionThrown") exceptions.push(data.params.exceptionDetails.exception?.description || data.params.exceptionDetails.text);
      const key = data.sessionId + ":" + data.method;
      if (events.has(key)) { events.get(key)(data.params); events.delete(key); }
    }
  });
  function send(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error("Protocol timeout: " + method)); }, 15000);
      pending.set(id, { resolve, reject, timer });
      socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }
  const target = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId: target.targetId, flatten: true });
  await send("Page.enable", {}, sessionId);
  await send("Runtime.enable", {}, sessionId);
  await send("Network.enable", {}, sessionId);
  await send('Network.setCacheDisabled', {cacheDisabled: true}, sessionId);
  // Offline font fallback: verify that layout, icons and controls do not need a CDN.
  await send("Network.setBlockedURLs", { urls: ["*fonts.googleapis.com*", "*fonts.gstatic.com*", "*googlesyndication.com*", "*doubleclick.net*"] }, sessionId);
  const controls = process.env.CODEHUB_RENDER_CONTROLS === '1';
  const matrix = process.env.CODEHUB_RENDER_MATRIX === "1" || controls;
  const matrixWidths = (process.env.CODEHUB_RENDER_WIDTHS || '320,360,576,768,992,1200,1440,2560').split(',').map(Number);
  const cases = controls ? [
    ['privacy', 'public-register.html'], ['license', 'public-register.html'],
    ['lightbox', 'portfolio-detail.html'], ['onboarding', 'customer-onboarding.html'],
    ['navbar', 'customer-settings.html'], ['account-menu', 'customer-settings.html'],
    ['sidebar', 'overview.html'], ['confirmation', 'product-form.html'],
    ['upload', 'product-form.html'],
    ['upload-cancel', 'product-form.html'], ['upload-error', 'product-form.html'],
    ['onboarding-last', 'customer-onboarding.html'],
  ].flatMap(([state, file]) => [[320, 568], [768, 1024], [992, 740], [1440, 900], [740, 360]]
    .map(([width, height]) => [state + '-' + width + '-' + height, file, width, height]))
    : matrix ? (await fs.readdir(path.join(artifacts, 'site/previews')))
    .filter(file => file.endsWith('.html') && (!process.env.CODEHUB_RENDER_FILTER || new RegExp(process.env.CODEHUB_RENDER_FILTER).test(file)))
    .flatMap(file => matrixWidths.map(width =>
      [file.replace('.html', '') + '-' + width, file, width, width < 768 ? 740 : 1000]))
    : process.env.CODEHUB_RENDER_AI === "1" ? [
    ["ai-settings-wide", "ai-settings.html", 1440, 1000],
    ["ai-settings-mobile", "ai-settings.html", 390, 844],
    ["ai-settings-dark", "ai-settings.html", 1440, 1000],
    ["ai-chat-wide", "ai-chat.html", 1440, 1000],
    ["ai-chat-mobile", "ai-chat.html", 390, 844],
    ["ai-chat-dark", "ai-chat.html", 1440, 1000],
    ["ai-manual-wide", "ai-manual.html", 1440, 1000],
    ["ai-manual-mobile", "ai-manual.html", 390, 844],
  ] : process.env.CODEHUB_RENDER_PORTFOLIO === "1" ? [
    ["portfolio-home-wide", "public-storefront.html#projects", 1440, 1000],
    ["portfolio-home-mobile", "public-storefront.html#projects", 390, 844],
    ["portfolio-home-dark", "public-storefront.html#projects", 1440, 1000],
    ["portfolio-featured-wide", "public-storefront.html#portfolio-featured", 1440, 1000],
    ["portfolio-featured-mobile", "public-storefront.html#portfolio-featured", 390, 844],
    ["portfolio-home-laptop", "public-storefront.html#projects", 1280, 900],
    ["portfolio-list-wide", "portfolio-list.html", 1440, 1000],
    ["portfolio-list-mobile", "portfolio-list.html", 390, 844],
    ["portfolio-detail-wide", "portfolio-detail.html", 1440, 1000],
    ["portfolio-detail-mobile", "portfolio-detail.html", 390, 844],
    ["portfolio-admin-wide", "portfolio-admin.html", 1440, 1000],
    ["portfolio-admin-mobile", "portfolio-admin.html", 390, 844],
    ["portfolio-form-wide", "portfolio-form.html", 1440, 1000],
    ["portfolio-form-mobile", "portfolio-form.html", 390, 844],
    ["portfolio-presentation-wide", "portfolio-presentation.html", 1440, 1000],
    ["portfolio-presentation-mobile", "portfolio-presentation.html", 390, 844],
    ["project-review-wide", "project-review-form.html", 1440, 1000],
    ["project-review-mobile", "project-review-form.html", 390, 844],
    ["registration-legal-wide", "public-register.html", 1440, 1000],
    ["registration-legal-mobile", "public-register.html", 390, 844],
    ["privacy-modal-wide", "public-register.html#privacy", 1440, 1000],
    ["privacy-modal-mobile", "public-register.html#privacy", 390, 844],
    ["license-modal-wide", "public-register.html#license", 1440, 1000],
    ["license-modal-mobile", "public-register.html#license", 390, 844],
    ["privacy-document-wide", "public-privacy.html", 1440, 1000],
    ["license-document-mobile", "public-license.html", 390, 844],
  ] : process.env.CODEHUB_RENDER_SERVICES === "1" ? [
    ["services-home-wide", "public-storefront.html", 1440, 1000],
    ["services-home-mobile", "public-storefront.html", 390, 844],
    ["services-home-ultrawide", "public-storefront.html", 2560, 1200],
    ["services-list-wide", "public-services.html", 1440, 1000],
    ["services-list-mobile", "public-services.html", 390, 844],
    ["request-form-wide", "customer-project-request.html", 1440, 1000],
    ["request-form-mobile", "customer-project-request.html", 390, 844],
    ["projects-account-wide", "customer-account.html", 1440, 1000],
    ["projects-account-mobile", "customer-account.html", 390, 844],
    ["services-admin-wide", "overview.html", 1440, 1000],
    ["services-admin-mobile", "overview.html", 390, 844],
    ["service-form-mobile", "service-form.html", 390, 844],
    ["customer-settings-mobile", "customer-settings.html", 390, 844],
    ["admin-settings-mobile", "settings.html", 390, 844],
  ] : [
    ["overview-desktop", "overview.html", 1440, 1000],
    ["products-desktop", "products.html", 1440, 1000],
    ["product-form-desktop", "product-form.html", 1440, 1000],
    ["overview-mobile", "overview.html", 390, 844],
    ["menu-mobile", "overview.html#menu-open", 390, 844],
    ["products-mobile", "products.html", 390, 844],
    ["product-form-mobile", "product-form.html", 390, 844],
    ["payments-mobile", "payments.html", 390, 844],
    ["overview-dark", "overview.html#dark", 1440, 1000],
    ["overview-ultrawide", "overview.html", 2560, 1200],
    ["storefront-wide", "public-storefront.html", 1920, 1080],
    ["storefront-mobile", "public-storefront.html", 390, 844],
    ["storefront-ultrawide", "public-storefront.html", 2560, 1200],
    ["catalog-wide", "public-catalog.html", 1920, 1080],
    ["catalog-mobile", "public-catalog.html", 390, 844],
    ["login-wide", "public-login.html", 1920, 1080],
    ["register-mobile", "public-register.html", 390, 844],
    ["privacy-wide", "public-privacy.html", 1920, 1080],
    ["account-wide", "customer-account.html", 1920, 1080],
    ["admin-settings-wide", "settings.html", 1440, 1000],
    ["admin-settings-mobile", "settings.html", 390, 844],
    ["customer-settings-wide", "customer-settings.html", 1440, 1000],
    ["customer-settings-mobile", "customer-settings.html", 390, 844],
    ["checkout-mobile", "customer-checkout.html", 390, 844],
    ["invoice-wide", "customer-invoice.html", 1920, 1080],
    ["onboarding-wide", "customer-onboarding.html", 1920, 1080],
    ["onboarding-mobile", "customer-onboarding.html", 390, 844],
  ];
  const results = [];
  if (matrix) await send('Emulation.setEmulatedMedia', {features: [{name: 'prefers-reduced-motion', value: 'reduce'}]}, sessionId);
  for (const [name, file, width, height] of cases) {
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: width < 992 }, sessionId);
    const loaded = new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Snapshot load timed out: " + file)), 15000);
      events.set(sessionId + ":Page.loadEventFired", () => { clearTimeout(timer); resolve(); });
    });
    const url = new URL(origin + "/previews/" + file);
    url.searchParams.set("qa", name); // Force a document load even when only the hash changes.
    await send("Page.navigate", { url: url.href }, sessionId);
    await loaded;
    if (process.env.CODEHUB_RENDER_STRESS === '1') {
      await send('Runtime.evaluate', {expression: `(() => {
        const longEmail = 'customer'.repeat(8) + '@' + 'organization'.repeat(5) + '.example.com';
        document.querySelectorAll('a[href^="mailto:"]').forEach(el => { el.textContent = longEmail; });
        document.querySelectorAll('h1, .portfolio-project-title').forEach(el => { el.textContent = 'Project' + 'X'.repeat(140); });
        document.querySelectorAll('.nav-account > span:last-of-type').forEach(el => { el.textContent = longEmail; });
        document.querySelectorAll('.metric-value').forEach(el => { el.textContent = '₱999,999,999,999.99'; });
      })()`}, sessionId);
    }
    if (controls) {
      const opened = await send('Runtime.evaluate', {expression: `(() => {
        const state = ${JSON.stringify(name.replace(/-\d+-\d+$/, ''))};
        if (state === 'privacy' || state === 'license') bootstrap.Modal.getOrCreateInstance(document.getElementById('legal-' + state)).show();
        if (state === 'lightbox') document.querySelector('[data-lightbox-open]').click();
        if (state.startsWith('onboarding')) {
          bootstrap.Modal.getOrCreateInstance(document.getElementById('onboarding')).show();
          if (state === 'onboarding-last') for (let step = 0; step < 3; step++) document.querySelector('[data-onboarding-next]').click();
        }
        if (state === 'navbar' && innerWidth < 1200) bootstrap.Collapse.getOrCreateInstance(document.getElementById('mainNav'), {toggle: false}).show();
        if (state === 'account-menu') {
          if (innerWidth < 1200) bootstrap.Collapse.getOrCreateInstance(document.getElementById('mainNav'), {toggle: false}).show();
          bootstrap.Dropdown.getOrCreateInstance(document.querySelector('.nav-account')).show();
        }
        if (state === 'sidebar' && innerWidth < 992) document.querySelector('[data-sidebar-open]').click();
        if (state === 'confirmation') Swal.fire({title: 'Delete this project?', text: 'All files and screenshots will be removed.', showCancelButton: true, confirmButtonText: 'Delete project', cancelButtonText: 'Keep editing'});
        if (state.startsWith('upload')) {
          // Keep the request pending locally: exercise the real progress dialog without sending files.
          window.fetch = state === 'upload-error' ? () => Promise.reject(new TypeError('Preview connection interrupted')) : () => new Promise(() => {});
          const input = document.querySelector('input[data-chunked-upload]');
          const files = new DataTransfer();
          files.items.add(new File(['preview only'], 'project-deliverables-with-a-long-file-name.zip', {type: 'application/zip'}));
          input.files = files.files;
          input.form.classList.remove('needs-validation');
          input.form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
          if (state === 'upload-cancel') document.querySelector('.upload-modal .btn-outline-danger').click();
        }
      })()`}, sessionId);
      assert.equal(opened.exceptionDetails, undefined, name + ': control opens successfully');
    }
    if (process.env.CODEHUB_RENDER_PORTFOLIO === "1" || process.env.CODEHUB_RENDER_AI === "1") await send("Runtime.evaluate", { expression: "document.documentElement.setAttribute('data-bs-theme', '" + (name.endsWith("-dark") ? "dark" : "light") + "')" }, sessionId);
    await send("Runtime.evaluate", { expression: "new Promise(resolve => setTimeout(resolve, " + (process.env.CODEHUB_RENDER_PORTFOLIO === "1" ? 1000 : 350) + "))", awaitPromise: true }, sessionId);
    if (controls && name.startsWith('account-menu-')) await send('Runtime.evaluate', {expression: "const menu = document.getElementById('mainNav'); menu.scrollTop = menu.scrollHeight;"}, sessionId);
    const measured = await send("Runtime.evaluate", { expression: `(() => {
      const sidebar = document.getElementById('manageSidebar');
      const modal = document.querySelector('.legal-modal.show');
      const modalContent = modal?.querySelector('.modal-content')?.getBoundingClientRect();
      const modalBody = modal?.querySelector('.modal-body');
      return {width: innerWidth, scrollY, scrollWidth: document.documentElement.scrollWidth,
        legalModal: modalContent ? {top: modalContent.top, bottom: modalContent.bottom, width: modalContent.width,
          scrollable: modalBody.scrollHeight > modalBody.clientHeight} : null,
        sidebarVisible: sidebar ? getComputedStyle(sidebar).visibility : null,
        sidebarNavigationHeight: sidebar ? document.querySelector('.workspace-navigation')?.clientHeight : null,
        menuExpanded: document.querySelector('[data-sidebar-open]')?.getAttribute('aria-expanded'),
        mainInert: document.querySelector('.manage-main')?.inert,
        stylesLoaded: getComputedStyle(document.documentElement).fontSize === '18px',
        bodyFont: parseFloat(getComputedStyle(document.body).fontSize),
        tableFont: document.querySelector('table') ? parseFloat(getComputedStyle(document.querySelector('table')).fontSize) : null,
        contentWidth: document.querySelector('.manage-content')?.getBoundingClientRect().width,
        containerWidth: document.querySelector('.container')?.getBoundingClientRect().width,
        measureWidths: Array.from(document.querySelectorAll('.prose, .auth-shell, .auth-card, .document-measure, .form-measure')).map(el => Math.round(el.getBoundingClientRect().width)),
        clippedContent: Array.from(document.querySelectorAll('.lp-cat-row, .lp-path')).filter(el => el.getBoundingClientRect().right > innerWidth + 1 || el.getBoundingClientRect().left < -1).length,
        overflow: Array.from(document.querySelectorAll('body *')).filter(el => el.getBoundingClientRect().right > visualViewport.width + 1 && el.getBoundingClientRect().left >= 0).slice(0,12).map(el => ({tag: el.tagName, className: el.className, text: el.textContent.slice(0, 100), width: Math.round(el.getBoundingClientRect().width), whiteSpace: getComputedStyle(el).whiteSpace, overflowWrap: getComputedStyle(el).overflowWrap})),
        iconFont: sidebar ? getComputedStyle(document.querySelector('.workspace-logo i'), '::before').fontFamily : null};
    })()`, returnByValue: true }, sessionId);
    const report = measured.result.value;
    if (matrix) {
      const details = await send('Runtime.evaluate', { expression: `(() => {
        const clipped = [];
        for (const el of document.querySelectorAll('a, button, input, select, textarea, h1, h2, p, label, .geo-row, .storage-legend li')) {
          const r = el.getBoundingClientRect(), style = getComputedStyle(el);
          if (!r.width || !r.height || style.visibility !== 'visible') continue;
          const internalOverflow = el.matches('h1, h2, .btn') && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2;
          if (!internalOverflow && r.left >= -1 && r.right <= ${width} + 1) continue;
          let scrollable = false;
          for (let parent = el.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
            if (['auto', 'scroll'].includes(getComputedStyle(parent).overflowX)) { scrollable = true; break; }
          }
          if (!scrollable) clipped.push({tag: el.tagName, className: el.className, text: (el.innerText || el.name || '').slice(0, 90), left: Math.round(r.left), right: Math.round(r.right), internalOverflow});
        }
        return clipped;
      })()`, returnByValue: true }, sessionId);
      report.clippedControls = details.result.value;
      report.requestedWidth = width;
      if (controls) {
        const navigation = await send('Runtime.evaluate', {expression: `(() => {
          const collapse = document.querySelector('.site-navbar .navbar-collapse.show');
          if (!collapse || innerWidth >= 1200) return null;
          return {bottom: document.querySelector('.site-navbar').getBoundingClientRect().bottom,
            height: innerHeight, scrollable: collapse.scrollHeight <= collapse.clientHeight + 1 || ['auto', 'scroll'].includes(getComputedStyle(collapse).overflowY)};
        })()`, returnByValue: true}, sessionId);
        report.navigation = navigation.result.value;
        const overlay = await send('Runtime.evaluate', {expression: `(() => {
          const modal = document.querySelector('.modal.show .modal-content, .swal2-popup, .upload-modal[open]');
          if (!modal) return null;
          const r = modal.getBoundingClientRect();
          return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: innerHeight,
            inaccessibleButtons: [...modal.querySelectorAll('button, a.btn')].filter(el => {
              const b = el.getBoundingClientRect();
              if (!b.width || !b.height || (b.top >= r.top - 1 && b.bottom <= r.bottom + 1)) return false;
              for (let p = el.parentElement; p && p !== modal; p = p.parentElement) {
                if (['auto', 'scroll'].includes(getComputedStyle(p).overflowY)) return false;
              }
              return !['auto', 'scroll'].includes(getComputedStyle(modal).overflowY);
            }).map(el => el.textContent.trim() || el.getAttribute('aria-label')),
            bodyCanScroll: [...modal.querySelectorAll('.modal-body, .swal2-html-container')].every(el => el.scrollHeight <= el.clientHeight + 1 || ['auto', 'scroll'].includes(getComputedStyle(el).overflowY))};
        })()`, returnByValue: true}, sessionId);
        report.overlay = overlay.result.value;
      }
      results.push({name, ...report});
      if (results.length % 8 === 0) console.log('Checked', results.length, 'of', cases.length, 'cases');
      await fs.writeFile(path.join(artifacts, controls ? 'controls-progress.json' : matrixName + '-progress.json'), JSON.stringify({results, exceptions}, null, 2));
      if (controls || process.env.CODEHUB_RENDER_SHOTS === '1' || report.scrollWidth > width + 1 || report.clippedControls.length) {
        console.log(name, JSON.stringify({scrollWidth: report.scrollWidth, clipped: report.clippedControls}));
        const shot = await send('Page.captureScreenshot', {format: 'png'}, sessionId);
        await fs.writeFile(path.join(artifacts, name + '.png'), Buffer.from(shot.data, 'base64'));
      }
      continue;
    }
    if (name === "ai-settings-wide") {
      const behavior = await send("Runtime.evaluate", {expression: `(() => {
        const provider = document.getElementById('id_provider');
        const key = document.getElementById('id_api_key');
        key.value = 'unsaved-test-key'; provider.value = 'minimax'; provider.dispatchEvent(new Event('change', {bubbles:true}));
        const result = {endpoint:document.getElementById('id_endpoint').value,
          model:document.getElementById('id_model_name').value, type:document.getElementById('id_model_name').type, key:key.value,
          refreshDisabled:document.querySelector('[data-ai-action="refresh"]').disabled};
        provider.value = 'openai'; provider.dispatchEvent(new Event('change', {bubbles:true}));
        const model = document.getElementById('id_model_name');
        model.value = 'custom/model-id'; model.dispatchEvent(new Event('input', {bubbles:true}));
        result.customModel = model.value;
        document.getElementById('ai-use-frontier-default').click();
        result.frontierModel = model.value;
        return result;
      })()`, returnByValue:true}, sessionId);
      assert.equal(behavior.result.value.endpoint, 'https://api.minimax.io/v1');
      assert.equal(behavior.result.value.type, 'text');
      assert.equal(behavior.result.value.model, 'MiniMax-M3.1-Flash');
      assert.equal(behavior.result.value.customModel, 'custom/model-id');
      assert.equal(behavior.result.value.frontierModel, 'gpt-6-astra');
      assert.equal(behavior.result.value.key, '');
      assert.equal(behavior.result.value.refreshDisabled, true);
    }
    const screenshot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false }, sessionId);
    await fs.writeFile(path.join(artifacts, name + ".png"), Buffer.from(screenshot.data, "base64"));
    console.log(name, JSON.stringify(report));
    assert.equal(report.width, width, name + ": exact viewport");
    assert.ok(report.scrollWidth <= width + 1, name + ": no page-level horizontal overflow");
    assert.equal(report.clippedContent, 0, name + ": no clipped catalog content");
    if (name.includes("settings")) assert.equal(report.scrollY, 0, name + ": settings open at the profile without jumping to the password form");
    if (name.includes("-modal-")) {
      assert.ok(report.legalModal, name + ": legal document modal opened");
      assert.ok(report.legalModal.top >= 0 && report.legalModal.bottom <= height + 1, name + ": modal fits viewport");
      assert.equal(report.legalModal.scrollable, true, name + ": full agreement scrolls inside the modal");
    }
    assert.equal(report.stylesLoaded, true, name + ": workspace CSS loaded");
    if (report.sidebarVisible !== null) {
      assert.match(report.iconFont, /bootstrap-icons/, name + ": local icons loaded");
      assert.equal(report.sidebarVisible, width >= 992 || name === "menu-mobile" ? "visible" : "hidden", name + ": sidebar visibility");
      assert.equal(report.mainInert, name === "menu-mobile", name + ": mobile background interaction");
      assert.ok(report.bodyFont >= 17, name + ": readable workspace text");
      if (width >= 1920) assert.ok(report.contentWidth >= width - 320, name + ": full available width");
    } else {
      assert.ok(report.bodyFont >= 18, name + ": readable storefront text");
      if (report.containerWidth) assert.ok(report.containerWidth >= Math.min(width, 1920) - 20 && report.containerWidth <= 1920, name + ": page container fills the screen up to 1920px");
      assert.ok(report.measureWidths.every(w => w <= 1300), name + ": forms, auth and documents keep a readable width");
    }
    if (report.tableFont) assert.ok(report.tableFont >= 16, name + ": readable table text");
    results.push({ name, ...report });
  }
  await fs.writeFile(path.join(artifacts, controls ? 'controls-results.json' : matrix ? matrixName + '-results.json' : 'render-results.json'), JSON.stringify({ results, exceptions }, null, 2));
  assert.deepEqual(exceptions, [], "No browser JavaScript exceptions");
  if (matrix) {
    const failed = results.filter(r => r.width !== r.requestedWidth || r.scrollWidth > r.requestedWidth + 1 || r.clippedControls.length ||
      (r.sidebarVisible === 'visible' && r.sidebarNavigationHeight !== null && r.sidebarNavigationHeight < 1) ||
      (r.navigation && (r.navigation.bottom > r.navigation.height + 1 || !r.navigation.scrollable)) ||
      (r.overlay && (r.overlay.left < -1 || r.overlay.right > r.requestedWidth + 1 || r.overlay.top < -1 || r.overlay.bottom > r.overlay.height + 1 || !r.overlay.bodyCanScroll || r.overlay.inaccessibleButtons.length)));
    console.log('Matrix complete:', results.length, 'cases;', failed.length, 'cases need review');
    assert.deepEqual(failed.map(r => r.name), [], 'Responsive content and overlays fit their viewports');
  }
  // Close only the browser launched by this script.
  await send("Browser.close").catch(() => {});
}

run().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  if (socket) socket.close();
  if (browser && browser.exitCode === null) browser.kill();
});
