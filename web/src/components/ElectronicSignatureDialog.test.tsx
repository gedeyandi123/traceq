import { act, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { vi } from "vitest";

import messages from "../../messages/id.json";
import { ElectronicSignatureDialog } from "./ElectronicSignatureDialog";

function wrap(ui: React.ReactNode) {
  return (
    <NextIntlClientProvider locale="id" messages={messages}>
      {ui}
    </NextIntlClientProvider>
  );
}

const SIGNER = { name: "Dewi Lestari", username: "dewi" };

describe("ElectronicSignatureDialog", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders target summary, content_hash preview, signature meaning, and honest demo label in demo mode", () => {
    const action = vi.fn();
    render(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Setujui Protokol"
          targetSummary="Protokol #7 · r7 TP/201"
          signatureMeaning="approved"
          contentHash={"f".repeat(64)}
          signingAuth={{ oidcMode: false, reauthAuthTime: null, signer: SIGNER }}
          signer={SIGNER}
          reauthNextUrl="/runs/r7/protocol?reauth_target=protocol_approval"
          action={action}
          confirmLabel="Setujui"
        />,
      ),
    );

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getAllByText("Protokol #7 · r7 TP/201").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Disetujui \(approved\)/i)).toBeTruthy();
    expect(screen.getByTitle("f".repeat(64)).textContent).toBe("ffffffffffffffff…");
    expect(screen.getByText(/Demo signature/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Setujui" })).toBeTruthy();
  });

  it("in OIDC mode without fresh reauth, triggers /api/auth/reauth and calls onBeforeReauth", () => {
    const onBeforeReauth = vi.fn();
    const onReauthNavigate = vi.fn();
    render(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Setujui Laporan"
          targetSummary="Laporan Kualifikasi · Eksekusi #12"
          signatureMeaning="approved"
          contentHash={"b".repeat(64)}
          signingAuth={{ oidcMode: true, reauthAuthTime: null, signer: SIGNER }}
          signer={SIGNER}
          reauthNextUrl="/runs/r7/report?reauth_target=qualification_report"
          onBeforeReauth={onBeforeReauth}
          onReauthNavigate={onReauthNavigate}
          action={vi.fn()}
          confirmLabel="Terbitkan Laporan"
        />,
      ),
    );

    expect(screen.getByText(/21 CFR Part 11/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Terbitkan Laporan" })).toBeNull();

    const reauthBtn = screen.getByRole("button", { name: /Autentikasi Ulang dengan Keycloak/i });
    fireEvent.click(reauthBtn);

    expect(onBeforeReauth).toHaveBeenCalledTimes(1);
    expect(onReauthNavigate).toHaveBeenCalledWith(
      "/api/auth/reauth?next=%2Fruns%2Fr7%2Freport%3Freauth_target%3Dqualification_report",
    );
  });

  it("in OIDC mode with fresh reauth_token auth_time, shows live countdown and requires explicit 1-click confirmation without auto-submit", () => {
    vi.useFakeTimers();
    const baseMs = new Date("2026-11-26T05:00:00Z").getTime();
    vi.setSystemTime(baseMs);
    const authTime = Math.floor(baseMs / 1000) - 10; // 50s remaining
    const action = vi.fn();

    render(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Setujui Laporan"
          targetSummary="Laporan Kualifikasi · Eksekusi #12"
          signatureMeaning="approved"
          contentHash={"b".repeat(64)}
          signingAuth={{ oidcMode: true, reauthAuthTime: authTime, signer: SIGNER }}
          signer={SIGNER}
          reauthNextUrl="/runs/r7/report?reauth_target=qualification_report"
          action={action}
          confirmLabel="Terbitkan Laporan"
        />,
      ),
    );

    expect(screen.getByText(/50 detik tersisa/i)).toBeTruthy();
    expect(action).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByText(/45 detik tersisa/i)).toBeTruthy();
    expect(action).not.toHaveBeenCalled();

    const confirmBtn = screen.getByRole("button", { name: "Terbitkan Laporan" }) as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(false);

    act(() => {
      vi.advanceTimersByTime(46000);
    });
    expect(screen.getByText(/Jendela autentikasi ulang \(60 detik\) telah berakhir/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Terbitkan Laporan" })).toBeNull();
    expect(screen.getByRole("button", { name: /Autentikasi Ulang dengan Keycloak/i })).toBeTruthy();
  });

  it("surfaces reauth_required errors distinctly from unauthorized", () => {
    const { rerender } = render(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Tutup Deviasi"
          targetSummary="Deviasi #1"
          signatureMeaning="approved"
          signingAuth={{ oidcMode: true, reauthAuthTime: null, signer: SIGNER }}
          signer={SIGNER}
          reauthNextUrl="/runs/r7/execution?reauth_target=deviation_closure"
          action={vi.fn()}
          confirmLabel="Tutup"
          error="Autentikasi ulang diperlukan"
          isReauthError
        />,
      ),
    );

    expect(screen.getByRole("alert").textContent).toMatch(/Autentikasi ulang diperlukan/i);
    expect(screen.getByRole("button", { name: /Autentikasi Ulang dengan Keycloak/i })).toBeTruthy();

    rerender(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Tutup Deviasi"
          targetSummary="Deviasi #1"
          signatureMeaning="approved"
          signingAuth={{ oidcMode: false, reauthAuthTime: null, signer: SIGNER }}
          signer={SIGNER}
          reauthNextUrl="/runs/r7/execution?reauth_target=deviation_closure"
          action={vi.fn()}
          confirmLabel="Tutup"
          error="Sesi tidak sah (401)"
          isReauthError={false}
        />,
      ),
    );

    expect(screen.getByRole("alert").textContent).toContain("Sesi tidak sah (401)");
    expect(screen.queryByRole("button", { name: /Autentikasi Ulang dengan Keycloak/i })).toBeNull();
  });

  it("shows who is signing, before the confirm action, in both auth modes", () => {
    for (const oidcMode of [false, true]) {
      const { unmount } = render(
        wrap(
          <ElectronicSignatureDialog
            open
            onOpenChange={vi.fn()}
            title="Setujui Protokol"
            targetSummary="Protokol #7"
            signatureMeaning="approved"
            signingAuth={{ oidcMode, reauthAuthTime: null, signer: SIGNER }}
            signer={SIGNER}
            reauthNextUrl="/x"
            action={vi.fn()}
            confirmLabel="Setujui"
          />,
        ),
      );
      const signer = screen.getByTestId("signature-signer");
      expect(signer.textContent).toBe("Dewi Lestari(dewi)");
      expect(screen.getByText("Ditandatangani sebagai")).toBeTruthy();
      unmount();
    }
  });

  it("says the signer is unknown instead of showing a blank when there is no session", () => {
    render(
      wrap(
        <ElectronicSignatureDialog
          open
          onOpenChange={vi.fn()}
          title="Setujui Protokol"
          targetSummary="Protokol #7"
          signatureMeaning="approved"
          signingAuth={{ oidcMode: false, reauthAuthTime: null, signer: null }}
          signer={null}
          reauthNextUrl="/x"
          action={vi.fn()}
          confirmLabel="Setujui"
        />,
      ),
    );
    expect(screen.getByTestId("signature-signer").textContent).toMatch(/tidak diketahui/);
  });
});
