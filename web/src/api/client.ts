import createClient from "openapi-fetch";

import type { components as evalComponents, paths as evalPaths } from "./eval-schema";
import type { components, paths } from "./schema";
import { API_URL, EVAL_URL } from "./url";

export type Matrix = components["schemas"]["Matrix"];
export type MatrixRow = components["schemas"]["MatrixRow"];
export type Cite = components["schemas"]["Cite"];
export type RunSummary = components["schemas"]["RunSummary"];
export type DroppedClaim = components["schemas"]["DroppedClaim"];
export type Completeness = components["schemas"]["Completeness"];
export type Findings = components["schemas"]["Findings"];
export type Proposal = components["schemas"]["Proposal"];
export type Decision = components["schemas"]["Decision"];
export type DecisionCounts = components["schemas"]["DecisionCounts"];
export type KindCounts = components["schemas"]["KindCounts"];
export type CoverageClass = NonNullable<MatrixRow["coverage"]>;
export type Value = NonNullable<MatrixRow["value"]>;
export type ProtocolDraftView = components["schemas"]["ProtocolDraftView"];
export type DraftTestStep = components["schemas"]["DraftTestStep"];
export type DraftFindingView = components["schemas"]["DraftFindingView"];
export type PrintedRead = NonNullable<components["schemas"]["DraftAcceptance"]["value"]>;
export type ProtocolView = components["schemas"]["ProtocolView"];
export type ProtocolRowView = components["schemas"]["ProtocolRowView"];
export type ProtocolEvent = components["schemas"]["ProtocolEvent"];
export type RowDraft = components["schemas"]["RowDraft"];
export type ProtocolUrs = components["schemas"]["ProtocolUrs"];
export type MissedNumberView = components["schemas"]["MissedNumberView"];
export type ChecklistItem = components["schemas"]["ChecklistItem"];
export type SubmissionView = components["schemas"]["SubmissionView"];
export type FrozenRow = components["schemas"]["FrozenRow"];
export type FrozenDecision = components["schemas"]["FrozenDecision"];
export type ExecutionView = components["schemas"]["ExecutionView"];
export type ExecutionRowView = components["schemas"]["ExecutionRowView"];
export type ExecutionEvent = components["schemas"]["ExecutionEvent"];
export type ExecutionTestStep = components["schemas"]["ExecutionTestStep"];
export type AttemptView = components["schemas"]["AttemptView"];
export type AttemptVersionView = components["schemas"]["AttemptVersionView"];
export type WitnessConfirmationView = components["schemas"]["WitnessConfirmationView"];
export type DeviationView = components["schemas"]["DeviationView"];
export type DeviationEventView = components["schemas"]["DeviationEventView"];
export type DeviationInvestigationView = components["schemas"]["DeviationInvestigationView"];
export type CompletionBlockers = components["schemas"]["CompletionBlockers"];
export type ExecutionCopy = components["schemas"]["ExecutionCopy"];
export type InstrumentInput = components["schemas"]["InstrumentInput"];
export type ObservedValue = NonNullable<components["schemas"]["EvidenceStep"]["observed_value"]>;
export type RunRoundsView = components["schemas"]["RunRoundsView"];
export type ReviewRoundView = components["schemas"]["ReviewRoundView"];
export type RoundDiffView = components["schemas"]["RoundDiffView"];
export type DocumentVersionView = components["schemas"]["DocumentVersionView"];
export type ReviewRoundEventView = components["schemas"]["ReviewRoundEventView"];
export type ReportExportView = components["schemas"]["ReportExportView"];
export type RoundStatus = components["schemas"]["RoundStatus"];
export type RoundEventKind = components["schemas"]["RoundEventKind"];
export type CloseOutcome = components["schemas"]["CloseOutcome"];
export type Stage = components["schemas"]["Stage"];
export type StepAttributesUpdate = components["schemas"]["StepAttributesUpdate"];
export type TechnicalConclusion = components["schemas"]["TechnicalConclusion"];
export type QualificationCounts = components["schemas"]["QualificationCounts"];
export type QualificationExportView = components["schemas"]["QualificationExportView"];
export type QualificationReportView = components["schemas"]["QualificationReportView"];
export type ApproveQualificationReportRequest =
  components["schemas"]["ApproveQualificationReportRequest"];
export type EquipmentSummary = components["schemas"]["EquipmentSummary"];
export type LatestRoundSummary = components["schemas"]["LatestRoundSummary"];
export type LatestProtocolSummary = components["schemas"]["LatestProtocolSummary"];
export type LatestExecutionSummary = components["schemas"]["LatestExecutionSummary"];
export type LatestQualificationReportSummary =
  components["schemas"]["LatestQualificationReportSummary"];
export type ElectronicSignatureView = components["schemas"]["ElectronicSignatureView"];
export type SignatureMeaning = components["schemas"]["SignatureMeaning"];

/** The typed client over the generated OpenAPI schema (ADR 0003). */
export const api = createClient<paths>({ baseUrl: API_URL, cache: "no-store" });

export type EvalSummary = evalComponents["schemas"]["EvalSummary"];
export type Rate = evalComponents["schemas"]["Rate"];

/** The harness's eval API: aggregates (k/n, split, cost) of scored runs, never items. */
export const evalApi = createClient<evalPaths>({ baseUrl: EVAL_URL, cache: "no-store" });

/** Where a citation opens: the document as the run read it, at the cited page. */
export function documentHref(runId: string, c: Cite): string {
  const doc = encodeURIComponent(c.doc);
  return `/api/runs/${encodeURIComponent(runId)}/documents/${doc}/${c.rev}#page=${c.page}`;
}
