import test from "node:test";
import assert from "node:assert/strict";
import {
  aidLinks,
  monetaryRows,
  compactUSD,
  totalBasis,
} from "./moneyAtlas.js";
import { flowKind, flowMeasure } from "./flows.js";
import { connectionReport } from "./connectionReport.js";

test("national monetary observations retain signed and zero values without inventing bilateral endpoints", () => {
  const rows = monetaryRows({
    rows: [
      { country: "GH", year: 2023, value: "-300" },
      { country: "US", year: 2023, value: "0" },
      { country: "WLD", year: 2023, value: "400" },
    ],
  });
  assert.equal(rows.length, 2);
  assert.equal(rows[0].value, "-300");
  assert.equal(rows[1].value, "0");
  assert.equal(rows[0].from, undefined);
  assert.equal(monetaryRows({ rows }, { code: "US" }).length, 1);
  assert.equal(compactUSD(null), "Unavailable");
  assert.equal(compactUSD("0"), "$0");
  assert.match(totalBasis({ total_basis: "covered_economies_sum" }), /partial/);
});

test("only positive reported net aid pairs animate, from actual donor to recipient", () => {
  const s = {
    aid: {
      rows: [
        {
          from: "US",
          to: "GH",
          year: 2023,
          usd: "123456.25",
          source_url: "https://data.worldbank.org/indicator/DC.DAC.USAL.CD",
          mirror_url: "https://example.org/pinned",
        },
        { from: "GH", to: "US", year: 2023, usd: "-10" },
        { from: "US", to: "GH", year: 2023, usd: "0" },
        { from: "EU", to: "GH", year: 2023, usd: "999" },
      ],
    },
  };
  const links = aidLinks(s);
  assert.equal(links.length, 1);
  assert.equal(links[0].reporter.code, "US");
  assert.equal(links[0].partner.code, "GH");
  assert.equal(links[0].exactUSD, "123456.25");
  assert.equal(flowKind(links[0]), "aid");
  assert.match(flowMeasure(links[0]), /net aid/);
  assert.equal(aidLinks(s, { code: "FR" }).length, 0);
  const report = connectionReport(
    links[0],
    null,
    "Obtain independently attributed recipient credits.",
  );
  assert.match(report, /123456.25/);
  assert.match(report, /Net of repayments/);
  assert.match(report, /Pinned data extract/);
});
