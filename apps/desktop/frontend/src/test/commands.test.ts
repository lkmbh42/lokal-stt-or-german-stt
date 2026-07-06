import { COMMANDS, matchCommand, normalizeUtterance } from "../voice/commands";

describe("normalizeUtterance", () => {
  it("folds umlauts, case and punctuation", () => {
    expect(normalizeUtterance("Tastenkürzel anzeigen!")).toBe("tastenkurzel anzeigen");
    expect(normalizeUtterance("  Bereich   VERLAUF. ")).toBe("bereich verlauf");
  });

  it("folds transliterated umlauts identically", () => {
    expect(normalizeUtterance("Tastenkuerzel")).toBe(normalizeUtterance("Tastenkürzel"));
  });
});

describe("matchCommand", () => {
  it("matches every command via its first trigger", () => {
    for (const command of COMMANDS) {
      expect(matchCommand(command.triggers[0])).toBe(command.action);
    }
  });

  it("matches triggers embedded in a longer utterance", () => {
    expect(matchCommand("Bitte den Bereich Verlauf öffnen, danke.")).toBe("open-jobs");
    expect(matchCommand("Öhm, Sprachsteuerung beenden.")).toBe("stop-voice-control");
  });

  it("handles ASR punctuation and casing", () => {
    expect(matchCommand("Tastenkürzel anzeigen.")).toBe("open-shortcuts");
    expect(matchCommand("BEREICH AUFNAHME")).toBe("open-record");
  });

  it("ignores free-form speech (closed grammar)", () => {
    expect(matchCommand("Das Wetter ist heute schön.")).toBeNull();
    expect(matchCommand("Wir besprechen den Verlaufsplan.")).toBeNull(); // substring ≠ word
    expect(matchCommand("")).toBeNull();
  });

  it("does not fire on partial word overlap", () => {
    // "aufnahmeleiter" contains "aufnahme" but not as a whole word sequence
    expect(matchCommand("Der Aufnahmeleiter öffnen wollte")).toBeNull();
  });
});
