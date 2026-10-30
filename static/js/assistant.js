(() => {
  'use strict';
  const form = document.getElementById('assistant-chat-form');
  if (!form) return;
  const question = document.getElementById('assistant-question');
  const log = document.getElementById('assistant-messages');
  const errorBox = document.getElementById('assistant-error');
  const state = document.getElementById('assistant-state');
  const submit = form.querySelector('[type="submit"]');
  let busy = false;
  function append(role, text) {
    const article = document.createElement('article');
    article.className = 'assistant-message assistant-message-' + role;
    const speaker = document.createElement('p');
    speaker.className = 'assistant-speaker';
    speaker.textContent = role === 'user' ? 'You' : 'Assistant';
    const body = document.createElement('div');
    body.className = 'assistant-message-text';
    // Model output is untrusted text, never HTML or executable Markdown.
    body.textContent = text;
    article.append(speaker, body);
    log.append(article);
    log.scrollTop = log.scrollHeight;
    return article;
  }
  function updateRevenue(snapshot) {
    const container = document.getElementById('assistant-revenue');
    container.replaceChildren();
    snapshot.periods.forEach(period => {
      const panel = document.createElement('div');
      panel.className = 'assistant-revenue-period';
      const heading = document.createElement('h3');
      heading.textContent = period.label;
      panel.append(heading);
      period.totals.forEach(total => {
        const amount = document.createElement('strong');
        amount.textContent = total.currency + ' ' + total.amount;
        const count = document.createElement('span');
        count.textContent = total.payments + ' confirmed payment' + (total.payments === 1 ? '' : 's');
        panel.append(amount, count);
      });
      const start = document.createElement('small');
      start.textContent = 'From ' + period.start.slice(0, 10);
      panel.append(start);
      container.append(panel);
    });
    document.getElementById('revenue-as-of').textContent = 'As of ' + snapshot.as_of + ' · ' + snapshot.timezone;
  }
  document.querySelectorAll('[data-chat-prompt]').forEach(button => button.addEventListener('click', () => {
    if (question.disabled || busy) return;
    question.value = button.dataset.chatPrompt;
    question.focus();
  }));
  question.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!busy && !question.disabled) form.requestSubmit();
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const text = question.value.trim();
    if (busy || question.disabled || !text || text.length > 3000) return;
    busy = true;
    submit.disabled = true;
    question.readOnly = true;
    errorBox.hidden = true;
    document.getElementById('assistant-welcome')?.remove();
    const pending = append('user', text);
    state.textContent = 'Getting an answer from your AI provider…';
    log.setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 65000);
    try {
      const response = await fetch(form.dataset.url, {method: 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value},
        body: JSON.stringify({message: text})});
      if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('Your session may have expired. Reload the page and sign in again.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'The message could not be sent.');
      append('assistant', data.answer);
      updateRevenue(data.revenue);
      question.value = '';
      state.textContent = 'Answered using the app manual and fresh revenue totals.';
    } catch (error) {
      pending.remove();
      errorBox.textContent = error.name === 'AbortError' ? 'The request timed out. Your message is still below; try again.' : error.message;
      errorBox.hidden = false;
      state.textContent = 'Message not completed. You can try again.';
    } finally {
      clearTimeout(timer);
      busy = false;
      submit.disabled = false;
      question.readOnly = false;
      log.setAttribute('aria-busy', 'false');
      question.focus();
    }
  });
  log.scrollTop = log.scrollHeight;
})();
