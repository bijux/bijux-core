/* Scoped to the admitted native runtime; clipboard success remains native-owned. */
const __bijuxClipboardStatuses = new WeakMap();

function __bijuxClipboardClear(trigger) {
  const status = __bijuxClipboardStatuses.get(trigger);
  if (status) status.remove();
  __bijuxClipboardStatuses.delete(trigger);
}

function __bijuxClipboardFailure(event) {
  const trigger = event.trigger;
  if (!(trigger instanceof HTMLElement)) return "Copy failed. Use your browser's Copy command.";
  trigger.focus();
  let selected = false;
  try {
    const selector = trigger.getAttribute("data-clipboard-target");
    const target = selector && document.querySelector(selector);
    const selection = window.getSelection();
    if (target && selection && target.textContent) {
      const range = document.createRange();
      range.selectNodeContents(target);
      selection.removeAllRanges();
      selection.addRange(range);
      selected = selection.rangeCount > 0 &&
        selection.getRangeAt(0).startContainer === target &&
        selection.getRangeAt(0).endContainer === target &&
        selection.getRangeAt(0).startOffset === 0 &&
        selection.getRangeAt(0).endOffset === target.childNodes.length;
    }
  } catch (_) {
    // Selection is optional; failure still explains the ordinary manual path.
  }
  let status = __bijuxClipboardStatuses.get(trigger);
  if (!status || !status.isConnected) {
    status = document.createElement("p");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    status.className = "md-code__copy-status";
    (trigger.closest(".highlight") || trigger.parentElement).after(status);
    __bijuxClipboardStatuses.set(trigger, status);
  }
  status.textContent = selected
    ? "Copy failed. Code selected; use your browser's Copy command."
    : "Copy failed. Select the code and use your browser's Copy command.";
  return status.textContent;
}
