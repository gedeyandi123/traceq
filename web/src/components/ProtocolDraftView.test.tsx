// The Protocol Draft screen (spec #196, user stories 6-9; ticket #210): Test Steps in draft
// order with their AC as read, the URS value, comparators and findings, then the findings
// about the whole document, with the decision controls of slice 1.
import { render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/id.json";
import type { DecisionView } from "./Decisions";
import { counts, decision, RUN_ID } from "./decisions.fixture";
import { deviates, draftView, notTested, proposal } from "./protocolDraft.fixture";
import { ProtocolDraftView } from "./ProtocolDraftView";

const action = async () => {};
const readOnly: DecisionView = { access: { mode: "readOnly", why: "noRole" } };

function renderDraft(view = draftView([]), decisions: DecisionView = readOnly) {
  return render(
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <ProtocolDraftView draft={view} runId={RUN_ID} decisions={decisions} />
    </NextIntlClientProvider>,
  );
}

const imported = draftView([
  { finding: deviates, proposal: proposal({ id: 40, position: 0 }) },
  {
    finding: notTested,
    proposal: proposal({ id: 41, position: 1, state: "decided", decisions: [decision({ id: 9 })] }),
  },
]);

function stepRows() {
  const steps = within(screen.getByRole("region", { name: "Langkah uji" }));
  return steps.getAllByRole("row").slice(1);
}

test("lists every Test Step in draft order with its AC as read, the URS value and its citation", () => {
  renderDraft(imported);

  expect(screen.getByText("OQ-TP201 rev 0, paket tinjauan TP-201-OQ-draft")).toBeDefined();
  expect(screen.getByText(/dirancang TraceQ sendiri tidak ditampilkan/)).toBeDefined();
  const rows = stepRows();
  expect(rows.map((r) => r.querySelector("th")?.textContent)).toEqual(["OQ-01", "OQ-02", "OQ-03"]);

  const first = within(rows[0]!);
  expect(first.getByText("minimal 100 kN")).toBeDefined();
  expect(first.getByText("URS-TP201-001")).toBeDefined();
  expect(first.getByText("≥ 100 kN")).toBeDefined();
  const urs = first.getByRole("link", { name: "URS-TP201 rev 1, hlm. 1" });
  expect(urs.getAttribute("href")).toBe(`/api/runs/${RUN_ID}/documents/URS-TP201/1#page=1`);
  expect(urs.getAttribute("title")).toBe("Gaya kompresi minimal 100 kN.");
  // The draft is not a corpus document: its citation names the page and quote, no link.
  const ac = first.getByText("OQ-TP201 rev 0, hlm. 1");
  expect(ac.closest("a")).toBeNull();
  expect(ac.getAttribute("title")).toBe("OQ-01 Gaya kompresi minimal 100 kN");
  expect(first.getByText("Sesuai URS")).toBeDefined();
  expect(first.getByText("Tidak ada temuan")).toBeDefined();
});

test("shows the comparators available, or none", () => {
  renderDraft(imported);
  const [first, second] = stepRows();
  expect(within(first!).getByText(/FAT-M-02/).textContent).toContain("102 kN");
  expect(within(first!).getByRole("link", { name: "FAT-TP201-M rev 0, hlm. 1" })).toBeDefined();
  expect(within(second!).getByText("tidak ada")).toBeDefined();
});

test("a step that is not compared says so with the reason, and has no finding", () => {
  renderDraft(imported);
  const second = within(stepRows()[1]!);
  expect(second.getByText("Tidak dibandingkan: two-sided URS range")).toBeDefined();
  expect(second.queryByText("Menyimpang dari URS")).toBeNull();
  expect(second.queryByRole("button")).toBeNull();
});

test("a finding sits on its Test Step, the document-level ones after the steps", () => {
  renderDraft(imported);
  const third = within(stepRows()[2]!);
  expect(third.getByText("Menyimpang dari URS")).toBeDefined();
  expect(third.getByText("Kriteria penerimaan lebih longgar dari URS")).toBeDefined();
  expect(third.getByText(deviates.detail)).toBeDefined();
  expect(third.getByText("Belum diputuskan")).toBeDefined();
  expect(third.queryByText(notTested.detail)).toBeNull();

  const doc = within(screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" }));
  expect(doc.getByText("Persyaratan tanpa langkah uji")).toBeDefined();
  expect(doc.getByText("URS-TP201-031")).toBeDefined();
  expect(doc.getByText(notTested.detail)).toBeDefined();
  expect(doc.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(doc.getByText("OQ-TP201 rev 0, hlm. 8").getAttribute("title")).toBe("URS-TP201-031 OQ-21");
  // Document order: the steps come before the findings about the whole document.
  const steps = screen.getByRole("region", { name: "Langkah uji" });
  const whole = screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" });
  expect(steps.compareDocumentPosition(whole) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("the deciding role gets accept and reject on a draft finding, reject with a reason", () => {
  renderDraft(imported, {
    counts: { ...counts, draft: { ...counts.draft, total: 2, undecided: 1, accepted: 1 } },
    access: { mode: "decide", action },
  });
  const third = within(stepRows()[2]!);
  const accept = third.getByRole("button", { name: "Terima" }).closest("form")!;
  expect(within(accept).queryByRole("textbox")).toBeNull();
  expect(accept.querySelector('input[name="screen"]')?.getAttribute("value")).toBe("draft");
  expect(accept.querySelector('input[name="proposal_id"]')?.getAttribute("value")).toBe("40");
  const reject = third.getByRole("button", { name: "Tolak" }).closest("form")!;
  expect(within(reject).getByRole("textbox").hasAttribute("required")).toBe(true);
  expect(screen.getByText("1/2 usulan sudah diputuskan")).toBeDefined();
  const tally = within(screen.getByRole("table", { name: "Jumlah keputusan" }));
  expect(tally.getByRole("row", { name: /Temuan draf protokol/ })).toBeDefined();
  expect(tally.queryByRole("row", { name: /Baris cakupan/ })).toBeNull();
});

test("a reader sees the decisions and no decision control", () => {
  renderDraft(imported);
  expect(screen.getByText("Diterima oleh Ayu Kartika Sari, 16/11/2026 09.30 UTC")).toBeDefined();
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByText("Tolak…")).toBeNull();
  expect(screen.getByText(/Hanya membaca: identitas ini tidak memiliki peran/)).toBeDefined();
});

test("a run not imported shows the findings without decision state", () => {
  renderDraft(draftView([{ finding: deviates, proposal: null }]), {
    access: { mode: "readOnly", why: "notImported" },
  });
  expect(screen.getByText(deviates.detail)).toBeDefined();
  expect(screen.queryByText("Belum diputuskan")).toBeNull();
  const doc = within(screen.getByRole("region", { name: "Temuan tentang seluruh dokumen" }));
  expect(doc.getByText("Tidak ada temuan tentang seluruh dokumen")).toBeDefined();
});

test("the summary counts the steps, those not compared and the document findings", () => {
  renderDraft(imported);
  const summary = within(screen.getByRole("list", { name: "Ringkasan draf" }));
  const items = summary.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")]);
  expect(items).toEqual([
    ["3 Langkah uji", "#draft-steps"],
    ["1 Langkah uji tidak dibandingkan", "#draft-not-compared"],
    ["1 Temuan tentang seluruh dokumen", "#draft-document"],
  ]);
});
