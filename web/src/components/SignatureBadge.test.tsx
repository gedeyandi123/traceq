import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import type { ElectronicSignatureView } from "@/api/client";
import messages from "../../messages/id.json";
import { SignatureBadge } from "./SignatureBadge";

function wrap(ui: React.ReactNode) {
  return (
    <NextIntlClientProvider locale="id" messages={messages}>
      {ui}
    </NextIntlClientProvider>
  );
}

const DEMO_SIG: ElectronicSignatureView = {
  id: 1,
  at: "2026-11-26T04:00:00Z",
  record_type: "protocol_approval",
  signature_meaning: "approved",
  content_hash: "a".repeat(64),
  hash_scheme_version: 1,
  signer_subject: "demo-0002",
  signer_issuer: "http://127.0.0.1:9000",
  signer_name: "Dewi Lestari",
  auth_time: "2026-11-26T04:00:00Z",
  is_demo: true,
  label: "Demo signature — demo identity without password re-authentication, not an Electronic Signature",
  verified: true,
};

const OIDC_SIG: ElectronicSignatureView = {
  ...DEMO_SIG,
  id: 2,
  signer_subject: "kc-dewi-sub",
  signer_issuer: "http://127.0.0.1:8080/realms/traceq",
  is_demo: false,
  label:
    "Electronic Signature — designed for 21 CFR Part 11, CPOB Annex 7, and draft EU GMP Annex 11 (2025), not validated (ADR 0007)",
  verified: true,
};

describe("SignatureBadge", () => {
  it("renders honest recorded-status fallback when signature is null (pre-Step-8)", () => {
    render(wrap(<SignatureBadge signature={null} />));
    expect(screen.getByText("Status Tercatat")).toBeTruthy();
    expect(screen.getByText(/bukan Tanda Tangan Elektronik/i)).toBeTruthy();
  });

  it("renders demo signature with signer name, meaning, short hash with copy, verified, and honest demo label", () => {
    render(wrap(<SignatureBadge signature={DEMO_SIG} />));
    expect(screen.getByText("Dewi Lestari")).toBeTruthy();
    expect(screen.getByText(/Disetujui \(approved\)/i)).toBeTruthy();
    expect(screen.getByText(/Hash cocok/i)).toBeTruthy();
    expect(screen.getByText(/Demo signature/i)).toBeTruthy();
    const hashEl = screen.getByTitle("a".repeat(64));
    expect(hashEl.textContent).toBe("aaaaaaaaaaaa…");
    expect(screen.getByRole("button", { name: /Salin hash/i })).toBeTruthy();
  });

  it("renders OIDC Electronic Signature with ADR 0007 label and voided badge when voided", () => {
    render(
      wrap(
        <SignatureBadge
          signature={{ ...OIDC_SIG, signature_meaning: "witnessed" }}
          voided
        />,
      ),
    );
    expect(screen.getByText("Tanda Tangan Elektronik")).toBeTruthy();
    expect(screen.getByText(/Disaksikan \(witnessed\)/i)).toBeTruthy();
    expect(screen.getByText("Dibatalkan")).toBeTruthy();
    expect(
      screen.getByText(/designed for 21 CFR Part 11, CPOB Annex 7/i),
    ).toBeTruthy();
  });

  it("renders a signature that was not checked as 'not checked', never as verified", () => {
    render(wrap(<SignatureBadge signature={{ ...DEMO_SIG, verified: null }} />));
    expect(screen.getByText("Belum Diperiksa")).toBeTruthy();
    expect(screen.queryByText("Hash cocok")).toBeNull();
    expect(screen.queryByText(/Verifikasi Gagal/i)).toBeNull();
  });

  it("renders a signature whose hash does not match as a failed verification", () => {
    render(wrap(<SignatureBadge signature={{ ...DEMO_SIG, verified: false }} />));
    expect(screen.getByText(/Verifikasi Gagal/i)).toBeTruthy();
    expect(screen.queryByText("Hash cocok")).toBeNull();
  });

  it("shows the check beside 'Hash cocok' in a neutral tone, not green", () => {
    render(wrap(<SignatureBadge signature={DEMO_SIG} />));
    const check = screen.getByTestId("signature-verified-check");
    expect(check.getAttribute("class") ?? "").not.toContain("text-pass");
    const label = screen.getByText(/Hash cocok/i).parentElement;
    expect(label?.className ?? "").not.toContain("text-pass");
  });

  it("does not show the green check for a voided signature", () => {
    render(wrap(<SignatureBadge signature={OIDC_SIG} voided />));
    expect(screen.getByText("Dibatalkan")).toBeTruthy();
    expect(screen.queryByTestId("signature-verified-check")).toBeNull();
  });

  it("shows the green check for a verified, not voided signature", () => {
    render(wrap(<SignatureBadge signature={OIDC_SIG} />));
    expect(screen.getByTestId("signature-verified-check")).toBeTruthy();
  });
});
