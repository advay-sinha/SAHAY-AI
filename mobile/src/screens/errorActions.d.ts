export interface ErrorActions {
  requestHuman(): void;
  retry(): void;
}

interface ErrorActionCallbacks {
  onRequestHuman: () => void;
  onRetry: () => void;
}

export function createErrorActions(callbacks: ErrorActionCallbacks): ErrorActions;
