/* Checkout page: switches payment panels and drives the PayPal JS SDK
   (PayPal Buttons and Advanced Card Fields). Card data is typed into
   PayPal-hosted iframes; this script only ever handles PayPal order IDs. */
(function () {
  "use strict";

  const config = document.getElementById("checkout-config");
  if (!config) return;
  const data = JSON.parse(config.textContent);

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function postJSON(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (json) {
        if (response.redirected || response.status === 401) throw new Error("Your session has expired. Refresh the page and sign in before continuing.");
        if (!response.ok) throw new Error(json.error || "Something went wrong. Please try again.");
        return json;
      });
    });
  }

  let lastError = "";
  function showError(method, message) {
    const box = document.getElementById("error-" + method);
    if (!box) return;
    box.textContent = message;
    box.classList.toggle("d-none", !message);
    if (message) box.focus();
    if (message && message !== lastError && window.FBAlerts) {
      window.FBAlerts.notify(message, "error", "Payment notice").catch(function () {});
    }
    lastError = message;
  }

  // ----- Method switching ----------------------------------------------------
  const radios = document.querySelectorAll("input[name=payment_method]");
  function showPanel(method) {
    document.querySelectorAll("[data-panel]").forEach(function (panel) {
      const active = panel.getAttribute("data-panel") === method;
      panel.hidden = !active;
    });
    const url = new URL(window.location.href);
    url.searchParams.set("method", method);
    window.history.replaceState(null, "", url);
  }
  radios.forEach(function (radio) {
    radio.addEventListener("change", function () { showPanel(radio.value); });
  });
  const checked = document.querySelector("input[name=payment_method]:checked");
  if (checked) showPanel(checked.value);

  // ----- PayPal SDK --------------------------------------------------------
  if (!data.sdkEnabled) return;

  function createOrder(method, extra) {
    showError(method, "");
    const body = { kind: data.kind, reference: data.reference, method: method };
    if (extra) Object.keys(extra).forEach(function (key) { body[key] = extra[key]; });
    return postJSON(data.createUrl, body).then(
      function (json) {
        if (!json.id) throw new Error("Checkout could not start. Refresh the page and try again.");
        return json.id;
      }
    );
  }

  function captureOrder(method, orderID) {
    return postJSON(data.captureUrl, { orderID: orderID }).then(function (json) {
      if (!json.redirect) throw new Error("We could not confirm the result. Check your order before trying again.");
      window.location.href = json.redirect;
    });
  }

  function whenSdkReady(callback) {
    if (window.paypal) return callback();
    const script = document.getElementById("paypal-sdk");
    if (script) {
      script.addEventListener("load", callback);
      script.addEventListener("error", sdkFailed);
    }
    setTimeout(function () { if (!window.paypal) sdkFailed(); }, 15000);
  }

  function sdkFailed() {
    const message = "The payment form could not load. Refresh the page or choose another payment method.";
    showError("paypal", message);
    showError("card", message);
    const submit = document.getElementById("card-submit");
    if (submit) submit.disabled = true;
  }

  // PayPal's own "Debit or Credit Card" button: PayPal shows the card form, no PayPal account needed.
  // Used when Advanced Card Fields isn't offered for the merchant account (e.g. the Philippines).
  function renderCardButton() {
    const container = document.getElementById("card-button");
    const unavailable = function () { document.getElementById("card-not-eligible").classList.remove("d-none"); };
    if (!container || !window.paypal.Buttons || !window.paypal.FUNDING) return unavailable();
    const button = window.paypal.Buttons({
      fundingSource: window.paypal.FUNDING.CARD,
      style: { layout: "vertical", shape: "rect" },
      createOrder: function () { return createOrder("card", { cardButton: true }); },
      onApprove: function (d) {
        return captureOrder("card", d.orderID).catch(function (err) { showError("card", err.message); });
      },
      onCancel: function () { showError("card", "Payment cancelled. You have not been charged."); },
      onError: function (err) {
        showError("card", (err && err.message) || "Your card could not be processed. Check the details or try another card.");
      },
    });
    if (!button.isEligible()) return unavailable();
    container.classList.remove("d-none");
    button.render(container);
  }

  whenSdkReady(function () {
    // PayPal Buttons
    const buttonsContainer = document.getElementById("paypal-buttons");
    if (buttonsContainer && window.paypal.Buttons) {
      window.paypal
        .Buttons({
          style: { layout: "vertical", shape: "rect", label: "pay" },
          createOrder: function () { return createOrder("paypal"); },
          onApprove: function (d) {
            return captureOrder("paypal", d.orderID).catch(function (err) { showError("paypal", err.message); });
          },
          onCancel: function () { showError("paypal", "Payment cancelled. You have not been charged."); },
          onError: function (err) {
            showError("paypal", (err && err.message) || "PayPal could not start. Please try again.");
          },
        })
        .render(buttonsContainer);
    }

    // Advanced Card Fields
    const cardForm = document.getElementById("card-form");
    if (cardForm && window.paypal.CardFields) {
      const submit = document.getElementById("card-submit");
      submit.disabled = false;
      const cardFields = window.paypal.CardFields({
        createOrder: function () { return createOrder("card"); },
        onApprove: function (d) {
          return captureOrder("card", d.orderID).catch(function (err) {
            showError("card", err.message);
            window.FB.setLoading(submit, false);
          });
        },
        onError: function () {
          showError("card", "Your card could not be processed. Check the details or try another card.");
          window.FB.setLoading(submit, false);
        },
        style: { input: { "font-size": "16px", "font-family": "Inter, system-ui, sans-serif" } },
      });

      if (!cardFields.isEligible()) {
        cardForm.classList.add("d-none");
        renderCardButton();
        return;
      }
      cardFields.NameField().render("#card-name");
      cardFields.NumberField().render("#card-number");
      cardFields.ExpiryField().render("#card-expiry");
      cardFields.CVVField().render("#card-cvv");

      cardForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (submit.getAttribute("aria-busy") === "true") return;
        showError("card", "");
        window.FB.setLoading(submit, true);
        cardFields.submit().catch(function () {
          showError("card", "Please check your card details and try again.");
          window.FB.setLoading(submit, false);
        });
      });
    } else if (cardForm) {
      cardForm.classList.add("d-none");
      renderCardButton();
    }
  });
})();
