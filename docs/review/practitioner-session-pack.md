# Paket sesi praktisi (sesi pertama, 30 menit, online)

Pegangan presenter untuk sesi pertama dengan praktisi: agenda menit demi menit, jawaban siap untuk setiap hal yang diketahui salah di demo, dan daftar pertanyaan. Dokumen ini hanya mengatur urutan dan kata-kata. Langkah teknisnya ada di `docs/demo-runbook.md`, pertanyaan lanjutan F1–F6 dan agenda D di `docs/review/tp201-practitioner-q16.md`.

**Keputusan yang mendasarinya:** sesi diadakan sesudah freeze 25 Nov di atas rilis 0.1.1 dan rekaman `haiku-r10` (#133). Urutannya mengikuti keputusan owner 16 Nov: tanya jawab lanjutan dulu, demo sesudahnya, supaya demo tidak menggiring jawaban. Sesi berlangsung online dengan layar dibagikan. Tanggal yang ditawarkan: Kamis 26, Jumat 27, atau Senin 30 Nov 2026.

## 1. Sebelum sesi

- **H-1:** jalankan runbook bagian 2 dan 3. Setelah gladi, reset demo supaya matriks kembali ke "0/38 usulan sudah diputuskan", lalu Keluar dan Masuk lagi sebagai Ayu (runbook bagian 7).
- **Bagikan seluruh layar, bukan satu tab.** Sitasi membuka PDF di tab baru, dan sitasi RA-TP201 mengunduh berkas Excel. Kalau yang dibagikan hanya satu tab, praktisi tidak melihat keduanya.
- **Siapkan lembar catatan** (bagian 5) di jendela lain. Jawaban praktisi dicatat kata demi kata.
- **Jangan menyebut lebih dulu** temuan mana yang salah. Bagian 3 dipakai sesudah praktisi memberi penilaiannya.

## 2. Agenda 30 menit

| Menit | Bagian | Yang dilakukan | Rujukan |
|---|---|---|---|
| 0–2 | Pembuka | Tiga kalimat: semua data fiktif (pabrik, vendor, mesin, orang); AI hanya memberi saran dan setiap usulan menunggu keputusan manusia; demo memutar ulang rekaman, jadi tidak ada data yang dikirim ke mana pun. | Runbook bagian 1 |
| 2–9 | Tanya jawab lanjutan | Pertanyaan F1–F6 atas jawaban form 16 Nov, sebelum layar demo dibuka. Kalau waktu mepet, dahulukan F1 (D9), F3 dan F4. | `tp201-practitioner-q16.md` bagian D |
| 9–10 | Masuk dan daftar run | Masuk sebagai Ayu Kartika Sari, lalu buka run TP-201. | Runbook bagian 4, langkah 1–2 |
| 10–14 | Matriks dan sitasi | Jelaskan satu baris: nilai yang disyaratkan, kelas cakupan, alasan, bukti. Buka sitasi URS-TP201-020 (SAT-TP201 hlm. 2) dan tunjukkan bahwa PDF terbuka tepat di halaman itu. Tanyakan: "Apakah cara membaca bukti seperti ini masuk akal?" | Langkah 3–4 |
| 14–16 | Keputusan pada baris cakupan | Tanyakan pendapat praktisi tentang URS-TP201-001, lalu "Terima". Pada URS-TP201-002, "Ubah kelas" dengan alasan. Tunjukkan bahwa baris cakupan tidak punya tombol "Tolak". | Langkah 5 (K3, K5) |
| 16–22 | Menilai temuan | Buka tab Temuan pra-tinjauan. Minta praktisi menilai ketujuh temuan satu per satu: **berguna, tidak berguna, atau ragu**, beserta alasannya. Catat di bagian 5. Sesudah itu, putuskan di layar mengikuti penilaian praktisi, bukan mengikuti kunci. | Langkah 6 (K6, K7) |
| 22–23 | Yang tidak dimasukkan sistem | Tunjukkan klaim yang dibuang pemeriksaan kutipan: sistem membuang klaim yang tidak bisa dikutip, bukan mengarangnya. | Langkah 7 |
| 23–24 | Hasil evaluasi | Tunjukkan k/n, misalnya nilai benar 29/38, dan jelaskan bahwa ini set pengembangan yang dinilai terhadap kunci jawaban. | Langkah 8 |
| 24–25 | Peran baca saja | Keluar, lalu masuk sebagai Citra Maharani Putri: keputusan Ayu terlihat, tetapi tombol keputusan tidak ada. | Langkah 9 (K9) |
| 25–29 | Pertanyaan dari demo | Pertanyaan bagian 4 di bawah, lalu D13 dan D14 kalau masih ada waktu. | Bagian 4 |
| 29–30 | Penutup | Ucapkan terima kasih. Tawarkan sesi kedua (sebelum 20 Des) untuk sisa agenda D, dan tanyakan apakah praktisi bersedia mereview nilai TP-202 (D16). | `tp201-practitioner-q16.md` |

Langkah 10 di runbook (reset) dikerjakan sesudah sesi, bukan di depan praktisi.

**Kalau waktu habis:** sisa agenda D (A10, D5, D6, D8, D4, D7, C2, D15, D16) pindah ke sesi kedua. Yang tidak boleh dipotong adalah penilaian temuan (menit 16–22), karena hanya itu yang menghasilkan angka "satu praktisi menilai k dari N temuan berguna" (ADR 0010, Q10).

## 3. Jawaban siap untuk hal yang diketahui salah

Dipakai hanya bila praktisi menemukan atau menanyakannya. Angkanya dari runbook bagian 6 (laporan scorer `recordings/haiku-r10/report-TP-201.json`). Prinsipnya sama untuk semua butir: akui apa adanya, sebut bahwa AI hanya memberi saran, lalu tanyakan bagaimana praktisi akan menangkapnya.

| # | Kalau praktisi bilang… | Jawaban |
|---|---|---|
| J1 | "Kelas cakupan baris ini salah." | "Betul. Kelasnya benar di 30 dari 38 baris, jadi 8 salah. Karena itulah setiap usulan menunggu keputusan manusia. Kelas yang salah bisa diubah dengan 'Ubah kelas' dan alasannya tercatat." Yang paling sering: lima baris yang ditandai "Sebagian" karena tanggal dianggap ambigu (005, 019, 020, 021, 023), padahal bukti vendornya cukup. |
| J2 | "Nilai teramati ini salah (204 kN, padahal SAT menulis 20,4 kN)." | "Betul, ini salah baca. Nilainya benar di 29 dari 38 baris. Nilai yang disyaratkan tetap benar; yang salah adalah angka teramati yang dibaca dari dokumen." |
| J3 | "Kenapa langkah uji ini dikaitkan dengan persyaratan itu?" | "Pengaitan bukti tidak sempurna: kira-kira 9 dari 10 bukti yang ditampilkan memang relevan, dan kira-kira 9 dari 10 bukti yang seharusnya ada memang ditampilkan. Dua langkah, FAT-M-11 dan FAT-C-02, sering ikut terbawa padahal tidak relevan. Kami sengaja tidak mengubah sistem sebelum sesi ini." |
| J4 | "Temuan 'Referensi kedaluwarsa' ini aneh." | "Betul, rinciannya sendiri menulis tidak ada referensi usang. Ini contoh temuan AI yang harus ditolak." |
| J5 | "Temuan 'Kriteria penerimaan menyimpang dari URS' (RA-TP201 lawan DQ-TP201)." | "Isinya menyentuh konflik ukuran tooling (EU D lawan EU B) yang memang ditanam, tetapi jenis temuannya tidak tepat, jadi penilaian kami menghitungnya salah." Kalau praktisi mengklik kutipannya: "Sumbernya lembar kerja Excel, jadi browser mengunduh berkasnya, bukan membuka halaman. Ini keterbatasan yang sudah diketahui; untuk sekarang tidak diubah." Lalu buka berkas yang terunduh di Excel. |
| J6 | "Temuan 'Data tidak konsisten' soal sensor gaya dan tachometer." | "Masalahnya sungguhan, yaitu kalibrasi tachometer yang kedaluwarsa, tetapi sudah ditemukan oleh aturan dan di sini jenisnya keliru. Jadi temuan AI ini tidak menambah informasi." |
| J7 | "Kenapa tidak ada temuan soal isian SAT yang ditimpa tanpa paraf?" atau "soal material 304?" | "Dua masalah itu memang ada di dokumen dan terlewat sebagai temuan: sistem menemukan 5 dari 7 cacat yang ditanam. Konflik desainnya tetap muncul sebagai kelas 'Konflik' di matriks (URS-TP201-008)." Tanyakan: "Apakah cacat seperti ini biasanya tertangkap di review Anda?" |
| J8 | "122.400 tablet/jam itu ambigu." | "Betul. Sistem menanyakan kedua nilai yang ambigu, tetapi draf langkah uji TS-URS-TP201-003 memakai satu tafsiran tanpa bertanya. Itu kekurangan yang sudah tercatat." |
| J9 | "Teks persyaratan diawali nomor dan 'Tidak' (URS-TP201-024 sampai 038)." | "Betul, di halaman 2 URS sistem ikut mengambil seluruh baris tabel, termasuk kolom Kritis. Kalimat persyaratannya tetap benar dan skor tidak terpengaruh. Perbaikannya dijadwalkan sesudah sesi ini." |
| J10 | "ID alat ukur ini salah baca (E0-MS)." | "Betul. Dari 36 isian tulisan tangan, 35 terbaca persis; ID SW-03 terbaca 'E0-MS'." |
| J11 | "Kenapa alasannya berbahasa Inggris?" | "Sistem menulis alasan dalam bahasa Inggris. Menurut Anda, perlu bahasa Indonesia?" (pertanyaan bagian 4) |
| J12 | "Jamnya salah." | "Waktu ditulis dalam UTC, tujuh jam di belakang WIB. Menurut Anda, sebaiknya WIB?" (pertanyaan bagian 4) |
| J13 | "Waktu pada temuan AI tidak cocok." | "Itu waktu demo diputar ulang, bukan waktu AI dijalankan." |

## 4. Pertanyaan yang lahir dari demo

Dari runbook bagian 9. Tanyakan sesudah demo (menit 25–29), dalam urutan ini:

1. **Bahasa:** alasan dan temuan sekarang berbahasa Inggris. Perlu bahasa Indonesia, atau bahasa Inggris wajar untuk dokumen vendor?
2. **Zona waktu:** waktu keputusan sebaiknya ditulis dalam UTC atau WIB?
3. **Menolak usulan cakupan:** baris cakupan tidak punya "Tolak". Apakah "Ubah kelas" dengan alasan sudah cukup untuk menolak usulan AI?
4. **D9, tanpa ditunjukkan di layar:** FAT menguji turret 20–60 rpm, sedangkan URS meminta 20–70 rpm (FAT-M-02, juga FAT-M-09 untuk paddle feeder). Apakah ini layak menjadi temuan terhadap FAT, atau cukup dicatat dan diuji ulang di OQ? Kalau F1 di awal sesi sudah menjawabnya, lewati.

Lalu, kalau masih ada waktu: D13 (siapa QA approver dan Witness) dan D14 (siapa yang memutuskan alat kerja baru), dari `tp201-practitioner-q16.md`.

## 5. Lembar catatan

Isi selama sesi, kata demi kata. Hasilnya dicatat di #133, dan perubahan kunci atau keputusan baru masuk PR sendiri.

**Penilaian temuan** (dikelompokkan seperti di layar, aturan dulu lalu AI; jangan bacakan mana yang salah menurut kunci):

| # | Temuan | Sumber | Penilaian praktisi (berguna / tidak / ragu) | Alasan praktisi |
|---|---|---|---|---|
| 1 | Protokol vendor tanpa persetujuan site (FAT-TP201-C) | Aturan | | |
| 2 | Kalibrasi kedaluwarsa (SAT-TP201) | Aturan | | |
| 3 | Hasil di luar batas ditandai Pass (FAT-TP201-M) | Aturan | | |
| 4 | Data tidak konsisten: nomor seri (DS-TP201 lawan SAT-TP201) | AI | | |
| 5 | Data tidak konsisten: sensor gaya dan tachometer (SAT-TP201) | AI | | |
| 6 | Kriteria penerimaan menyimpang dari URS (RA-TP201, DQ-TP201) | AI | | |
| 7 | Referensi kedaluwarsa (DQ-TP201) | AI | | |

Hasilnya: k dari 7 temuan dinilai berguna oleh satu praktisi.

**Jawaban lain:** F1–F6, empat pertanyaan bagian 4, D13, D14, dan hal yang disebut praktisi tanpa ditanya.
