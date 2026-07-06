/**
 * Screen-reader live regions (polite + assertive) — same pattern as the
 * desktop frontend, without the live-transcript batching (Variant B has no
 * streaming view; recordings are uploaded as batch jobs).
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
}

const AnnouncerContext = createContext<AnnouncerApi | null>(null);

export function useAnnouncer(): AnnouncerApi {
  const api = useContext(AnnouncerContext);
  if (!api) throw new Error("useAnnouncer must be used inside <AnnouncerProvider>");
  return api;
}

export function AnnouncerProvider({ children }: { children: React.ReactNode }) {
  const [politeText, setPoliteText] = useState("");
  const [assertiveText, setAssertiveText] = useState("");
  const timers = useRef<{ polite?: number; assertive?: number }>({});

  const announce = useCallback(
    (message: string, priority: "polite" | "assertive" = "polite") => {
      const setter = priority === "assertive" ? setAssertiveText : setPoliteText;
      setter("");
      window.clearTimeout(timers.current[priority]);
      timers.current[priority] = window.setTimeout(() => setter(message), 50);
    },
    [],
  );

  const api = useMemo(() => ({ announce }), [announce]);

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
