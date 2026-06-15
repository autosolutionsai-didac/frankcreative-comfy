import { describe, expect, it } from "vitest";

// Vitest runs this static contract in Node; the app build does not execute it.
// @ts-expect-error The app tsconfig intentionally does not include Node types.
const { readFileSync } = await import("node:fs");
const styles = readFileSync("./src/styles.css", "utf-8") as string;

describe("Frank brand theme", () => {
  it("uses the official frank body fonts and masterbrand colour tokens", () => {
    expect(styles).toContain('font-family: "Pitch"');
    expect(styles).toContain("Pitch-Semibold.woff2");
    expect(styles).toContain('font-family: "Founders Grotesk Text"');
    expect(styles).toContain("FoundersGroteskText-Light.woff2");
    expect(styles).toContain("--pink: #ffb6a5");
    expect(styles).toContain("--ink: #3f2a2d");
    expect(styles).toContain("--white: #ffffff");
    expect(styles).toContain('--font-heading: "Pitch"');
    expect(styles).toContain('--font-body: "Founders Grotesk Text"');
  });
});
