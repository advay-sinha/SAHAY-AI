/** Creates a synchronous-lock controller for one human-request lifecycle. */
function createHandoffRequestController(onRequestHuman, onStateChange) {
  let disposed = false;
  let inFlight = false;
  let requested = false;

  async function request() {
    if (disposed || inFlight || requested) return false;

    inFlight = true;
    onStateChange("requesting");

    try {
      await onRequestHuman();
      if (disposed) return false;

      requested = true;
      onStateChange("requested");
      return true;
    } catch {
      if (disposed) return false;

      onStateChange("failed");
      return false;
    } finally {
      inFlight = false;
    }
  }

  function dispose() {
    disposed = true;
  }

  return { dispose, request };
}

module.exports = { createHandoffRequestController };
