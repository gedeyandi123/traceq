"use client";

import {
  CheckCircle2,
  Download,
  ExternalLink,
  FilePlus2,
  FileText,
  GitCompareArrows,
  Lock,
  MinusCircle,
  RefreshCw,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useActionState, useState } from "react";

import type {
  CloseOutcome,
  DocumentVersionView,
  ReviewRoundView,
  RoundDiffView,
  RunRoundsView,
} from "@/api/client";
import type { Session } from "@/auth/session";
import { Alert } from "@/components/ui/Alert";
import { CopyHashButton } from "@/components/ui/CopyHashButton";
import { DirtyGuardBanner } from "@/components/ui/DirtyGuardBanner";
import { FieldTextarea } from "@/components/ui/FormControls";
import { Modal } from "@/components/ui/Modal";
import { RoundStatusBadge } from "@/components/ui/StatusBadge";
import { SubmitButton } from "@/components/ui/SubmitButton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Button, cell, DataTable, EmptyState, SectionHeading } from "@/components/ui/ui";
import type {
  CloseRoundActionState,
  ExportReportActionState,
  RoundsError,
} from "@/rounds/actions";

export type CloseRoundAction = (
  prev: CloseRoundActionState,
  formData: FormData,
) => Promise<CloseRoundActionState>;

export type ExportReportAction = (
  prev: ExportReportActionState,
  formData: FormData,
) => Promise<ExportReportActionState>;

type DocRow = {
  doc: DocumentVersionView;
  isActive: boolean;
  diffKind: "added" | "revised" | "unchanged" | null;
};

function buildDocumentRows(
  rounds: ReviewRoundView[],
  currentRound: ReviewRoundView | undefined,
  diff: RoundDiffView | null,
): DocRow[] {
  const activeKeys = new Set(
    (currentRound?.documents ?? []).map((d) => `${d.doc_id}::${d.rev}`),
  );
  const seen = new Set<string>();
  const allDocs: DocumentVersionView[] = [];

  // Put current round documents first, then historical versions in reverse round order.
  const orderedRounds = [
    ...(currentRound ? [currentRound] : []),
    ...[...rounds].reverse().filter((r) => r.id !== currentRound?.id),
  ];

  for (const r of orderedRounds) {
    for (const d of r.documents) {
      const key = `${d.doc_id}::${d.rev}`;
      if (!seen.has(key)) {
        seen.add(key);
        allDocs.push(d);
      }
    }
  }

  const added = new Set(diff?.documents_added ?? []);
  const revised = new Set(diff?.documents_revised ?? []);
  const unchanged = new Set(diff?.documents_unchanged ?? []);

  return allDocs.map((doc) => {
    const isActive = activeKeys.has(`${doc.doc_id}::${doc.rev}`);
    let diffKind: DocRow["diffKind"] = null;
    if (isActive && diff) {
      if (added.has(doc.doc_id)) diffKind = "added";
      else if (revised.has(doc.doc_id)) diffKind = "revised";
      else if (unchanged.has(doc.doc_id)) diffKind = "unchanged";
    }
    return { doc, isActive, diffKind };
  });
}

function errorMessage(t: ReturnType<typeof useTranslations<"rounds">>, err?: RoundsError): string {
  if (!err) return "";
  return t(`errors.${err}`);
}

export function RoundsWorkbench({
  runId,
  data,
  session,
  closeRoundAction,
  exportReportAction,
}: {
  runId: string;
  data: RunRoundsView;
  session: Session | null;
  closeRoundAction: CloseRoundAction;
  exportReportAction: ExportReportAction;
}) {
  const t = useTranslations("rounds");
  const ui = useTranslations("ui");
const findingTypes = useTranslations("draft");

  const currentRound =
    data.rounds.find((r) => r.id === data.current_round_id) ?? data.rounds.at(-1);
  const canDecide = Boolean(session?.mayDecide);
  const canExport = Boolean(session?.mayDecide || session?.mayApprove);

  const docRows = buildDocumentRows(data.rounds, currentRound, data.diff);
  const allExports = [...data.rounds]
    .reverse()
    .flatMap((r) => r.exports.map((exp) => ({ roundNumber: r.round_number, exp })));

  const [closeModalOpen, setCloseModalOpen] = useState(false);
  const [outcome, setOutcome] = useState<CloseOutcome>("returned_for_revision");
  const [reason, setReason] = useState("");
  const [dirtyGuardOpen, setDirtyGuardOpen] = useState(false);

  const [closeState, closeFormAction] = useActionState(
    async (prev: CloseRoundActionState, fd: FormData) => {
      const next = await closeRoundAction(prev, fd);
      if (next.ok && next.submittedAt) {
        setCloseModalOpen(false);
        setDirtyGuardOpen(false);
        setOutcome("returned_for_revision");
        setReason("");
      } else if (!next.ok && next.error) {
        if (next.outcome) setOutcome(next.outcome);
        if (next.reason !== undefined) setReason(next.reason);
      }
      return next;
    },
    { ok: false },
  );
  const [exportState, exportFormAction] = useActionState(exportReportAction, { ok: false });

  const isDirty = outcome !== "returned_for_revision" || reason.trim() !== "";

  const handleCloseModalChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setDirtyGuardOpen(false);
      setCloseModalOpen(true);
      return;
    }
    if (isDirty) {
      setDirtyGuardOpen(true);
      return;
    }
    setDirtyGuardOpen(false);
    setCloseModalOpen(false);
  };

  const handleDiscardAndClose = () => {
    setDirtyGuardOpen(false);
    setOutcome("returned_for_revision");
    setReason("");
    setCloseModalOpen(false);
  };

  return (
    <div className="space-y-4">
      <Tabs defaultValue="documents" className="w-full">
        <TabsList aria-label={t("title")}>
          <TabsTrigger value="documents">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("tabs.documents")}</span>
            <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
              {docRows.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="rounds">
            <GitCompareArrows className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("tabs.rounds")}</span>
            <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
              {data.rounds.length}
            </span>
          </TabsTrigger>
          <TabsTrigger value="exports">
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{t("tabs.exports")}</span>
            <span className="rounded-full bg-sunken px-1.5 py-0.5 text-[11px] font-semibold text-ink-muted tabular-nums">
              {allExports.length}
            </span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-4">
          <SectionHeading
            id="doc-versions"
            title={t("documents.heading")}
            count={docRows.length}
            note={t("documents.note")}
          />

          {docRows.length === 0 ? (
            <EmptyState title={t("documents.empty")} />
          ) : (
            <DataTable>
              <thead>
                <tr>
                  <th scope="col">{t("documents.colDocId")}</th>
                  <th scope="col">{t("documents.colRev")}</th>
                  <th scope="col">{t("documents.colType")}</th>
                  <th scope="col">{t("documents.colSource")}</th>
                  <th scope="col">{t("documents.colSha256")}</th>
                  <th scope="col">{t("documents.colStatus")}</th>
                  <th scope="col">{t("documents.colDiff")}</th>
                  <th scope="col">{t("documents.colPreview")}</th>
                </tr>
              </thead>
              <tbody>
                {docRows.map(({ doc, isActive, diffKind }) => (
                  <tr key={`${doc.id}-${doc.doc_id}-${doc.rev}`}>
                    <td className={cell.id}>{doc.doc_id}</td>
                    <td className="tabular-nums whitespace-nowrap">{doc.rev}</td>
                    <td className="whitespace-nowrap text-xs text-ink-muted">
                      {doc.doc_type ?? t("documents.typeUnknown")}
                    </td>
                    <td className="whitespace-nowrap text-xs text-ink-muted">{doc.source}</td>
                    <td className="whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <code
                          title={doc.sha256}
                          className="rounded bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink tabular-nums"
                        >
                          {doc.sha256.slice(0, 12)}
                        </code>
                        <CopyHashButton
                          value={doc.sha256}
                          copyLabel={ui("copyHash")}
                          copiedLabel={ui("copied")}
                        />
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      {isActive ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-pass-edge bg-pass-soft px-2 py-0.5 text-[11px] font-semibold text-pass">
                          <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>{t("documents.statusActive")}</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-full border border-border-strong bg-sunken px-2 py-0.5 text-[11px] font-semibold text-ink-muted">
                          <MinusCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>{t("documents.statusSuperseded")}</span>
                        </span>
                      )}
                    </td>
                    <td className="whitespace-nowrap">
                      {diffKind === "added" && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-info-edge bg-info-soft px-2 py-0.5 text-[11px] font-semibold text-info">
                          <FilePlus2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>{t("documents.diffAdded")}</span>
                        </span>
                      )}
                      {diffKind === "revised" && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-warn-edge bg-warn-soft px-2 py-0.5 text-[11px] font-semibold text-warn">
                          <RefreshCw className="h-3 w-3 shrink-0" aria-hidden="true" />
                          <span>{t("documents.diffRevised")}</span>
                        </span>
                      )}
                      {diffKind === "unchanged" && (
                        <span className="text-xs text-ink-muted">{t("documents.diffUnchanged")}</span>
                      )}
                      {diffKind === null && <span className="text-xs text-ink-muted">—</span>}
                    </td>
                    <td className="whitespace-nowrap">
                      <a
                        href={`/api/runs/${encodeURIComponent(doc.first_seen_run_id)}/documents/${encodeURIComponent(doc.doc_id)}/${doc.rev}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-semibold text-accent no-underline hover:underline"
                      >
                        <span>{t("documents.previewLink")}</span>
                        <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}

          {data.diff && data.diff.documents_removed.length > 0 && (
            <div className="rounded-lg border border-warn-edge bg-warn-soft p-3 text-xs">
              <h3 className="m-0 font-semibold text-warn">{t("documents.removedHeading")}</h3>
              <p className="mt-1 mb-0 font-mono text-ink tabular-nums">
                {data.diff.documents_removed.join(", ")}
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="rounds" className="space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <SectionHeading
              id="review-rounds"
              title={t("reviewRounds.heading")}
              count={data.rounds.length}
              note={t("reviewRounds.note")}
            />

            {currentRound && currentRound.status === "open" && canDecide && (
              <Button
                type="button"
                variant="primary"
                onClick={() => handleCloseModalChange(true)}
              >
                <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{t("reviewRounds.closeButton")}</span>
              </Button>
            )}
          </div>

          {currentRound && currentRound.status === "open" && !canDecide && (
            <Alert tone="info">{t("reviewRounds.readOnlyNote")}</Alert>
          )}

          <div className="grid gap-3">
            {[...data.rounds].reverse().map((round) => (
              <section
                key={round.id}
                aria-labelledby={`round-heading-${round.id}`}
                className="rounded-lg border border-border bg-surface p-4 shadow-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3
                      id={`round-heading-${round.id}`}
                      className="m-0 text-sm font-bold text-ink tabular-nums"
                    >
                      {t("reviewRounds.roundLabel", { number: round.round_number })}
                    </h3>
                    <RoundStatusBadge status={round.status} />
                    <span className="text-xs text-ink-muted tabular-nums">
                      {t("reviewRounds.runIdLabel", { runId: round.run_id })}
                    </span>
                  </div>
                  <span className="text-xs text-ink-muted tabular-nums">
                    {t("reviewRounds.openedAt", { when: round.at })}
                  </span>
                </div>

                <div className="mt-3">
                  <h4 className="m-0 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                    {t("reviewRounds.eventsTitle")}
                  </h4>
                  <ul className="mt-2 mb-0 space-y-1.5 pl-4 text-xs text-ink">
                    {round.events.map((ev) => (
                      <li key={ev.id} className="leading-relaxed">
                        <span className="font-semibold">
                          {t(`reviewRounds.eventLabels.${ev.event}`)}
                        </span>{" "}
                        <span className="text-ink-muted tabular-nums">
                          ({t("reviewRounds.eventBy", { name: ev.name, when: ev.at })})
                        </span>
                        {ev.reason && (
                          <p className="mt-0.5 mb-0 rounded border border-border bg-canvas px-2.5 py-1 text-ink">
                            {ev.reason}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
            ))}
          </div>

          <section aria-labelledby="round-diff-heading" className="space-y-3">
            <h2 id="round-diff-heading" className="m-0 text-base font-semibold text-ink">
              {data.diff
                ? t("reviewRounds.diffHeading", {
                    prevNumber: data.diff.previous_round_number,
                  })
                : t("reviewRounds.diffHeading", { prevNumber: 0 })}
            </h2>

            {!data.diff ? (
              <EmptyState title={t("reviewRounds.diffSingleRound")} />
            ) : (
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
                  <h3 className="m-0 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                    {t("reviewRounds.diffDocsTitle")}
                  </h3>
                  <dl className="mt-2.5 mb-0 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDocsAdded")}</dt>
                      <dd className="m-0 font-semibold text-info tabular-nums">
                        {data.diff.documents_added.length}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDocsRevised")}</dt>
                      <dd className="m-0 font-semibold text-warn tabular-nums">
                        {data.diff.documents_revised.length}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDocsUnchanged")}</dt>
                      <dd className="m-0 font-semibold text-ink tabular-nums">
                        {data.diff.documents_unchanged.length}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDocsRemoved")}</dt>
                      <dd className="m-0 font-semibold text-fail tabular-nums">
                        {data.diff.documents_removed.length}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
                  <h3 className="m-0 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                    {t("reviewRounds.diffFindingsTitle")}
                  </h3>
                  <dl className="mt-2.5 mb-0 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffFindingsResolved")}</dt>
                      <dd className="m-0 font-semibold text-pass tabular-nums">
                        {data.diff.findings_resolved}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffFindingsPersisted")}</dt>
                      <dd className="m-0 font-semibold text-warn tabular-nums">
                        {data.diff.findings_persisted - data.diff.findings_persisted_changed}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">
                        {t("reviewRounds.diffFindingsPersistedChanged")}
                      </dt>
                      <dd className="m-0 font-semibold text-warn tabular-nums">
                        {data.diff.findings_persisted_changed}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffFindingsNew")}</dt>
                      <dd className="m-0 font-semibold text-fail tabular-nums">
                        {data.diff.findings_new}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div className="rounded-lg border border-border bg-surface p-3.5 shadow-xs">
                  <h3 className="m-0 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                    {t("reviewRounds.diffDecisionsTitle")}
                  </h3>
                  <dl className="mt-2.5 mb-0 space-y-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">
                        {t("reviewRounds.diffDecisionsCarriedForward")}
                      </dt>
                      <dd className="m-0 font-semibold text-pass tabular-nums">
                        {data.diff.decisions_carried_forward}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDecisionsChanged")}</dt>
                      <dd className="m-0 font-semibold text-warn tabular-nums">
                        {data.diff.decisions_changed}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-ink-muted">{t("reviewRounds.diffDecisionsUndecided")}</dt>
                      <dd className="m-0 font-semibold text-ink-muted tabular-nums">
                        {data.diff.decisions_undecided}
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            )}
            {data.diff && data.diff.findings.some((f) => f.change !== "persisted") && (
              <div className="mt-3 rounded-lg border border-border bg-surface p-3.5 shadow-xs">
                <h3 className="m-0 text-xs font-semibold tracking-wide text-ink-muted uppercase">
                  {t("reviewRounds.diffFindingsListTitle")}
                </h3>
                <p className="m-0 mt-1 text-[11px] text-ink-muted">{t("reviewRounds.devOnly")}</p>
                <ul className="mt-2.5 mb-0 list-none space-y-1.5 p-0 text-xs">
                  {data.diff.findings
                    .filter((f) => f.change !== "persisted")
                    .map((f) => (
                      <li key={`${f.proposal_id}-${f.change}`} className="flex gap-2">
                        <span className="w-32 shrink-0 font-semibold text-ink">
                          {t(`reviewRounds.diffFindingChange.${f.change}`)}
                        </span>
                        <span className="text-ink-muted">
                          {[
                            f.finding_type === null
                              ? null
                              : findingTypes.has(`types.${f.finding_type}`)
                                ? findingTypes(`types.${f.finding_type}`)
                                : f.finding_type,
                            f.test_step,
                            f.requirement,
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </section>
        </TabsContent>

        <TabsContent value="exports" className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <SectionHeading
              id="report-exports"
              title={t("exports.heading")}
              count={allExports.length}
              note={t("exports.note")}
            />

            {currentRound && canExport && (
              <form action={exportFormAction}>
                <input type="hidden" name="run_id" value={runId} />
                <input type="hidden" name="round_id" value={currentRound.id} />
                <SubmitButton variant="primary">
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{t("exports.issueButton")}</span>
                </SubmitButton>
              </form>
            )}
          </div>

          {!canExport && <Alert tone="info">{t("exports.roleNote")}</Alert>}

          {!exportState.ok && exportState.error && (
            <Alert tone="fail" role="alert">
              {errorMessage(t, exportState.error)}
            </Alert>
          )}
          {exportState.ok && exportState.submittedAt && (
            <Alert tone="pass" role="status">
              {t("exports.issuedSuccess")}
            </Alert>
          )}

          <h3 className="m-0 text-sm font-semibold text-ink">{t("exports.historyHeading")}</h3>

          {allExports.length === 0 ? (
            <EmptyState title={t("exports.empty")} />
          ) : (
            <DataTable>
              <thead>
                <tr>
                  <th scope="col">{t("exports.colRound")}</th>
                  <th scope="col">{t("exports.colIssuedAt")}</th>
                  <th scope="col">{t("exports.colIssuer")}</th>
                  <th scope="col">{t("exports.colSnapshotHash")}</th>
                  <th scope="col">{t("exports.colPdfSha256")}</th>
                  <th scope="col">{t("exports.colAction")}</th>
                </tr>
              </thead>
              <tbody>
                {allExports.map(({ roundNumber, exp }) => (
                  <tr key={exp.id}>
                    <td className={cell.id}>R{roundNumber}</td>
                    <td className="text-xs text-ink-muted tabular-nums whitespace-nowrap">
                      {exp.at}
                    </td>
                    <td className="text-xs text-ink whitespace-nowrap">{exp.name}</td>
                    <td className="whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <code
                          title={exp.snapshot_hash}
                          className="rounded bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink tabular-nums"
                        >
                          {exp.snapshot_hash.slice(0, 12)}
                        </code>
                        <CopyHashButton
                          value={exp.snapshot_hash}
                          copyLabel={ui("copyHash")}
                          copiedLabel={ui("copied")}
                        />
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        <code
                          title={exp.pdf_sha256}
                          className="rounded bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink tabular-nums"
                        >
                          {exp.pdf_sha256.slice(0, 12)}
                        </code>
                        <CopyHashButton
                          value={exp.pdf_sha256}
                          copyLabel={ui("copyHash")}
                          copiedLabel={ui("copied")}
                        />
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      <a
                        href={`/api/rounds/${exp.round_id}/exports/${exp.id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 rounded border border-accent/35 bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent no-underline transition-colors hover:bg-accent hover:text-on-accent"
                      >
                        <Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        <span>{t("exports.downloadButton")}</span>
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
          )}
        </TabsContent>
      </Tabs>

      {currentRound && (
        <Modal
          open={closeModalOpen}
          onOpenChange={handleCloseModalChange}
          title={t("closeModal.title", { number: currentRound.round_number })}
          description={t("closeModal.description")}
        >
          <form action={closeFormAction} className="space-y-4">
            <input type="hidden" name="run_id" value={runId} />
            <input type="hidden" name="round_id" value={currentRound.id} />

            {dirtyGuardOpen && (
              <DirtyGuardBanner
                message={t("closeModal.dirtyWarning")}
                discardLabel={t("closeModal.dirtyDiscard")}
                keepLabel={t("closeModal.dirtyKeep")}
                onDiscard={handleDiscardAndClose}
                onKeep={() => setDirtyGuardOpen(false)}
              />
            )}

            {!closeState.ok && closeState.error && (
              <Alert tone="fail" role="alert">
                {errorMessage(t, closeState.error)}
              </Alert>
            )}

            <fieldset className="space-y-2 border-0 p-0">
              <legend className="text-xs font-semibold text-ink">
                {t("closeModal.outcomeLabel")}
              </legend>
              <label className="flex cursor-pointer items-start gap-2 rounded-md border border-border bg-canvas p-2.5 text-xs">
                <input
                  type="radio"
                  name="outcome"
                  value="returned_for_revision"
                  checked={outcome === "returned_for_revision"}
                  onChange={() => setOutcome("returned_for_revision")}
                  className="mt-0.5"
                />
                <span className="font-medium text-ink">{t("closeModal.outcomeReturned")}</span>
              </label>
              <label className="flex cursor-pointer items-start gap-2 rounded-md border border-border bg-canvas p-2.5 text-xs">
                <input
                  type="radio"
                  name="outcome"
                  value="ready_for_protocol"
                  checked={outcome === "ready_for_protocol"}
                  onChange={() => setOutcome("ready_for_protocol")}
                  className="mt-0.5"
                />
                <span className="font-medium text-ink">{t("closeModal.outcomeReady")}</span>
              </label>
            </fieldset>

            <div className="space-y-1.5">
              <label htmlFor="close-round-reason" className="block text-xs font-semibold text-ink">
                {t("closeModal.reasonLabel")}
              </label>
              <p className="m-0 text-[11px] text-ink-muted">
                {outcome === "returned_for_revision"
                  ? t("closeModal.reasonRequiredHint")
                  : t("closeModal.reasonOptionalHint")}
              </p>
              <FieldTextarea
                id="close-round-reason"
                name="reason"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t("closeModal.reasonPlaceholder")}
                required={outcome === "returned_for_revision"}
                className="w-full"
              />
            </div>

            <Alert tone="info">{t("closeModal.adr0007Notice")}</Alert>

            <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
              <Button
                type="button"
                variant="quiet"
                onClick={() => handleCloseModalChange(false)}
              >
                {t("closeModal.cancelButton")}
              </Button>
              <SubmitButton variant="primary">{t("closeModal.confirmButton")}</SubmitButton>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
