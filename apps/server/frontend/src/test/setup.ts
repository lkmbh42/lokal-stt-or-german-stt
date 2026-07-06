import "@testing-library/jest-dom/vitest";

// jsdom lacks <dialog> methods
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
}
if (!HTMLDialogElement.prototype.close) {
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}

// jsdom lacks Web Audio — earcons degrade silently, but constructing must not throw
class FakeAudioContext {
  currentTime = 0;
  destination = {};
  createOscillator() {
    return {
      type: "sine",
      frequency: { value: 0 },
      connect: () => ({ connect: () => undefined }),
      start: () => undefined,
      stop: () => undefined,
    };
  }
  createGain() {
    const node = {
      gain: {
        setValueAtTime: () => undefined,
        exponentialRampToValueAtTime: () => undefined,
      },
      connect: (target: unknown) => target,
    };
    return node;
  }
  close() {
    return Promise.resolve();
  }
}
(globalThis as Record<string, unknown>).AudioContext ??= FakeAudioContext;
