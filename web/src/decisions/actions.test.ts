import { buildDecisionRedirect } from "./redirect";

test("buildDecisionRedirect preserves valid filters, error, and row anchor (#163)", () => {
  expect(
    buildDecisionRedirect("/runs/r1", {
      returnQuery: "coverage=gap&status=undecided&evil=1",
      anchor: "URS-TP201-001",
    }),
  ).toBe("/runs/r1?coverage=gap&status=undecided#URS-TP201-001");

  expect(
    buildDecisionRedirect("/runs/r1", {
      error: "refused",
      returnQuery: "coverage=invalid",
      anchor: "bad anchor!",
    }),
  ).toBe("/runs/r1?error=refused");
});
