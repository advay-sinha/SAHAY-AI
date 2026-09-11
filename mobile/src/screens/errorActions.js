function createErrorActions({ onRequestHuman, onRetry }) {
  return {
    requestHuman() {
      onRequestHuman();
    },
    retry() {
      onRetry();
    },
  };
}

module.exports = { createErrorActions };
