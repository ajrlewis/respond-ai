type EventListener = (event: Event) => void;

export class MockEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  static instances: MockEventSource[] = [];

  readonly CONNECTING = MockEventSource.CONNECTING;
  readonly OPEN = MockEventSource.OPEN;
  readonly CLOSED = MockEventSource.CLOSED;

  readonly url: string;
  readonly withCredentials: boolean;
  readyState = MockEventSource.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;

  private listeners = new Map<string, Set<EventListener>>();

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(init?.withCredentials);
    MockEventSource.instances.push(this);

    queueMicrotask(() => {
      if (this.readyState === MockEventSource.CLOSED) return;
      this.readyState = MockEventSource.OPEN;
      this.onopen?.(new Event("open"));
    });
  }

  addEventListener(type: string, listener: EventListener): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set<EventListener>());
    }
    this.listeners.get(type)?.add(listener);
  }

  removeEventListener(type: string, listener: EventListener): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.readyState = MockEventSource.CLOSED;
  }

  emit(type: string, data: unknown): void {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    const messageEvent = new MessageEvent(type, { data: payload });

    if (type === "message") {
      this.onmessage?.(messageEvent);
    }
    if (type === "error") {
      this.onerror?.(new Event("error"));
    }

    this.listeners.get(type)?.forEach((listener) => listener(messageEvent));
  }

  static latest(): MockEventSource | null {
    return MockEventSource.instances[MockEventSource.instances.length - 1] ?? null;
  }

  static reset(): void {
    MockEventSource.instances = [];
  }
}

export function installMockEventSource(): void {
  Object.defineProperty(globalThis, "EventSource", {
    writable: true,
    configurable: true,
    value: MockEventSource,
  });
}

export function resetMockEventSources(): void {
  MockEventSource.reset();
}

export function getLatestMockEventSource(): MockEventSource | null {
  return MockEventSource.latest();
}
