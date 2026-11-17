# Review skor risk assessment RA-TP201 (sebelum freeze 25 Nov)

Status: **diputuskan owner, 17 Nov 2026** (#133). Dibuat oleh agen pada 17 Nov 2026 dari `world/tp201.yaml`; tabel di bawah adalah usul sebelum keputusan.

## Keputusan (17 Nov 2026)

- Ambang S ≥ 4 tetap. O dan D semua baris disetujui apa adanya.
- **012 dan 025: S3 → S4** (kritis). 012: material kontak produk, sama seperti pelumas 013. 025: timestamp audit trail adalah integritas data, sama seperti 021 dan 022.
- **017: tetap S3** sampai sesi (D9).
- **037: tetap S2** sampai sesi (A10). Usul S4/S5 di bawah ditarik: itu ekstrapolasi aturan praktisi pada baris yang praktisi jawab "tidak tahu", dan critical aspect GMP menyangkut mutu produk dan keselamatan pasien, bukan dokumen keselamatan mesin.
- **Bagian B: tetap.** 010 (kekasaran permukaan) kandidat terkuat; ditanyakan di sesi (D15).
- Semua skor lain disetujui owner dan ditandai "not reviewed by a practitioner". Jumlah kritis: 18 dari 38.
- TP-202 dibekukan dengan nilai draf LLM apa adanya (owner bukan praktisi; agen tidak membuka data held-out); review praktisi di agenda (D16).

Sumber: `world/tp201.yaml` (`risk_assessment`), dibuat otomatis dari data dunia. Ambang kritis sekarang: **S ≥ 4** ("kegagalan berdampak langsung pada mutu produk, keselamatan, atau integritas data"). Skala 1–5; RPN = S × O × D.

## Apa yang diputuskan dan dampaknya

- **S (keparahan) menentukan status kritis.** Bila S melewati ambang 4 (naik dari 3 atau turun dari 4), status kritis persyaratan berubah. Akibatnya: kolom "Kritis" di URS dan RA berubah (byte korpus berubah), answer key berubah (PR tersendiri, design §10), dan aturan witness berubah (kriteria 6 Test Step, belum dinilai). Kelas cakupan di answer key dan gate `unsafe_covered_by_vendor` tidak bergantung pada status kritis. Sistem membaca kolom "Kritis" di URS, jadi jawaban model bisa ikut berubah; itu terukur di run freeze.
- **O (kemungkinan) dan D (deteksi) hanya mengubah RPN** yang tercetak di dokumen RA. Tidak ada skor eval atau keputusan sistem yang memakai O, D atau RPN. Taruhannya kecil; usul: setujui apa adanya.
- **Ambang 4:** usul tetap. Mengubah ambang mengubah status kritis banyak baris sekaligus.
- Kolom "Usul" ditulis oleh asisten AI dari aturan yang sudah ada (definisi di atas, aturan praktisi dari form). Itu justru jenis keputusan yang menurut prinsip 7 harus diputuskan manusia: Anda bebas menolaknya.

## A. Perlu keputusan Anda (4 baris)

| ID | Persyaratan | S sekarang | Alasan usul |
|---|---|---|---|
| 012 | Gasket dan seal yang kontak dengan produk terbuat dari {allowed}. | 3 | Seal kontak produk (S3) berefek kontaminasi produk, sama seperti material kontak 009 (S5) dan pelumas 013 (S4, kritis menurut form). Usul: S4. |
| 017 | Kecepatan paddle feeder dapat diatur pada rentang …–… rpm. | 3 | Kecepatan feeder (S3) berefek variasi bobot tablet, sama seperti kecepatan turret 002 (S4). Form juga menyamakan keduanya (transport-sensitive). **Tetapi** status kritis 017 adalah inti D9 (#100): praktisi menjawab rentang vendor yang lebih sempit "tergantung kekritisan parameter", dan FAT-M-09 (pada 017) dibedakan dari FAT-M-02 (pada 002, kritis) karena itu. Mengubahnya sekarang menjawab D9 sebelum sesi. **Usul: biarkan S3 sampai sesi**, tanyakan di D9. |
| 025 | Jam sistem HMI disinkronkan dengan sumber waktu pabrik. | 3 | Jam HMI tidak sinkron (S3) membuat waktu audit trail tidak bisa dikorelasikan, yaitu integritas data. Audit trail 022 dan level akses 021 sudah S4. Usul: S4. |
| 037 | Deklarasi kesesuaian keselamatan mesin tersedia. | 2 | Deklarasi keselamatan (S2). Aturan praktisi: dokumen bukti dinilai sekritis fungsi yang dibuktikannya (035 S5, 036 S4). Fungsi keselamatan 018/019 = S5. Usul: S4 atau S5, atau biarkan bila deklarasi dianggap dokumen pembelian, bukan bukti fungsi. |

## B. Boleh dicek (6 baris, alasan lebih lemah)

| ID | Persyaratan | S sekarang | Pertimbangan |
|---|---|---|---|
| 005 | Gaya pra-kompresi yang dapat dicapai minimal … kN. | 3 | Capping/laminasi = cacat mutu produk; gaya tekan utama 004 = S5. |
| 010 | Kekasaran permukaan bagian kontak produk Ra maksimal … µm. | 3 | Residu tertahan, sehingga pembersihan tidak efektif (mutu produk). |
| 023 | HMI menyimpan log alarm beserta waktu dan pengguna. | 3 | Log alarm untuk investigasi penyimpangan (integritas data). |
| 024 | Resep produk dapat di-backup dan dipulihkan. | 3 | Resep diketik ulang dengan risiko salah input (mutu/integritas data). |
| 029 | Tingkat kebisingan di posisi operator maksimal … dBA. | 3 | Kebisingan berdampak pada keselamatan operator. |
| 033 | Bagian kontak produk dapat dilepas untuk dibersihkan tanpa alat khusus | 3 | Pembersihan tidak menyeluruh berisiko kontaminasi silang; dust extraction 028 = S4. |

## C. Semua 38 baris

| ID | Mode kegagalan | S | O | D | RPN | Kritis | Transport | Asal S | Tanda |
|---|---|---|---|---|---|---|---|---|---|
| 001 | Jumlah stasiun punch kurang dari kebutuhan | 2 | 1 | 1 | 2 | Tidak |  | draf LLM |  |
| 002 | Rentang kecepatan turret tidak tercapai | 4 | 2 | 2 | 16 | Ya | Ya | draf LLM |  |
| 003 | Kapasitas produksi di bawah kebutuhan | 4 | 2 | 2 | 16 | Ya | Ya | form: dikonfirmasi |  |
| 004 | Gaya tekan utama tidak tercapai | 5 | 2 | 2 | 20 | Ya | Ya | draf LLM |  |
| 005 | Gaya pra-kompresi tidak tercapai | 3 | 2 | 2 | 12 | Tidak | Ya | draf LLM | B |
| 006 | Diameter tablet terbesar tidak dapat dicetak | 2 | 1 | 1 | 2 | Tidak |  | draf LLM |  |
| 007 | Kedalaman pengisian tidak mencukupi | 3 | 1 | 2 | 6 | Tidak |  | draf LLM |  |
| 008 | Tipe tooling berbeda dari inventaris pabrik | 2 | 2 | 1 | 4 | Tidak |  | draf LLM |  |
| 009 | Bagian kontak produk tidak terbuat dari SS 316L | 5 | 2 | 3 | 30 | Ya |  | draf LLM |  |
| 010 | Permukaan kontak produk terlalu kasar | 3 | 2 | 3 | 18 | Tidak |  | draf LLM | B |
| 011 | Material rangka dan penutup tidak tahan pembersihan | 2 | 2 | 2 | 8 | Tidak |  | draf LLM |  |
| 012 | Material gasket atau seal tidak sesuai | 3 | 2 | 3 | 18 | Tidak |  | draf LLM | A |
| 013 | Pelumas bukan food-grade | 4 | 2 | 3 | 24 | Ya |  | form: jadi kritis |  |
| 014 | Kontrol berat otomatis tidak bekerja | 5 | 2 | 3 | 30 | Ya | Ya | draf LLM |  |
| 015 | Tablet di luar batas tidak ditolak | 5 | 2 | 4 | 40 | Ya | Ya | draf LLM |  |
| 016 | Pengukuran gaya tekan tidak akurat | 4 | 2 | 4 | 32 | Ya | Ya | draf LLM |  |
| 017 | Kecepatan paddle feeder tidak dapat diatur pada rentangnya | 3 | 2 | 2 | 12 | Tidak | Ya | draf LLM | A |
| 018 | Interlock pintu pelindung tidak berfungsi | 5 | 2 | 3 | 30 | Ya | Ya | draf LLM |  |
| 019 | Emergency stop tidak menghentikan mesin | 5 | 1 | 2 | 10 | Ya | Ya | draf LLM |  |
| 020 | Proteksi overload punch tidak bekerja | 4 | 2 | 2 | 16 | Ya | Ya | form: jadi kritis |  |
| 021 | Level akses pengguna tidak terpisah | 4 | 2 | 3 | 24 | Ya | Ya | draf LLM |  |
| 022 | Audit trail tidak merekam perubahan | 4 | 2 | 4 | 32 | Ya | Ya | draf LLM |  |
| 023 | Log alarm tidak lengkap | 3 | 2 | 3 | 18 | Tidak | Ya | draf LLM | B |
| 024 | Resep tidak dapat dipulihkan | 3 | 2 | 3 | 18 | Tidak | Ya | draf LLM | B |
| 025 | Jam HMI tidak sinkron dengan waktu pabrik | 3 | 3 | 3 | 27 | Tidak | Ya | draf LLM | A |
| 026 | Suplai listrik tidak sesuai spesifikasi mesin | 2 | 1 | 1 | 2 | Tidak | Ya | draf LLM |  |
| 027 | Tekanan udara tekan tidak sesuai | 3 | 2 | 2 | 12 | Tidak | Ya | draf LLM |  |
| 028 | Kapasitas dust extraction tidak memadai | 4 | 2 | 2 | 16 | Ya | Ya | form: jadi kritis |  |
| 029 | Kebisingan melebihi batas | 3 | 2 | 1 | 6 | Tidak | Ya | draf LLM | B |
| 030 | Mesin tidak muat di ruang cetak | 2 | 1 | 1 | 2 | Tidak | Ya | draf LLM |  |
| 031 | Mesin tidak stabil pada suhu ruang | 2 | 1 | 2 | 4 | Tidak | Ya | draf LLM |  |
| 032 | Changeover dan pembersihan melebihi waktu | 2 | 2 | 1 | 4 | Tidak |  | draf LLM |  |
| 033 | Bagian kontak produk tidak dapat dilepas tanpa alat | 3 | 2 | 2 | 12 | Tidak |  | draf LLM | B |
| 034 | Manual operasi dan perawatan tidak tersedia | 2 | 1 | 1 | 2 | Tidak |  | draf LLM |  |
| 035 | Sertifikat material 3.1 tidak tersedia | 5 | 1 | 1 | 5 | Ya |  | form: jadi kritis |  |
| 036 | Sertifikat kalibrasi sensor gaya tidak tersedia atau kedaluwarsa | 4 | 2 | 2 | 16 | Ya | Ya | form: jadi kritis |  |
| 037 | Deklarasi kesesuaian keselamatan tidak tersedia | 2 | 1 | 1 | 2 | Tidak |  | draf LLM | A |
| 038 | Daftar suku cadang dan gambar as-built tidak tersedia | 2 | 1 | 1 | 2 | Tidak |  | draf LLM |  |

Jumlah kritis sebelum keputusan: 16 dari 38.

## Cara menjawab

Cukup satu pesan, misalnya: *"Ambang 4 tetap. A: 012 S4, 017 tunggu sesi, 025 biarkan, 037 biarkan. B: setuju apa adanya. O dan D: setuju semua."* Setelah itu saya buat PR terpisah (world + answer key + DATASHEET + CHANGELOG, `reviewed_by: owner`); Anda yang merge.
