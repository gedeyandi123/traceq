// A Protocol started from the Protocol Draft (spec #375, ticket S4b; ADR 0012 as amended 26 Nov
// 2026): the pinned source and its warning, the draft steps no requirement owns, the candidates
// and findings of a row, the reason an accepted finding needs, the latest draft revision a
// signature names, the version 2 frozen copy, and the labels "dev only", "awaiting the
// practitioner (#245)" and "not reviewed by a practitioner".
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";

import type { ProtocolCopy, ProtocolView } from "@/api/client";
import type { ProtocolFormActionState } from "@/protocol/actions";
import messages from "../../messages/id.json";
import {
  type ApprovalControls,
  AssembledProtocolView,
  type ProtocolControls,
  type ProtocolError,
} from "./AssembledProtocolView";
import type { DecisionView } from "./Decisions";
import { RUN_ID } from "./decisions.fixture";
import { finding, fromDraft, fromDraftReady, fromDraftRows, submittedFromDraft } from "./draftProtocol.fixture";
import { protocolView, rows } from "./protocol.fixture";
import { proposal } from "./protocolDraft.fixture";
import { decision } from "./decisions.fixture";
import { RunShellProvider } from "./RunShellContext";

const action = async () => {};
type Inline = (p: ProtocolFormActionState, f: FormData) => Promise<ProtocolFormActionState>;
const ok: Inline = async () => ({ ok: true, submittedAt: 1 });
const controls: ProtocolControls = {
  start: action,
  withdraw: action,
  write: action,
  remove: action,
  edit: action,
  answer: action,
  submit: action,
  mapInline: ok,
  giveReasonInline: ok,
};
const decider: DecisionView = { access: { mode: "decide", action } };
const reader: DecisionView = { access: { mode: "readOnly", why: "noRole" } };
const approvalControls: ApprovalControls = { approve: action, return: action };
const SIGNING_AUTH = {
  oidcMode: false,
  reauthAuthTime: null,
  signer: { name: "Dewi Lestari", username: "dewi" },
};

function page(
  protocol: ProtocolView | null,
  opts: {
    decisions?: DecisionView;
    error?: ProtocolError;
    approver?: boolean;
    hasDraft?: boolean;
    controls?: ProtocolControls;
  } = {},
) {
  const decisions = opts.decisions ?? reader;
  return (
    <NextIntlClientProvider locale="id" messages={messages} timeZone="UTC">
      <RunShellProvider>
        <AssembledProtocolView
          protocol={protocol}
          runId={RUN_ID}
          decisions={decisions}
          controls={decisions.access.mode === "decide" ? (opts.controls ?? controls) : null}
          approval={opts.approver ? approvalControls : null}
          signingAuth={SIGNING_AUTH}
          error={opts.error}
          hasDraft={opts.hasDraft}
        />
      </RunShellProvider>
    </NextIntlClientProvider>
  );
}

const user = () => userEvent.setup();

async function openRow(u: ReturnType<typeof user>, requirement: string) {
  await u.click(within(screen.getByTestId(requirement)).getByRole("button", { name: requirement }));
  return within(await screen.findByRole("dialog"));
}

test("a run that read a draft offers to start the Protocol from it, posting from_draft", () => {
  const { container } = render(page(null, { decisions: decider, hasDraft: true }));
  const button = screen.getByRole("button", { name: "Mulai protokol dari draf yang ditinjau" });
  const form = button.closest("form") as HTMLFormElement;
  expect((form.elements.namedItem("from_draft") as HTMLInputElement).value).toBe("true");
  expect(screen.getByRole("button", { name: "Mulai protokol dari run ini" })).toBeDefined();
  expect(container.textContent).toContain("terpaku pada revisi draf");
});

test("a run that read no draft offers only the old start", () => {
  render(page(null, { decisions: decider, hasDraft: false }));
  expect(screen.queryByRole("button", { name: "Mulai protokol dari draf yang ditinjau" })).toBeNull();
});

test("the source shows the pinned revision and hash, the latest revision, and the warning that it does not follow", () => {
  render(page(fromDraft));
  const source = within(screen.getByRole("region", { name: "Sumber: draf protokol" }));
  expect(source.getByTestId("draft-source-line").textContent).toBe(
    `OQ-TP201 rev 0, hash ${"ab".repeat(32)}`,
  );
  expect(source.getByText(/Revisi terbaru draf saat halaman ini dibaca: 1/)).toBeDefined();
  expect(source.getByTestId("draft-behind").textContent).toContain("terpaku pada rev 0");
  expect(source.getByText("Hanya pengembangan (dev only)")).toBeDefined();
  expect(source.getByText("Menunggu jawaban praktisi (#245)")).toBeDefined();
});

test("no warning when the Protocol is pinned to the latest revision", () => {
  render(page({ ...fromDraft, latest_draft_rev: 0 }));
  const source = within(screen.getByRole("region", { name: "Sumber: draf protokol" }));
  expect(source.queryByTestId("draft-behind")).toBeNull();
});

test("a Protocol assembled the old way shows no draft source and no draft labels", () => {
  render(page(protocolView()));
  expect(screen.queryByRole("region", { name: "Sumber: draf protokol" })).toBeNull();
  expect(screen.queryByTestId("draft-labels")).toBeNull();
  expect(screen.queryByRole("tab", { name: /Langkah draf/ })).toBeNull();
});

test("the checklist lists the four checks the draft adds", () => {
  render(page(fromDraft, { decisions: decider }));
  const list = within(screen.getByRole("region", { name: /Yang memblokir pengajuan/ }));
  expect(list.getByTestId("check-finding_undecided").textContent).toContain(
    "Temuan draf belum diputuskan: 1",
  );
  expect(list.getByTestId("check-finding_reason_missing").textContent).toContain("tanpa alasan tertulis: 0");
  expect(list.getByTestId("check-stage_missing").textContent).toContain("tanpa tahap IQ atau OQ: 1");
  expect(list.getByTestId("check-draft_step_unresolved").textContent).toContain(
    "Langkah draf tanpa persyaratan (petakan atau tolak): 1",
  );
});

test("the table marks a draft row with its source, its finding count and its labels", () => {
  render(page(fromDraft));
  const r = within(screen.getByTestId("URS-TP201-002"));
  expect(r.getByText(/Sumber: Draf/)).toBeDefined();
  expect(r.getByText("2 temuan")).toBeDefined();
  expect(r.getByText("Belum ditinjau praktisi")).toBeDefined();
  expect(r.getByText("Hanya pengembangan (dev only)")).toBeDefined();
  expect(r.getByText(/Memblokir: ada temuan draf/)).toBeDefined();
  expect(r.getByText(/Memblokir: tetapkan tahap IQ atau OQ/)).toBeDefined();
});

test("a draft step no requirement owns is listed, unusable, and mapped to one requirement", async () => {
  const u = user();
  const mapInline = vi.fn<Inline>(async () => ({ ok: true, submittedAt: 1 }));
  render(page(fromDraft, { decisions: decider, controls: { ...controls, mapInline } }));
  const tab = screen.getByRole("tab", { name: /Langkah draf/ });
  expect(tab.textContent).toContain("1");
  await u.click(tab);
  const step = within(await screen.findByTestId("draft-step-OQ-40"));
  expect(step.getByText("Belum dapat dipakai")).toBeDefined();
  expect(step.getByText("Periksa fungsi interlock pintu")).toBeDefined();
  await u.selectOptions(step.getByRole("combobox", { name: "Petakan ke persyaratan" }), "URS-TP201-030");
  await u.click(step.getByRole("button", { name: "Simpan pemetaan" }));
  await waitFor(() => expect(mapInline).toHaveBeenCalledTimes(1));
  const form = mapInline.mock.calls[0]?.[1] as FormData;
  expect(form.get("protocol_id")).toBe("7");
  expect(form.get("step")).toBe("OQ-40");
  expect(form.get("requirement")).toBe("URS-TP201-030");
  // a step that stands for a requirement is shown as such, with no form
  expect(within(screen.getByTestId("draft-step-OQ-02")).getByText("Mewakili URS-TP201-002")).toBeDefined();
  expect(within(screen.getByTestId("draft-step-OQ-02")).queryByRole("combobox")).toBeNull();
});

test("the row drawer shows the candidate Test Step, the finding types, and the label only where the API carries it", async () => {
  const u = user();
  render(page(fromDraft, { decisions: decider }));
  const drawer = await openRow(u, "URS-TP201-002");
  const candidate = within(drawer.getByTestId("candidate-OQ-02"));
  expect(candidate.getByText("Atur turret ke 20 dan 70 rpm", { selector: "div" })).toBeDefined();
  expect(candidate.getByText(/Kriteria penerimaan:.*20.*70 rpm/, { selector: "span" })).toBeDefined();
  expect(candidate.getByText("Keputusan atas langkah")).toBeDefined();
  // the criterion is decided once the step is accepted, not before
  expect(candidate.queryByText("Keputusan atas kriteria penerimaan")).toBeNull();

  const plain = within(drawer.getByTestId("finding-301"));
  expect(plain.getByText("Kriteria penerimaan lebih longgar dari URS")).toBeDefined();
  expect(plain.queryByText("Belum ditinjau praktisi")).toBeNull();
  const labelled = within(drawer.getByTestId("finding-302"));
  expect(labelled.getByText("Kriteria penerimaan di luar kemampuan yang tercantum di datasheet")).toBeDefined();
  expect(labelled.getByText("Belum ditinjau praktisi")).toBeDefined();
  expect(labelled.getByText("Hanya pengembangan (dev only)")).toBeDefined();
});

test("the criterion is decided after its step is accepted", async () => {
  const u = user();
  const accepted = fromDraftRows.map((r) =>
    r.requirement === "URS-TP201-002"
      ? {
          ...r,
          candidates: r.candidates.map((c) => ({
            ...c,
            proposal: proposal({
              id: 201,
              kind: "draft_step" as const,
              state: "decided" as const,
              decisions: [decision({ id: 5, decision: "accepted" })],
            }),
          })),
        }
      : r,
  );
  render(page({ ...fromDraft, rows: accepted }, { decisions: decider }));
  const drawer = await openRow(u, "URS-TP201-002");
  expect(drawer.getByText("Keputusan atas kriteria penerimaan")).toBeDefined();
});

test("an accepted finding on an unchanged row asks for a written reason; a changed row does not", async () => {
  const u = user();
  const giveReasonInline = vi.fn<Inline>(async () => ({ ok: true, submittedAt: 1 }));
  const withAccepted = (changed: boolean) =>
    fromDraftRows.map((r) =>
      r.requirement === "URS-TP201-002"
        ? {
            ...r,
            changed,
            findings: [
              finding(301, {
                proposal: proposal({
                  id: 301,
                  kind: "draft",
                  state: "decided",
                  decisions: [decision({ id: 6, decision: "accepted" })],
                }),
              }),
            ],
          }
        : r,
    );
  const { unmount } = render(
    page({ ...fromDraft, rows: withAccepted(false) }, { decisions: decider, controls: { ...controls, giveReasonInline } }),
  );
  let drawer = await openRow(u, "URS-TP201-002");
  await u.type(drawer.getByRole("textbox", { name: "Alasan" }), "Batas disetujui pemasok");
  await u.click(drawer.getByRole("button", { name: "Simpan alasan" }));
  await waitFor(() => expect(giveReasonInline).toHaveBeenCalledTimes(1));
  const form = giveReasonInline.mock.calls[0]?.[1] as FormData;
  expect(form.get("proposal_id")).toBe("301");
  expect(form.get("reason")).toBe("Batas disetujui pemasok");
  unmount();

  render(page({ ...fromDraft, rows: withAccepted(true) }, { decisions: decider }));
  drawer = await openRow(u, "URS-TP201-002");
  expect(drawer.queryByRole("textbox", { name: "Alasan" })).toBeNull();
});

test("a reader sees the candidates and findings but no form", async () => {
  const u = user();
  render(page(fromDraft, { decisions: reader }));
  const drawer = await openRow(u, "URS-TP201-002");
  expect(drawer.getByTestId("candidate-OQ-02")).toBeDefined();
  expect(drawer.queryByRole("button", { name: "Simpan alasan" })).toBeNull();
  expect(drawer.queryByRole("button", { name: "Terima" })).toBeNull();
});

test("the submit dialog names the latest draft revision the Preparer read", async () => {
  const u = user();
  render(page(fromDraftReady, { decisions: decider }));
  await u.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Ajukan protokol untuk persetujuan?" }));
  const form = dialog.getByRole("button", { name: "Ajukan protokol" }).closest("form") as HTMLFormElement;
  expect((form.elements.namedItem("expected_latest_draft_rev") as HTMLInputElement).value).toBe("1");
  expect((form.elements.namedItem("expected_draft_hash") as HTMLInputElement).value).toBe("c".repeat(64));
});

test("a Protocol not started from the draft sends no draft revision", async () => {
  const u = user();
  render(page(protocolView({ checklist: fromDraftReady.checklist, draft_hash: "c".repeat(64), rows }), { decisions: decider }));
  await u.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  const dialog = within(await screen.findByRole("dialog"));
  const form = dialog.getByRole("button", { name: "Ajukan protokol" }).closest("form") as HTMLFormElement;
  expect(form.elements.namedItem("expected_latest_draft_rev")).toBeNull();
});

test("the approve dialog names the latest draft revision the Approver read", async () => {
  const u = user();
  render(page(submittedFromDraft, { approver: true }));
  await u.click(screen.getByRole("button", { name: "Setujui protokol" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Setujui protokol" }));
  const form = dialog.getByRole("button", { name: "Setujui protokol" }).closest("form") as HTMLFormElement;
  expect((form.elements.namedItem("expected_latest_draft_rev") as HTMLInputElement).value).toBe("0");
  expect((form.elements.namedItem("hash") as HTMLInputElement).value).toBe("d".repeat(64));
});

test("a stale draft closes the submit dialog and says to reload, naming no other cause", async () => {
  const u = user();
  const { rerender } = render(page(fromDraftReady, { decisions: decider }));
  await u.click(screen.getByRole("button", { name: "Ajukan protokol" }));
  await screen.findByRole("dialog");
  rerender(page(fromDraftReady, { decisions: decider, error: "stale_draft" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("revisi draf yang lebih baru masuk");
  expect(alert.textContent).toContain("Muat ulang halaman");
  await waitFor(() => expect(document.activeElement).toBe(alert));
});

test("a Protocol pinned to an older revision says so in plain words, not as a generic conflict", async () => {
  const u = user();
  const { rerender } = render(page(submittedFromDraft, { approver: true }));
  await u.click(screen.getByRole("button", { name: "Setujui protokol" }));
  await screen.findByRole("dialog");
  rerender(page(submittedFromDraft, { approver: true, error: "pinned_behind" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  const alert = screen.getByRole("alert");
  expect(alert.textContent).toContain("terpaku pada revisi draf yang lebih lama");
  expect(alert.textContent).toContain("mulai protokol baru dari revisi terbaru");
  expect(alert.textContent).not.toContain("Ditolak API");
});

test("the version 2 frozen copy shows its source, mapped steps, findings with decisions and reasons, and the labels", () => {
  render(page(submittedFromDraft));
  const copy = within(screen.getByTestId("copy-draft"));
  expect(copy.getByText(`Draf: OQ-TP201 rev 0, hash ${"ab".repeat(32)}, run ${RUN_ID}`)).toBeDefined();
  expect(copy.getByText("OQ-40: URS-TP201-030")).toBeDefined();
  expect(copy.getByText(/Dipetakan ke URS-TP201-030 oleh Ayu Kartika Sari/)).toBeDefined();
  expect(copy.getByTestId("copy-row-URS-TP201-002").textContent).toBe(
    "URS-TP201-002 Sumber baris: Draf; tanpa tahap",
  );

  const decided = within(copy.getByTestId("copy-finding-301"));
  expect(decided.getByText(/Diterima oleh Bima Arya Nugraha/)).toBeDefined();
  expect(decided.getByText(/Batas 70 rpm disetujui pemasok/)).toBeDefined();
  expect(decided.queryByText("Belum ditinjau praktisi")).toBeNull();

  const open = within(copy.getByTestId("copy-finding-302"));
  expect(open.getByText("Belum ditinjau praktisi")).toBeDefined();
  expect(open.getByText("Tidak diputuskan")).toBeDefined();
  expect(copy.getByText("Hanya pengembangan (dev only)")).toBeDefined();
  expect(copy.getByText("Menunggu jawaban praktisi (#245)")).toBeDefined();
  expect(screen.getByTestId("copy-hash").textContent).toBe("d".repeat(64));
});

test("a version 1 frozen copy shows no draft section", () => {
  render(page(protocolView({ status: "submitted", rows: null, urs: null, checklist: null, submission: { ...submittedFromDraft.submission!, frozen_copy: fromDraftV1() } })));
  expect(screen.queryByTestId("copy-draft")).toBeNull();
});

function fromDraftV1(): ProtocolCopy {
  const { protocol_id, equipment, run_id, preparer, rows: copyRows, urs } = submittedFromDraft.submission!
    .frozen_copy;
  return { protocol_id, equipment, run_id, preparer, rows: copyRows, urs };
}

test("the flow from the draft to a signed copy, page by page", async () => {
  const u = user();
  // 1. start from the draft
  const { rerender } = render(page(null, { decisions: decider, hasDraft: true }));
  expect(screen.getByRole("button", { name: "Mulai protokol dari draf yang ditinjau" })).toBeDefined();
  // 2. in Draft: pinned, behind, blocked, submit disabled
  rerender(page(fromDraft, { decisions: decider }));
  expect(screen.getByTestId("draft-behind").textContent).toContain("terpaku pada rev 0");
  expect((screen.getByRole("button", { name: "Ajukan protokol" }) as HTMLButtonElement).disabled).toBe(true);
  await u.click(screen.getByRole("tab", { name: /Langkah draf/ }));
  expect(await screen.findByTestId("draft-step-OQ-40")).toBeDefined();
  // 3. nothing blocks: submit names the draft revision
  rerender(page(fromDraftReady, { decisions: decider }));
  expect((screen.getByRole("button", { name: "Ajukan protokol" }) as HTMLButtonElement).disabled).toBe(false);
  // 4. Submitted: the approver reads the v2 copy and signs naming the revision
  rerender(page(submittedFromDraft, { approver: true }));
  expect(screen.getByTestId("copy-draft")).toBeDefined();
  expect(screen.getByRole("button", { name: "Setujui protokol" })).toBeDefined();
});

test("the edit form of a draft step starts from the drafted criterion, so an edit does not drop it", async () => {
  const u = user();
  render(page(fromDraft, { decisions: decider, controls }));
  const drawer = await openRow(u, "URS-TP201-002");
  const form = within(drawer.getByTestId("candidate-OQ-02")).getByRole("form", {
    name: "Sunting rancangan",
  });
  expect(form.querySelector<HTMLSelectElement>("[name=ac_type]")?.value).toBe("range");
  expect(form.querySelector<HTMLInputElement>("[name=ac_min]")?.value).toBe("20");
  expect(form.querySelector<HTMLInputElement>("[name=ac_max]")?.value).toBe("70");
});

test("an unchanged edit of an inclusive range submits the same range it was given", async () => {
  const u = user();
  const editInline = vi.fn<Inline>(async () => ({ ok: true, submittedAt: 1 }));
  render(page(fromDraft, { decisions: decider, controls: { ...controls, editInline } }));
  const drawer = await openRow(u, "URS-TP201-002");
  const form = within(drawer.getByTestId("candidate-OQ-02")).getByRole("form", {
    name: "Sunting rancangan",
  });
  await u.type(within(form).getByLabelText(/Alasan perubahan/), "koreksi");
  await u.click(within(form).getByRole("button", { name: "Simpan suntingan" }));
  await waitFor(() => expect(editInline).toHaveBeenCalledTimes(1));
  const sent = editInline.mock.calls[0]?.[1] as FormData;
  expect(sent.get("ac_type")).toBe("range");
  expect(sent.get("ac_min")).toBe("20");
  expect(sent.get("ac_max")).toBe("70");
  expect(sent.get("ac_unit")).toBe("rpm");
});

test("a strict range is not prefilled, so it cannot be saved as an inclusive one", async () => {
  const u = user();
  const strict = fromDraftRows.map((r) =>
    r.requirement === "URS-TP201-002"
      ? {
          ...r,
          candidates: r.candidates.map((c) => ({
            ...c,
            criterion: c.criterion
              ? {
                  ...c.criterion,
                  value: { type: "range" as const, min: 20, max: 70, unit: "rpm", min_exclusive: false, max_exclusive: true },
                }
              : c.criterion,
          })),
        }
      : r,
  );
  render(page({ ...fromDraft, rows: strict }, { decisions: decider, controls }));
  const drawer = await openRow(u, "URS-TP201-002");
  const form = within(drawer.getByTestId("candidate-OQ-02")).getByRole("form", {
    name: "Sunting rancangan",
  });
  expect(form.querySelector<HTMLSelectElement>("[name=ac_type]")?.value).toBe("");
  expect(form.querySelector("[name=ac_max]")).toBeNull();
});

test("a map refusal says why in words of its own", async () => {
  const u = user();
  const mapInline = vi.fn<Inline>(async () => ({ ok: false, error: "refused" }));
  render(page(fromDraft, { decisions: decider, controls: { ...controls, mapInline } }));
  await u.click(screen.getByRole("tab", { name: /Langkah draf/ }));
  const step = within(await screen.findByTestId("draft-step-OQ-40"));
  await u.selectOptions(step.getByRole("combobox", { name: "Petakan ke persyaratan" }), "URS-TP201-030");
  await u.click(step.getByRole("button", { name: "Simpan pemetaan" }));
  expect((await step.findByRole("alert")).textContent).toMatch(/tepat satu persyaratan/);
});

test("after a mapping is saved, focus moves to the step, not to the document", async () => {
  const u = user();
  const mapInline = vi.fn<Inline>(async () => ({ ok: true, submittedAt: 1 }));
  render(page(fromDraft, { decisions: decider, controls: { ...controls, mapInline } }));
  await u.click(screen.getByRole("tab", { name: /Langkah draf/ }));
  const step = within(await screen.findByTestId("draft-step-OQ-40"));
  await u.selectOptions(step.getByRole("combobox", { name: "Petakan ke persyaratan" }), "URS-TP201-030");
  await u.click(step.getByRole("button", { name: "Simpan pemetaan" }));
  await waitFor(() => expect(document.activeElement?.id).toBe("draft-step-OQ-40"));
});
