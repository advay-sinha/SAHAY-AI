const { validateVictimEvent } = require("../net/victimPayload");

function copyState(draft, messages) {
  return {
    draft,
    messages: messages.map((message) => ({ ...message })),
  };
}

function createChatSendController(onSend, onStateChange) {
  let disposed = false;
  let inFlight = false;
  let nextId = 1;
  let draft = "";
  let messages = [];

  function emit() {
    if (!disposed) onStateChange(copyState(draft, messages));
  }

  function setDraft(text) {
    if (disposed) return false;
    draft = text;
    emit();
    return true;
  }

  async function send() {
    const text = draft.trim();
    if (disposed || inFlight || text.length === 0) return false;

    inFlight = true;
    const id = nextId;
    nextId += 1;
    messages = [...messages, { id, text, status: "pending" }];
    emit();

    try {
      await onSend(text, id);
      if (disposed) return false;

      messages = messages.map((message) => (
        message.id === id ? { ...message, status: "sent" } : message
      ));
      if (draft.trim() === text) draft = "";
      emit();
      return true;
    } catch {
      if (disposed) return false;

      messages = messages.map((message) => (
        message.id === id ? { ...message, status: "failed" } : message
      ));
      draft = text;
      emit();
      return false;
    } finally {
      inFlight = false;
    }
  }

  async function retry(id) {
    if (disposed || inFlight) return false;
    const failed = messages.find((message) => message.id === id && message.status === "failed");
    if (!failed) return false;

    inFlight = true;
    messages = messages.map((message) => (
      message.id === id ? { ...message, status: "pending" } : message
    ));
    emit();

    try {
      await onSend(failed.text, id);
      if (disposed) return false;

      messages = messages.map((message) => (
        message.id === id ? { ...message, status: "sent" } : message
      ));
      if (draft.trim() === failed.text) draft = "";
      emit();
      return true;
    } catch {
      if (disposed) return false;

      messages = messages.map((message) => (
        message.id === id ? { ...message, status: "failed" } : message
      ));
      draft = failed.text;
      emit();
      return false;
    } finally {
      inFlight = false;
    }
  }

  function getState() {
    return copyState(draft, messages);
  }

  function dispose() {
    disposed = true;
  }

  return { dispose, getState, retry, send, setDraft };
}

function selectDisplayMessages(values, consent, aiPermitted) {
  if (!Array.isArray(values)) return [];

  const selected = [];
  for (const value of values) {
    const event = validateVictimEvent(value);
    if (event?.type === "assistant.turn") {
      if (consent === "granted" && aiPermitted === true) {
        selected.push({
          id: `assistant:${event.turn_id}`,
          labelKey: "chat.assistant",
          text: event.text,
        });
      }
    } else if (event?.type === "officer.message") {
      selected.push({
        id: `human_officer:${event.turn_id}`,
        labelKey: "chat.human_officer",
        text: event.text,
      });
    }
  }
  return selected;
}

module.exports = { createChatSendController, selectDisplayMessages };
