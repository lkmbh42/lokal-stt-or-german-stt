/**
 * Screen-reader announcement infrastructure.
 *
 * Two visually hidden live regions: `polite` (progress, transcript batches)
 * and `assertive` (recording state changes, errors). Live-transcript
 * announcements can be muted by the user — they then only get a completion
 * cue (see brief, Accessibility section).
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";

export interface AnnouncerApi {
  announce: (message: string, priority?: "polite" | "assertive") => void;
  liveTranscriptMuted: boolean;
  setLiveTranscriptMuted: (muted: boolean) => void;
  earconsEnabled: boolean;
  setEarconsEnabled: (enabled: boolean) => void;
}

const AnnouncerContext = createContext<AnnouncerApi | null>(null);

export function useAnnouncer(): AnnouncerApi {
  const api = useContext(AnnouncerContext);
  if (!api) throw new Error("useAnnouncer must be used inside <AnnouncerProvider>");
  return api;
}

function readSetting(key: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : raw === "true";
  } catch {
    return fallback;
  }
}

export function AnnouncerProvider({ children }: { children: React.ReactNode }) {
  const [politeText, setPoliteText] = useState("");
  const [assertiveText, setAssertiveText] = useState("");
  const [liveTranscriptMuted, setLiveMutedState] = useState(() =>
    readSetting("stt.liveTranscriptMuted", false),
  );
  const [earconsEnabled, setEarconsState] = useState(() =>
    readSetting("stt.earconsEnabled", true),
  );
  const timers = useRef<{ polite?: number; assertive?: number }>({});

  const announce = useCallback(
    (message: string, priority: "polite" | "assertive" = "polite") => {
      const setter = priority === "assertive" ? setAssertiveText : setPoliteText;
      // clear + re-set so repeating the same text is re-announced
      setter("");
      window.clearTimeout(timers.current[priority]);
      timers.current[priority] = window.setTimeout(() => setter(message), 50);
    },
    [],
  );

  const setLiveTranscriptMuted = useCallback((muted: boolean) => {
    setLiveMutedState(muted);
    try {
      window.localStorage.setItem("stt.liveTranscriptMuted", String(muted));
    } catch {
      /* private mode: setting simply doesn't persist */
    }
  }, []);

  const setEarconsEnabled = useCallback((enabled: boolean) => {
    setEarconsState(enabled);
    try {
      window.localStorage.setItem("stt.earconsEnabled", String(enabled));
    } catch {
      /* private mode: setting simply doesn't persist */
    }
  }, []);

  const api = useMemo(
    () => ({
      announce,
      liveTranscriptMuted,
      setLiveTranscriptMuted,
      earconsEnabled,
      setEarconsEnabled,
    }),
    [announce, liveTranscriptMuted, setLiveTranscriptMuted, earconsEnabled, setEarconsEnabled],
  );

  return (
    <AnnouncerContext.Provider value={api}>
      {children}
      <div aria-live="polite" role="status" className="visually-hidden" data-testid="live-polite">
        {politeText}
      </div>
      <div
        aria-live="assertive"
        role="alert"
        className="visually-hidden"
        data-testid="live-assertive"
      >
        {assertiveText}
      </div>
    </AnnouncerContext.Provider>
  );
}

/**
 * Batches transcript fragments so screen readers are not flooded token by
 * token: fragments arriving within `intervalMs` are joined into a single
 * announcement (≈ sentence-sized chunks at natural speech pause boundaries).
 */
export class TranscriptBatcher {
  private buffer: string[] = [];
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    private readonly emit: (text: string) => void,
    private readonly intervalMs = 2500,
  ) {}

  add(fragment: string): void {
    const text = fragment.trim();
    if (!text) return;
    this.buffer.push(text);
    if (this.timer === undefined) {
      this.timer = setTimeout(() => this.flush(), this.intervalMs);
    }
  }

  flush(): void {
    if (this.timer !== undefined) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
    if (this.buffer.length > 0) {
      this.emit(this.buffer.join(" "));
      this.buffer = [];
    }
  }

  dispose(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.buffer = [];
  }
}
