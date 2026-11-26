"use client";

import { useState } from "react";

import type { ProtocolError } from "./AssembledProtocolView";

/** Open state of a Protocol signature dialog (submit, approve) that reacts to a refused signing.
 *
 * A refusal returns as the page's `protocolError`. When the Protocol status does not change
 * (e.g. a stale-draft `conflict`) the dialog would otherwise stay open under the overlay and
 * invite a blind retry with a fresh signature. So any error other than `reauth_required` closes
 * the dialog the moment it first appears, leaving the page alert (focused by the view) in sight.
 * `reauth_required` keeps the dialog open: it leads to the re-authentication prompt. While an
 * error is still on the page, callers also pass it to the dialog, so a reopened or repeat-failing
 * dialog shows it inside itself. */
export function useSigningDialog(error: ProtocolError | undefined, initialOpen: boolean) {
  const [open, setOpen] = useState(initialOpen);
  const [seenError, setSeenError] = useState(error);
  if (error !== seenError) {
    setSeenError(error);
    if (error !== undefined && error !== "reauth_required") setOpen(false);
  }
  return { open, setOpen };
}
