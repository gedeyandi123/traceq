# TP-201: pertanyaan untuk sesi praktisi (Q16)

Daftar ini dipakai saat wawancara praktisi (decision log Q16, sekitar 30 menit). Isinya site decision TP-201 yang dibuat LLM dan belum bisa dinilai pemilik karena butuh pengalaman lapangan. Selama nilai di Bagian A belum direview, dataset belum boleh dibekukan (prinsip 7).

**Konteks untuk praktisi:** TP-201 adalah mesin cetak tablet rotary *single-sided* di pabrik farmasi fiktif. Semua dokumennya (URS, FAT, SAT) sintetis. Angka-angkanya tidak harus sama dengan pabrik tertentu, tetapi tidak boleh terasa janggal bagi orang yang pernah mengkualifikasi mesin sejenis.

**Cara mencatat jawaban:**
- *Setuju*: isi `reviewed_by: practitioner` pada nilai itu di `world/tp201.yaml`.
- *Diubah*: ubah nilainya, isi `reviewed_by: practitioner`, lalu jalankan `uv run pytest`. Perhatikan kolom "Batas" karena beberapa nilai terikat ke hasil uji FAT/SAT atau ke skenario.
- *Ragu*: biarkan, dan catat alasannya.

## A. Wajib dijawab (memblokir freeze)

| # | ID | Nilai sekarang | Pertanyaan | Batas jika diubah |
|---|---|---|---|---|
| 1 | URS-TP201-005 | Gaya pra-kompresi minimal **20 kN** (20% dari gaya utama 100 kN) | Apakah kemampuan pra-kompresi 20 kN wajar untuk mesin dengan gaya utama 100 kN? Apakah aturan "sekitar 20% dari gaya utama" dipakai dalam praktik? | SAT mencatat 20,4 kN. Jika min dinaikkan di atas 20,4, hasil SAT ikut disesuaikan. |
| 2 | URS-TP201-006 | Diameter tablet maksimal **25 mm** | Apakah 25 mm wajar sebagai tablet bulat terbesar di portofolio pabrik generik? Apakah ukuran ini lazim dicetak dengan tooling EU D? | FAT mencatat 25 mm. Perhitungan gaya tekan URS-TP201-004 (25 mm × 200 MPa ≈ 98 kN) memakai nilai ini. |
| 3 | URS-TP201-011 | Bagian non-kontak (rangka, penutup) dari **SS 304** | Apakah SS 304 standar yang lazim untuk bagian non-kontak? | FAT mencatat SS 304. |
| 4 | URS-TP201-012 | Gasket/seal kontak produk dari **EPDM atau silikon** | Apakah dua elastomer ini yang lazim diminta? Dokumen apa yang biasanya diminta sebagai bukti kesesuaiannya (mis. pernyataan food-contact, FDA 21 CFR 177.2600, USP Class VI)? | Tidak ada uji vendor (sengaja *gap*); bebas diubah. |
| 5 | URS-TP201-016 | Akurasi pengukuran gaya tekan maksimal **±1% dari skala penuh** | (a) Berapa akurasi yang lazim tertulis di URS? (b) Apakah dinyatakan terhadap skala penuh atau terhadap nilai terbaca? (c) Untuk kanal pra-kompresi (sekitar 20 kN), apakah ±1% FS dari kanal 100 kN terlalu longgar? | FAT mencatat 0,5% FS. Jika batas diperketat di bawah 0,5, hasil FAT ikut disesuaikan. |
| 6 | URS-TP201-027 | Udara tekan **6–7 bar** di titik ruang cetak | Apakah 6–7 bar lazim di header udara tekan pabrik farmasi? | Utilitas pabrik (*site_only*); bebas diubah. |
| 7 | URS-TP201-030 | Tinggi plafon ruang cetak **3000 mm** | Apakah 3 m cukup untuk mesin cetak rotary beserta hopper dan akses perawatan? Berapa yang lazim? | *site_only*; bebas diubah. |
| 8 | URS-TP201-031 | Suhu ruang cetak **18–25 °C** | Apakah rentang ini lazim untuk ruang cetak di Indonesia? Apakah RH (kelembapan) juga biasanya ditulis di URS mesin? | *site_only*; bebas diubah. |
| 9 | URS-TP201-032 | Changeover + pembersihan antar produk maksimal **120 menit** | Apakah 2 jam realistis untuk mesin 36 stasiun (ganti tooling, bongkar feeder, bersihkan)? Berapa yang lazim? | Tidak ada uji vendor (sengaja *gap*); bebas diubah. |
| 10 | URS-TP201-037 | Vendor wajib menyerahkan **deklarasi kesesuaian keselamatan mesin** | Apakah pabrik di Indonesia biasa meminta deklarasi ini (mis. EC Declaration of Conformity) untuk mesin impor? Apakah ini ditulis di URS atau di dokumen pembelian? | Tidak ada uji vendor (sengaja *gap*); bebas diubah. |

## B. Konfirmasi cepat (sudah disetujui pemilik, tanpa kutipan)

Pemilik menyetujui nilai-nilai ini berdasarkan logika dan cek fakta umum. Praktisi cukup menjawab "wajar" atau "janggal". Kalau janggal, catat dan bahas ulang dengan pemilik.

| # | ID | Nilai | Pertanyaan |
|---|---|---|---|
| 11 | URS-TP201-014 | Kontrol berat otomatis berbasis gaya tekan, wajib di semua mesin baru | Wajar sebagai kebijakan pabrik? |
| 12 | URS-TP201-018 | Interlock pintu pelindung menghentikan mesin | Wajar? |
| 13 | URS-TP201-019 | Tombol emergency stop | Wajar? |
| 14 | URS-TP201-020 | Mesin berhenti otomatis saat punch overload | Wajar? |
| 15 | URS-TP201-026 | Listrik 380 V, 3 fase, 50 Hz | Wajar? |
| 16 | URS-TP201-004 | Gaya tekan utama minimal 100 kN; produk terbesar dikempa sampai sekitar 200 MPa | Apakah 100 kN wajar untuk tablet sampai 25 mm? |

## D. Risk assessment, kalibrasi, dan answer key (agenda lisan, bukan form)

Bagian A–C sudah dikirim sebagai Google Form. Bagian D tidak dikirim sebagai form kedua agar praktisi tidak menerima kiriman berulang; isinya dibahas lisan di sesi review 30 menit (Q16), yang digabung dengan demo minggu 3–4. Isi bagian ini menyangkut penilaian, bukan nilai URS. Kriteria kritis (D1–D3) memblokir sign-off RA (`risk_assessment.reviewed_by`). Dengan aturan RA sekarang (Aspek kritis = Ya bila S ≥ 4), mengubah kritis sebuah requirement berarti mengubah `critical` di URS dan skor S-nya di RA sekaligus. Kelas Coverage tidak ikut berubah.

| # | Topik | Keadaan sekarang | Pertanyaan |
|---|---|---|---|
| D1 | URS-TP201-003, kritis | Kapasitas produksi minimal 120.000 tablet/jam ditandai **kritis** (RA: S = 4) | Kapasitas lebih ke kebutuhan bisnis daripada mutu produk. Apakah lazim ditandai sebagai aspek kritis? |
| D2 | URS-TP201-013, -020, -028, tidak kritis | Pelumas food-grade, proteksi overload punch, dan dust extraction ditandai **tidak kritis** (RA: S = 3) | Ketiganya bisa berdampak ke mutu produk (kontaminasi pelumas, serpihan logam, kontaminasi silang). Mana yang biasanya dianggap aspek kritis? |
| D3 | Fungsi vs dokumen | Akurasi gaya tekan (016) S = 4 tetapi sertifikat kalibrasinya (036) S = 3; material kontak (009) S = 5 tetapi sertifikat materialnya (035) S = 3 | Apakah kegagalan dokumen bukti dinilai lebih rendah daripada kegagalan fungsinya, atau disamakan? |
| D4 | Format RA | FMEA singkat: satu baris per persyaratan URS, skala S/O/D 1–5, RPN = S × O × D, aspek kritis bila S ≥ 4, dan satu kolom pengendalian per kelompok persyaratan | Apakah format dan ambang ini lazim? Kolom apa yang biasanya ada tetapi di sini tidak ada? |
| D5 | Sertifikat sensor gaya (CAL-TP201-01) | Diterbitkan vendor, dua kanal (gaya utama dan pra-kompresi), dikalibrasi sebelum FAT, berlaku 12 bulan | Apakah sertifikat dari vendor diterima, atau pabrik meminta lab terakreditasi? Apakah sensor gaya dikalibrasi ulang setelah instalasi? |
| D6 | Evidence dari alat kedaluwarsa (S2) | SAT-01 memakai tachometer yang kalibrasinya kedaluwarsa sehari sebelumnya, tetapi URS-TP201-003 tetap dihitung *covered_by_vendor* lewat SAT-01 | Apakah hasil uji dari alat ukur yang kedaluwarsa masih dihitung sebagai bukti? |
| D7 | Tanggal ambigu di SAT | Tanggal tulisan tangan seperti `07/05/2026` ambigu dd/mm vs mm/dd bila dibaca sendiri; konteks dokumen memastikannya. Tidak ditanam sebagai cacat. | Apakah reviewer di lapangan akan mempermasalahkannya? |
| D8 | Severity cacat | S5 dan S6 critical; S1, S2, S4 major; S3 dan S7 minor (lihat `answer_key/TP-201/defects.yaml`) | Apakah pembagian ini sesuai cara pabrik menilai temuan? |
| D9 | AC vendor lebih sempit dari URS | FAT-M-02 menguji 20–60 rpm terhadap URS 20–70 rpm. Dihitung *partial* (rentang URS tidak teruji penuh), bukan cacat "AC menyimpang dari URS" | Apakah pabrik menganggapnya cukup dicatat dan diuji ulang di OQ, atau sudah termasuk temuan? |
| D10 | Decision table Coverage | Empat syarat *covered_by_vendor* (vendor dinilai, protokol disetujui site sebelum eksekusi, rentang URS teruji penuh, tidak sensitif transportasi atau diuji ulang di SAT); lihat `docs/design/synthetic-dataset.md` §6 | Apakah ini cara pabrik memutuskan hasil vendor boleh dipakai? Ada syarat yang kurang atau berlebihan? |

## C. Di luar nilai (opsional, jika waktu cukup)

- Apakah ada persyaratan yang lazim di URS mesin cetak tablet tetapi tidak ada di daftar 38 persyaratan TP-201?
- Dari skenario cacat S1–S8 (lihat `docs/design/synthetic-dataset.md`), mana yang paling sering ditemukan di lapangan, dan mana yang terasa dibuat-buat?
