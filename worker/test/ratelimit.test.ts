import { SELF } from "cloudflare:test";
import { beforeEach, describe, expect, it } from "vitest";
import { resetData } from "./apply-schema";
import { control } from "./origin";

beforeEach(async () => {
  await control();
  await resetData();
});

const lookup = (ip: string) =>
  SELF.fetch("https://wayfinder.test/api/search?q=ratelimit", { headers: { "cf-connecting-ip": ip } });

describe("per-client limit", () => {
  it("answers 429 once one client passes the per-minute lookup limit", async () => {
    let last = 0;
    for (let i = 0; i < LOOKUPS_PER_MINUTE + 1; i++) last = (await lookup("203.0.113.7")).status;
    expect(last).toBe(429);
    // Another client still gets through, and health is never limited.
    expect((await lookup("203.0.113.8")).status).not.toBe(429);
    const health = await SELF.fetch("https://wayfinder.test/api/health", {
      headers: { "cf-connecting-ip": "203.0.113.7" },
    });
    expect(health.status).toBe(200);
  });
});

const LOOKUPS_PER_MINUTE = 30;
