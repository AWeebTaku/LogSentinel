import { describe, expect, it } from "vitest";
import { ACTION_LABEL, TRANSITIONS, ago, fmtBytes, fmtMs, histogramRows } from "./format";

describe("format", () => {
  it("formats latency", () => {
    expect(fmtMs(null)).toBe("n/a");
    expect(fmtMs(4.26)).toBe("4.3 ms");
    expect(fmtMs(72.4)).toBe("72 ms");
    expect(fmtMs(1500)).toBe("1.50 s");
  });
  it("formats ages", () => {
    const now = 1_000_000_000_000;
    expect(ago((now - 5_000) * 1e6, now)).toBe("5 s ago");
    expect(ago((now - 125_000) * 1e6, now)).toBe("2 min ago");
    expect(ago((now - 7_300_000) * 1e6, now)).toBe("2 h ago");
  });
  it("formats sizes", () => {
    expect(fmtBytes(500)).toBe("500 B");
    expect(fmtBytes(2048)).toBe("2.0 KB");
  });
  it("offers the same lifecycle moves as the backend", () => {
    expect(TRANSITIONS.open).toEqual(["acknowledged", "resolved", "false_positive"]);
    expect(TRANSITIONS.resolved).toEqual(["open"]);
    for (const list of Object.values(TRANSITIONS)) for (const s of list) expect(ACTION_LABEL[s]).toBeTruthy();
    for (const [from, list] of Object.entries(TRANSITIONS)) expect(list).not.toContain(from);
  });
  it("builds histogram rows", () => {
    expect(histogramRows([0.5, 0.6, 0.7], [3, 4])).toEqual([
      { group: "Alerts", key: "0.50", value: 3 },
      { group: "Alerts", key: "0.60", value: 4 },
    ]);
  });
});
