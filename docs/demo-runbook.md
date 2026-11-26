# Runbook demo TraceQ

Panduan menjalankan demo TraceQ untuk sesi praktisi: persiapan, alur end to end (Proposal Decisions, Protocol Assembly, Execution & Deviations, Ronde Tinjauan, Laporan Kualifikasi, dan login Keycloak dengan tanda tangan elektronik), kasus uji langkah demi langkah, hal yang diketahui salah, dan pemulihan. Perintah dasarnya ada di `README.md` (bagian "Demo"). Dokumen ini tidak mengulanginya kecuali bila urutannya penting.

**Status:** gladi penuh terakhir yang tercatat di bagian 5 dilakukan pada 17 Nov 2026 (rilis 0.1.1, rekaman `haiku-r10`, `main` e3bb58e, 17 kasus), sebelum langkah 5 sampai 8 (Protocol Assembly, Eksekusi & Deviasi, Ronde Tinjauan, Laporan Kualifikasi, Keycloak dan tanda tangan elektronik). Kasus bagian 11 sampai 15 punya kolom "Hasil" sendiri; sel yang kosong belum diverifikasi ulang pada stack demo saat ini. Demo memakai rekaman r10 atas keputusan owner. Riwayat gladi sebelumnya ada di riwayat git berkas ini.

## 1. Apa yang ditunjukkan demo, dan apa yang tidak

- **Ditunjukkan:** matriks ketertelusuran TP-201 (38 persyaratan) dengan bukti yang dikutip sampai halaman PDF, temuan pra-tinjauan (aturan dan AI), keputusan manusia (terima, ubah kelas, tolak) yang tercatat di Audit Trail, peran baca saja, dan skor eval dengan k/n.
- **Bukan panggilan LLM langsung:** run diputar ulang dari rekaman `recordings/haiku-r10` dan tidak mengirim apa pun ke API. "Biaya run: 0,039 USD" di layar eval adalah biaya panggilan yang direkam saat dijalankan live (`cost_usd`), bukan biaya demo (`live_cost_usd` = 0).
- **Data fiktif:** pabrik, vendor (Pressora Maschinenbau GmbH), mesin dan persona demo semuanya sintetis (ADR 0001).
- **AI hanya memberi saran:** setiap Proposal menunggu keputusan manusia (ADR 0002, ADR 0009).
- **Dua mode login:** persona demo bawaan tidak memakai kata sandi dan bukan kontrol akses sungguhan. Mode Keycloak OIDC dengan tanda tangan elektronik berotentikasi ulang tersedia di bagian 15 (ADR 0005, ADR 0007).
- **Rekaman r10 dibuat pada rilis 0.1.1:** tanda kritis dan transport-sensitive di layar mengikuti korpus beku, termasuk label form lanjutan (#128).

## 2. Persiapan (H-1)

| # | Langkah | Cek |
|---|---|---|
| P1 | Docker Desktop menyala | `docker info` menjawab |
| P2 | `uv sync` di root repo | tanpa error |
| P3 | Node 24 dan dependensi UI: `cd web && npm ci` | `npm ci` selesai. Tanpa langkah ini `npm run dev` gagal di checkout baru |
| P4 | Unduh dan cek korpus: `gh release download corpus-v0.1.1 --repo gedeyandi123/traceq --pattern 'corpus-0.1.1.tar.gz*'`, lalu `sha256sum -c corpus-0.1.1.tar.gz.sha256` dan `tar -xzf corpus-0.1.1.tar.gz` | `OK`; folder `t0-2026-06-01/` berisi `manifest.json`, `TP-201/`, `TP-202/` |
| P5 | Port 5432 (Postgres), 8000 (API), 9000 (issuer), 8001 (eval), 3000 (UI) bebas, atau 5432 dipakai Postgres TraceQ sendiri | `netstat -ano` |
| P6 | Build UI untuk produksi: `cd web && npm run build` | daftar route tampil (`/`, `/runs/[runId]`, …, `/signin`) |
| P7 | Jalankan seluruh bagian 3 dan 5 sekali sebagai gladi | semua kasus sesuai harapan |
| P8 | Matikan mode tidur laptop selama sesi | — |

Pakai **mode produksi** (`npm run build` lalu `npm start`), bukan `npm run dev`. Mode dev menampilkan ikon "N" Next.js di pojok kiri bawah, dan setiap halaman lambat saat pertama kali dikompilasi. Pada latihan, kunjungan pertama ke `/signin` belum tampil sebelum kompilasi selesai. Mode produksi melayani halaman dalam 14–90 ms dan tidak menampilkan ikon dev.

## 3. Menyalakan (hari H)

Jalankan dari root repo, masing-masing di terminal sendiri:

1. **Demo** (Postgres, reset database, replay, issuer, API, import):
   `uv run python scripts/demo.py <CORPUS_DIR>/t0-2026-06-01 --recordings recordings/haiku-r10`
   (rilis 0.1.1 dengan rekaman r10, dari `main`. Rekaman lama seperti r8 tidak bisa diputar ulang dari `main` sejak prompt berubah: perintahnya berhenti dengan "… calls are not recorded"; r8 hanya jalan dari checkout a975cae. Untuk rilis lain, pakai rekaman yang dibuat di rilis itu: pasangan yang tidak cocok ditolak sebelum database disentuh). Tambahkan `--no-compose` bila Postgres sudah jalan. Perintah ini tetap di foreground. Replay butuh sekitar 0,2 detik. Tunggu baris `demo: ready. …`, lalu jalankan UI mode produksi (langkah 3).
2. **Eval (opsional, disarankan):** tanpa langkah ini halaman "Hasil evaluasi" menulis "Run ini belum dinilai". Ambil run id dari `runs-demo/`, lalu:
   - `uv run python -m traceq_eval world/tp201.yaml runs-demo/<run id>/submission.json --out runs-demo/<run id>` (sekitar 7 detik, keluar dengan `gates PASS`)
   - `uv run python -m traceq_eval.screen serve --runs runs-demo --port 8001`

   Penilaian sengaja tidak masuk `demo.py`: sistem tidak boleh membaca answer key (`tests/test_isolation.py`), dan penilaian adalah tugas harness.
3. **UI:** `cd web && npm start`, lalu buka http://localhost:3000.

**Cek siap (2 menit):** http://127.0.0.1:9000/demo/personas menampilkan 5 persona (Ayu, Bima, Citra, Dewi, Eko). Di `/`, daftar "Run analisis" berisi satu run TP-201 dengan mode "Putar ulang". Matriks menampilkan 38 baris dan baris "0/38 usulan sudah diputuskan"; buka "Jumlah keputusan" untuk melihat "Belum diputuskan 38".

## 4. Alur demo end to end (urutan cerita)

1. **Masuk** di `/signin` → "Masuk sebagai Ayu Kartika Sari" (dapat memutuskan). Header menampilkan "Masuk sebagai Ayu Kartika Sari (identitas demo)".
2. **Daftar run** `/` → klik run TP-201.
3. **Matriks ketertelusuran**: per persyaratan ada nilai yang disyaratkan, kelas cakupan, alasan, bukti (langkah FAT/SAT dengan nilai teramati dan data desain), dan kolom Keputusan. Di atas ada ringkasan cakupan (Konflik, Celah, Sebagian, dst.) dan baris "k/n usulan sudah diputuskan"; tabel "Jumlah keputusan" terlipat di bawahnya dan dibuka dengan klik.
4. **Buka sitasi**: buka lipatan bukti "Semua bukti dan kutipan" (▸ sebelum chip) pada URS-TP201-020, lalu klik "SAT-TP201 rev 0, hlm. 2" PDF terbuka di tab baru tepat di halaman 2 (SAT-05..07). Arahkan kursor ke link untuk melihat kutipan verbatimnya.
5. **Keputusan pada baris cakupan**: "Terima" (kasus K3), lalu "Ubah kelas" dengan alasan (K5). Baris cakupan tidak punya tombol "Tolak": usulan cakupan yang salah diperbaiki dengan mengubah kelasnya. Filter di atas tabel (`Cakupan`, `Status keputusan`) membantu menyaring baris di URL dan tetap terjaga setelah keputusan.
6. **Temuan pra-tinjauan** (tab Temuan pra-tinjauan): temuan aturan (deterministik, tanpa model) dan "Temuan AI (saran)" lengkap dengan model, hash prompt dan kutipan. Panel "Ringkasan temuan" di atas menautkan ke setiap bagian (3 temuan aturan, 4 temuan AI, 2 dokumen yang tidak ada). Terima temuan yang benar dan tolak yang salah, dengan alasan (K6, K7).
7. **Yang tidak dimasukkan sistem** (tab): klaim yang dibuang pemeriksaan kutipan, beserta alasannya, dan kriteria penerimaan yang diserahkan ke manusia. Panel "Ringkasan" menautkan ke setiap bagian (6 klaim dibuang, 10 kriteria penerimaan untuk manusia, 9 teks URS tidak dikutip). Ini bukti bahwa sistem membuang klaim yang tidak bisa dikutip, bukan mengarangnya.
8. **Hasil evaluasi** (tab): k/n per ukuran untuk set pengembangan TP-201 dan gerbang fabrikasi (bagian 6).
9. **Peran baca saja**: "Keluar", lalu masuk sebagai Citra Maharani Putri. Keputusan Ayu terlihat, tetapi tidak ada tombol keputusan (K9).
10. **Reset**: hentikan demo (Ctrl-C) dan jalankan lagi. Database kosong lagi (K11), lalu **Keluar dan Masuk lagi** (bagian 7).

## 5. Kasus uji langkah demi langkah

Kolom "Hasil" berisi hasil gladi 17 Nov 2026 23.18–23.27 UTC pada rilis 0.1.1 dengan rekaman r10 (`main` e3bb58e). ✅ = sesuai harapan dan sudah diamati. "Belum" = belum diuji pada gladi.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K1 | Masuk sebagai pemutus | `/signin` → Ayu | Header "Masuk sebagai Ayu Kartika Sari (identitas demo)"; daftar run (tabel) tampil | ✅ (17 Nov, r10) |
| K2 | Sitasi membuka dokumen asli di halaman yang benar | Buka lipatan bukti "Semua bukti dan kutipan" (▸ sebelum chip), lalu klik link sitasi mana pun; untuk halaman 2 pakai sitasi SAT-05/06/07 | PDF terbuka di halaman yang dikutip. Pada gladi r10, 116 link (102 di matriks, 14 di temuan) mengarah ke 10 dokumen, semuanya HTTP 200, `target=_blank` dengan kutipan di `title`. Sembilan dokumen adalah PDF; satu, RA-TP201 pada temuan AI "Kriteria penerimaan menyimpang dari URS", adalah lembar kerja Excel yang diunduh browser, bukan dibuka di halaman 1 (bagian 6) | ✅ (17 Nov, r10) |
| K3 | Terima usulan cakupan | URS-TP201-001 → "Terima" | Baris menjadi "Sudah diputuskan / Diterima oleh Ayu Kartika Sari, <tanggal> UTC"; baris "1/38"; di tabel "Jumlah keputusan" (dibuka): Belum diputuskan 37, Diterima 1 | ✅ (17 Nov, r10; halaman tetap di tempat, juga pada baris jauh di bawah, lihat di bawah tabel) |
| K4 | Ubah kelas tanpa alasan ditolak | URS-TP201-002 → buka "Ubah kelas…" → pilih "Celah" → "Ubah kelas" tanpa alasan | Browser menahan form ("Please fill out this field", pesan bawaan browser dalam bahasa Inggris) | ✅ (17 Nov, r10) |
| K5 | Ubah kelas dengan alasan | Sama, dengan alasan diisi | "Diubah ke Celah oleh Ayu Kartika Sari", alasan tampil miring; kolom Cakupan "Sebagian → Celah"; baris "2/38"; di tabel "Jumlah keputusan": Diubah 1 | ✅ (17 Nov, r10) |
| K6 | Tolak temuan yang salah | Temuan pra-tinjauan → temuan AI "Referensi kedaluwarsa" (DQ-TP201, rinciannya sendiri menulis "no outdated reference found beyond this note") → buka "Tolak…" → isi alasan → "Tolak" | "Ditolak oleh …" dengan alasan; baris temuan "1/7"; Ditolak 1 di tabel "Jumlah keputusan" (Temuan AI). Temuan ini false positive yang diketahui (bagian 6). Sejak #101 tidak ada lagi temuan aturan yang salah, jadi contoh penolakan memakai temuan AI | ✅ (17 Nov, r10) |
| K7 | Terima temuan AI yang benar | Temuan AI "Data tidak konsisten" (nomor seri RTP36-25-0417 vs -0471) → "Terima" (tombol terlihat) | Diterima; baris temuan "2/7"; Temuan AI Diterima 1 di tabel "Jumlah keputusan" | ✅ (17 Nov, r10) |
| K8 | Memutuskan ulang wajib beralasan, dan penolakan API tampil | Pada baris yang sudah diputuskan, buka "Putuskan ulang", kirim "Terima" lagi dengan alasan kosong atau hanya spasi | Alasan kosong: ditahan browser. Hanya spasi: muncul banner "Keputusan ditolak API. Alasan perubahan wajib …" (`?error=refused`); hitungan tetap 2/38 | ✅ (17 Nov, r10) |
| K9 | Peran baca saja | Keluar → masuk sebagai Citra → buka matriks | Keputusan Ayu terlihat; tidak ada tombol Terima, Ubah kelas atau Tolak, dan tidak ada lipatan "Ubah kelas…", "Tolak…" atau "Putuskan ulang"; muncul pemberitahuan "Hanya membaca: …" | ✅ (17 Nov, r10) |
| K10 | Server menolak penulisan tanpa hak | `POST /runs/<id>/proposals/<n>/decisions` ke API: dengan token Citra, lalu tanpa token | 403, lalu 401. Pembatasannya ada di API, bukan hanya di UI | ✅ (17 Nov, r10) |
| K11 | Audit Trail mencatat dan reset mengosongkan | Setelah K3–K15: `docker exec traceq-postgres-1 psql -U postgres -d traceq -c "select id, at, name, action, record_id, reason from audit_trail order by 1"`; lalu reset | Sebelum reset: 1 "run imported" ditambah 1 baris per keputusan. Setelah reset: hanya 1 "run imported" | ✅ (17 Nov, r10: 1 "run imported" + 6 keputusan, setelah reset 1 baris) |
| K12 | Hasil evaluasi | Jalankan langkah eval di bagian 3 → "Hasil evaluasi" | Gerbang fabrikasi lulus, nilai 29/38, kutipan 117/117, recall cacat 5/7, fabrikasi 0/180 dan 0/6, OCR 35/36 (sama dengan `recordings/haiku-r10/report-TP-201.json`); panel "Gerbang dan biaya" menulis "Gerbang fabrikasi: lulus" dan "Biaya run: 0,039 USD" | ✅ (17 Nov, r10; laporan run demo sama persis dengan laporan rekaman kecuali run id, juga sesudah reset) |
| K13 | Halaman eval tanpa harness | Lewati langkah eval | Judul "Belum ada hasil evaluasi" dan teks "Run ini belum dinilai, atau API evaluasi tidak dapat dihubungi"; halaman lain tetap jalan | ✅ (17 Nov, r10; eval screen dimatikan sebentar) |
| K14 | Mode produksi | `npm run build` lalu `npm start`, lalu satu keputusan | Halaman dan PDF terlayani, keputusan tersimpan, tidak ada ikon dev | ✅ (17 Nov, r10) |
| K15 | Pemutus kedua | Masuk sebagai Bima, buka "Putuskan ulang" pada baris yang diputuskan Ayu dan putuskan (dengan alasan) | "Diterima oleh Bima Arya Nugraha" dengan alasan dan "Keputusan sebelumnya atas isi ini"; Audit Trail punya baris baru dengan `old_value` (keputusan Ayu), `new_value` dan `reason` | ✅ (17 Nov, r10; baris tetap terlihat, lihat di bawah tabel) |
| K16 | Ctrl-C di terminal sungguhan | Ctrl-C pada `demo.py` | Issuer dan API berhenti ("Application shutdown complete"), port 8000 dan 9000 bebas, Postgres tetap jalan | ✅ (17 Nov, r10; CTRL_C_EVENT asli ke console demo, prompt kembali; kode keluar tidak dibaca kali ini, pada gladi r8 exit 0) |
| K17 | Docker mati | Jalankan `demo.py` (tanpa `--no-compose`) saat Docker tidak bisa dihubungi | "could not start Postgres with Docker Compose (…); is Docker running?", exit 2 | ✅ (17 Nov, r10; Docker disimulasikan tidak terjangkau dengan `DOCKER_HOST` ke port tertutup, port demo lain) |

**Posisi halaman setelah keputusan.** Setiap keputusan mengirim form, dan server mengarahkan kembali ke halaman yang sama. Diukur pada gladi r10, 17 Nov 2026 (posisi gulir `scrollY` sebelum dan sesudah, jendela 1920 px):

- Keputusan langsung tetap di tempat: "Terima" (K3 pada URS-TP201-001, 105 → 105 px; juga pada URS-TP201-031 jauh di bawah, 3569 → 3569 px) dan "Terima" pada temuan AI (K7, 564 → 564).
- Keputusan lewat lipatan dengan alasan menjaga baris tetap terlihat, tetapi halaman bergeser sedikit saat form menutup: "Ubah kelas…" (K5, 367 → 418) dan "Tolak…" (K6, 934 → 859).
- Penolakan API kembali ke atas bersama banner (K8), karena URL berubah menjadi `?error=refused`. Pada gladi r8, keputusan sukses pertama sesudahnya juga kembali ke atas, karena `?error` dihapus dari URL (URS-TP201-030: 3438 → 0); pada gladi r10 hal ini tidak diukur ulang.
- Keputusan lewat "Putuskan ulang" oleh pemutus kedua (K15) pada URS-TP201-001: 211 → 0, karena form yang menutup memendekkan halaman di atas baris; baris tetap terlihat (bagian atasnya di 492 px). Pada gladi r8 halaman bergeser naik 366 px.

Presenter yang memutuskan jauh di bawah halaman perlu menggulir kembali ke barisnya hanya setelah K8.

## 6. Yang diketahui salah di rekaman r10 (TP-201, set pengembangan)

Siapkan jawabannya sebelum praktisi menemukannya. Angka di bawah dari laporan scorer `recordings/haiku-r10/report-TP-201.json` (run 20261117T211439Z-f6ddbf, scorer 0.8.0, dinilai ulang sesudah #101 dan #204 dengan angka yang sama; laporan run demo sama persis kecuali run id).

- **Kelas cakupan benar 30/38**, nilai benar 29/38. Ukuran pertama tidak muncul di layar eval, yang hanya menampilkan akurasi nilai. Ke-8 kelas yang salah adalah alasan setiap usulan menunggu keputusan manusia.
  - Usulan "Sebagian" dengan alasan "condition 2: date ambiguous" untuk langkah SAT yang sebenarnya *covered_by_vendor* (005, 019, 020, 021, 023).
  - Usulan "Celah" ("no FAT/SAT step addresses it", tanpa bukti) untuk 011, yang seharusnya *covered_by_vendor*, dan untuk 016, yang seharusnya "Sebagian".
  - 034 "Sebagian" ("FAT-M-11: URS value not verified") yang seharusnya *covered_by_vendor*.
- **Sembilan nilai salah** (001, 003, 006, 007, 008, 016, 026, 030, 034). Contoh yang terlihat: URS-TP201-005 menampilkan "Teramati: 204 kN" untuk nilai yang dicatat SAT sebagai 20,4 kN (nilai yang disyaratkan tetap benar).
- **Bukti:** presisi 0,880 dan recall 0,929 (r8: 0,875 dan 0,857). Langkah berlebih dari `link` diselidiki pada 18 Nov (#172): 038 (FAT-M-11) dan 014 (FAT-C-02) muncul hampir di setiap jawaban, 002 (SAT-01) hanya kadang-kadang. Prompt tidak diubah sebelum sesi praktisi.
- **Recall cacat 5/7, presisi temuan 5/8.** Tiga temuan bukan cacat yang benar, semuanya temuan AI:
  - "Referensi kedaluwarsa" (DQ-TP201): rinciannya sendiri menulis tidak ada referensi usang. Ini contoh penolakan pada K6.
  - "Kriteria penerimaan menyimpang dari URS" (RA-TP201 lawan DQ-TP201, tooling EU D lawan EU B): isinya menyentuh konflik tooling S6, tetapi scorer tidak mencocokkannya dengan cacat S6 dan menghitungnya false positive. Kutipannya menunjuk RA-TP201, lembar kerja Excel: link sitasinya mengunduh berkas, bukan membuka halaman.
  - "Data tidak konsisten" tentang serial sensor gaya dan kalibrasi tachometer: menunjuk cacat kalibrasi kedaluwarsa (S2) yang sudah ditemukan aturannya, dengan jenis yang salah (`mislabelled`).

  Tiga temuan aturan "Tanda tangan atau tanggal tidak ada" pada sertifikat kalibrasi sudah hilang (#101). Dua cacat yang terlewat sebagai temuan adalah koreksi GDP (S1) dan konflik desain (S6). Konflik tooling S6 tetap tampil sebagai kelas "Konflik" pada URS-TP201-008 di matriks.
- **Nilai ambigu "122.400 tablets/h":** 2 dari 2 nilai ambigu ditanyakan, tetapi rancangan langkah uji TS-URS-TP201-003 mengutip satu tafsiran tanpa bertanya (`silently_resolved` 1, diterima owner bersama #182).
- **Teks persyaratan URS halaman 2** (URS-TP201-024 s.d. 038): jawaban `segment` untuk halaman itu masih mengambil seluruh baris tabel (diawali ID dan isi kolom Kritis, misalnya "URS-TP201-024 Tidak Resep produk …"). Untuk run baru, matriks dan Protocol menampilkan kalimat persyaratannya saja (ID dan sel Kritis dibuang saat ditampilkan); kutipan sumber tetap baris penuh. Prompt `segment` belum diubah: itu jalur B, menunggu sesi praktisi (#145). Skor tidak membaca teks ini.
- **OCR:** layar eval menulis 35/36 entri terbaca persis: ID instrumen SW-03 di SAT-TP201 hlm. 1 terbaca "E0-MS" (sama dengan r7).
- **Alasan dalam bahasa Inggris:** kolom Alasan, rincian temuan dan alasan pada "Yang tidak dimasukkan sistem" berbahasa Inggris di dalam UI berbahasa Indonesia. Tanyakan ke praktisi apakah ini mengganggu (bagian 9).
- **Waktu dalam UTC:** keputusan ditulis "… 12.10 UTC", bukan WIB.
- **Waktu pada temuan AI** adalah waktu replay, bukan waktu panggilan live.

## 7. Reset, pemulihan dan jebakan

| Gejala | Penyebab | Tindakan |
|---|---|---|
| Halaman 404 setelah reset | Setiap reset membuat run id baru, dan tab lama masih menunjuk run lama. Halaman menampilkan 404 berbahasa Indonesia "Halaman tidak ditemukan" dengan "Kembali ke daftar run" (HTTP 404), tetapi judul tab browser masih "Matriks ketertelusuran · TraceQ"; ini keterbatasan yang diketahui | Mulai dari `/` |
| Banner "Hanya membaca: API tidak menerima token …" padahal header masih menulis "Masuk sebagai …" | Issuer membuat kunci tanda tangan baru setiap kali start, jadi cookie lama ditolak | **Keluar lalu Masuk lagi setelah setiap reset** |
| `port 8000 is in use` | Demo sebelumnya masih jalan | Ctrl-C pada demo sebelumnya, lalu jalankan lagi |
| "Run ini belum dinilai" | Eval screen tidak jalan, atau run baru belum dinilai | Ulangi langkah eval di bagian 3 dengan run id baru |
| Halaman pertama lambat atau gagal | UI dijalankan dengan `npm run dev` | Pakai `npm run build` lalu `npm start` |
| Token kedaluwarsa | Masa berlaku token demo 8 jam | Keluar lalu Masuk lagi |

Reset menghapus seluruh keputusan dan Audit Trail. Ini sengaja, dan justru karena itu reset bukan bukti ketahanan Audit Trail.

## 8. Mematikan

Ctrl-C pada `demo.py`, eval screen dan `npm start`. Postgres tetap jalan; matikan dengan `docker compose stop postgres` bila perlu. `runs-demo/` diabaikan git.

## 9. Pertanyaan untuk praktisi yang lahir dari demo

- Bahasa alasan dan temuan: perlu bahasa Indonesia, atau bahasa Inggris wajar untuk dokumen vendor?
- Waktu keputusan: UTC atau WIB?
- Baris cakupan tanpa "Tolak": apakah "Ubah kelas" cukup untuk menolak usulan AI?
- D9 (#100): apakah FAT-M-02 dan FAT-M-09 layak menjadi temuan? Di rekaman r10 keduanya tidak lagi tampil, karena `ai_review` kini melaporkan "Kriteria penerimaan menyimpang dari URS" hanya untuk protokol milik site; tanyakan tanpa menunjukkannya di layar.

## 10. Draf protokol OQ (irisan 3, spec #196)

Layar "Draf protokol" menampilkan draf protokol OQ milik site dari Review Package `TP-201-OQ-draft` 0.1.0: setiap langkah uji dalam urutan draf dengan kriteria penerimaan (KP) seperti terbaca, nilai URS yang dibandingkan, pembanding per dokumen vendor (datasheet, FAT, SAT: langkah FAT/SAT dan data desain dari matriks, atau "tidak ada"; hanya ditampilkan), dan temuannya atau "Tidak dibandingkan" dengan alasannya; lalu temuan tentang seluruh dokumen. Langkah uji yang tercetak di draf tetapi bacaannya dibuang oleh pemeriksaan kutipan tetap tampil di tempatnya dengan "Tidak terbaca: …" dan alasannya (run live pertama r1 punya tiga: OQ-01, OQ-03 dan OQ-12; r3 tidak punya). Langkah uji OQ yang dirancang TraceQ sendiri tidak tampil di sini. Draf dimuat bersama paket saat demo dinyalakan; tidak ada unggahan.

**Menyalakan dengan paket.** Ganti perintah demo di bagian 3 langkah 1 dengan:

`uv run python scripts/demo.py <CORPUS_DIR>/t0-2026-06-01 --recordings recordings/haiku-r10 --review-package recordings/TP-201-OQ-draft-0.1.0 --package-recordings recordings/haiku-oq-draft-r3`

Run-nya menjadi run Review Package: Pre-review peralatan diputar ulang dari r10 tanpa perubahan, draf dibaca dari rekaman paket, keduanya hanya dibaca. Tunggu baris `demo: … with the Review Package …` lalu `demo: ready`. Kedua opsi paket wajib bersama; satu saja ditolak sebelum database disentuh.

**Batas yang harus diketahui presenter:**

- Rekaman draf di `recordings/haiku-oq-draft-r3` adalah **run live ketiga** (Claude Haiku, 19 Nov, prompt dengan aturan tabel yang berlanjut ke halaman berikutnya; `recordings/README.md`), berlabel "dev only; labels not reviewed": kunci jawaban paket belum ditinjau. Angka di bawah berasal dari rekaman itu. Semua 26 langkah uji terbaca dan kedua halaman tabel ketertelusuran terbaca. Ini satu sampel: jangan menyebut angkanya sebagai hasil aturan baru. (r1, run live pertama: tiga langkah uji tidak terbaca karena kutipan berisi judul langkah; r2 tidak di-merge; angka keduanya di `recordings/README.md`.)
- Kutipan ke draf (OQ-TP201) **bukan link**: API hanya menyajikan dokumen korpus, dan draf bukan dokumen korpus. Arahkan kursor untuk melihat kutipannya. Kutipan ke URS dan pembanding tetap membuka PDF.
- Draf dibaca dengan token: tanpa masuk, layar meminta masuk.
- Penilaian (bagian 3 langkah 2) untuk run Review Package memerlukan `--package world/tp201-oq-draft.yaml`; layar eval untuk run ini belum dilatih.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K18 | Demo memuat paket | Nyalakan dengan perintah di atas, buka `/`, lalu run TP-201 | Satu run; header run menulis "Draf protokol: OQ-TP201 rev 0 (TP-201-OQ-draft 0.1.0)"; tab "Draf protokol" di antara "Temuan pra-tinjauan" dan "Yang tidak dimasukkan" | ✅ (18 Nov, fixture paket di atas r10, stack kedua di port lain) |
| K19 | "OQ tidak ada" tetap | Tab "Temuan pra-tinjauan" | Sama dengan run tanpa paket: 3 temuan aturan, 4 temuan AI, "Dokumen yang tidak ada" tetap memuat IQ-TP201 dan OQ-TP201; tab "Draf protokol" menautkan ke draf | ✅ (18 Nov: 3 aturan, 4 AI, IQ dan OQ tidak ada, 0/7; temuan draf tidak tercampur) |
| K20 | Draf tanpa masuk | Keluar, buka `/runs/<id>/draft` | "Masuk untuk melihat draf protokol"; tidak ada tabel | ✅ (18 Nov) |
| K21 | Langkah uji dalam urutan draf | Masuk sebagai Ayu → tab "Draf protokol" | Ringkasan "26 Langkah uji", "19 Langkah uji tidak dibandingkan", "2 Temuan tentang seluruh dokumen" (tanpa "tidak terbaca"); baris pertama OQ-01 "Tidak dibandingkan: the URS states a single number…"; OQ-05 "minimal 15 kN" dengan nilai URS "≥ 20 kN", "Menyimpang dari URS" dan temuan "Kriteria penerimaan lebih longgar dari URS"; "0/5 usulan sudah diputuskan" | ✅ (18 Nov; diulang 19 Nov setelah #221); ✅ diulang 19 Nov di browser dengan rekaman live r1 (build produksi :3002, stack kedua): 26, 3 tidak terbaca (OQ-01, OQ-03, OQ-12), 17 tidak dibandingkan, 2 temuan dokumen, OQ-05 seperti di atas, 0/4; ⏳ belum diulang di browser dengan r3 (angka harapan dari data run r3) |
| K22 | Kutipan | Pada OQ-05: arahkan kursor ke "OQ-TP201 rev 0, hlm. …", lalu klik link "URS-TP201 rev 1, hlm. …" | Kutipan draf tampil sebagai tooltip, bukan link; link URS membuka PDF URS di halaman itu | ✅ (18 Nov: kutipan draf berupa tooltip; link URS menyajikan application/pdf) |
| K23 | Terima temuan draf | OQ-05 → "Terima" | "Diterima oleh Ayu Kartika Sari, …"; "1/5" (r1: "1/4"); di "Jumlah keputusan": baris "Temuan draf protokol", Diterima 1; halaman kembali ke `/runs/<id>/draft` | ✅ (18 Nov) |
| K24 | Tolak temuan dokumen dengan alasan | "Temuan tentang seluruh dokumen" → URS-TP201-002 → "Tolak…" → isi alasan → "Tolak" (tanpa alasan: ditahan browser) | "Ditolak oleh …" dengan alasan; "2/5" (r1: "2/4"); Ditolak 1 | ✅ (18 Nov: tanpa alasan formulir tidak valid, `required`) |
| K25 | Pembaca | Keluar → masuk sebagai Citra → tab "Draf protokol" | Keputusan Ayu terlihat; tidak ada tombol Terima/Tolak atau lipatan "Tolak…"/"Putuskan ulang"; "Hanya membaca: …" | ✅ (18 Nov) |
| K26 | Lebar layar | Ulangi K21 pada 1920 px dan pada jendela sempit (di bawah 1199 px dan sekitar 768 px) | Ringkasan dan "Jumlah keputusan" bertumpuk di bawah 1199 px; tabel bergulir ke samping di dalam bingkainya, halaman tidak | ✅ (18 dan 19 Nov: 1920 berdampingan; 1100 dan 768 bertumpuk; pada 768 tabel 918 px bergulir di bingkainya, lebar halaman tetap; diukur dengan iframe same-origin) |
| K27 | Pembanding per dokumen vendor | Pada K21, lihat kolom "Pembanding" baris OQ-05 | OQ-05: datasheet DS-TP201 dengan "Maximum pre-compression force", FAT-TP201-C dan FAT-TP201-M "tidak ada", SAT-TP201 dengan SAT-02 dan link ke PDF SAT; setiap baris yang terbaca menyebut keempat dokumen itu, masing-masing dengan faktanya atau "tidak ada" | ✅ (19 Nov, baris OQ-03 rekaman tiruan); ✅ diulang 19 Nov dengan rekaman live r1: OQ-05 seperti yang diharapkan, link SAT menyajikan application/pdf; 23 baris terbaca semuanya menyebut keempat dokumen; ⏳ belum diulang di browser dengan r3 |

## 11. Protokol yang disusun di TraceQ (langkah 5a, spec #247)

Layar "Protokol (disusun di TraceQ)" (`/runs/<id>/protocol`, tab di header run, terpisah dari tab "Draf protokol" milik site) menyusun protokol IQ/OQ peralatan dari keputusan manusia atas run: satu baris per persyaratan, memakai langkah uji rancangan TraceQ yang diterima atau disunting, atau langkah uji yang ditulis orang (ADR 0012). Persona keempat, **Dewi Anggraini Lestari** (`dewi`), hanya memegang peran menyetujui; Ayu dan Bima memutuskan, Citra membaca. Tidak ada persona yang memegang kedua peran.

**Menyalakan.** Sama dengan bagian 3 (run TP-201 r10 biasa; tab Protokol tidak butuh paket). Cek siap: `/demo/personas` menampilkan 4 persona dan halaman masuk menawarkan "Masuk sebagai Dewi Anggraini Lestari".

**Gladi mulai dari database yang direset.** Protokol yang sudah Disetujui menghalangi protokol baru untuk peralatan yang sama (ADR 0012), jadi setiap gladi dimulai dari `demo.py` yang baru dijalankan (bagian 7: reset, lalu Keluar dan Masuk lagi). Pengajuan penuh pada run TP-201 berarti memutuskan **38 kelas Cakupan**, **31 rancangan langkah uji** (7 persyaratan `covered_by_vendor` menjadi baris "Referensi vendor" dan tidak perlu rancangan diputuskan) dan menetapkan **21 kriteria penerimaan** (19 rancangan tanpa kriteria penerimaan dan 2 dengan teks bebas). Itu lama untuk demo hidup: lakukan sebagian di depan peserta (K29 sampai K31) dan selesaikan sisanya sebelum sesi.

**Batas yang harus diketahui presenter:**

- Penolakan persetujuan oleh Penyusun di demo adalah **penolakan berdasarkan peran**: Ayu dan Bima tidak memegang peran menyetujui, dan tidak ada persona yang memegang keduanya. Aturan "Penyusun tidak boleh menyetujui" dan "penulis isi salinan tidak boleh menyetujui" hanya ditunjukkan oleh tes, bukan di layar.
- Run demo TP-201 punya **0 dari 38 nomor yang terlewat**, jadi bagian "Nomor persyaratan tercetak yang terlewat" kosong dan formulir jawabannya tidak bisa ditunjukkan. Jawaban atas nomor terlewat hanya ditunjukkan oleh tes.
- Tanda tangan dirancang untuk 21 CFR Part 11, CPOB Annex 7, dan draf EU GMP Annex 11 (2025), belum divalidasi; mode demo memakai tanda tangan demo (ADR 0007). Satu langkah uji per persyaratan, IQ dan OQ digabung, tidak ada cetak atau ekspor, tidak ada versi baru setelah disetujui (langkah 6). Panel "Batas yang diketahui" di layar menulis ini.
- Protokol dibaca dengan token: tanpa masuk, layar meminta masuk.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K28 | Memulai protokol | Masuk sebagai Ayu → tab "Protokol (disusun di TraceQ)" → "Mulai protokol dari run ini" | Status "Draft (sedang disusun)"; riwayat "Dimulai oleh Ayu Kartika Sari, …"; daftar "Yang memblokir pengajuan" berisi jumlah di atas nol; "Baris protokol" menulis "38 baris: …" | ✅ (19 Nov, build produksi dari `feat/protocol-5a` 884a771, korpus 0.2.0 + r10): Draft, "Dimulai oleh Ayu …", Cakupan belum diputuskan 38, "38 baris: 38 masih memblokir, 0 referensi vendor, 0 baris langkah uji" |
| K29 | Memutuskan rancangan | Pada satu baris: "Putuskan di matriks" dan terima cakupannya; kembali ke layar protokol; terima rancangannya | Pemblokir "Cakupan belum diputuskan" dan "Langkah uji rancangan belum diputuskan" berkurang satu; baris menampilkan "Langkah uji rancangan yang diterima" | ✅ (19 Nov, URS-TP201-003): Cakupan 38 → 36 (003 dan 004 diterima di matriks), rancangan 2 → 1, baris "Langkah uji rancangan yang diterima" |
| K30 | Menetapkan kriteria penerimaan yang hilang dengan menyunting | Pada baris rancangan tanpa kriteria penerimaan: "Sunting rancangan dan tetapkan kriteria penerimaan" → "Bentuk": "Rentang (satu atau dua batas, dengan satuan)" (input menyesuaikan bentuk terpilih) → isi batas dan satuan, "Alasan perubahan" → "Simpan suntingan" | Baris menjadi "Langkah uji rancangan yang disunting, versi 1"; "Riwayat versi (1)"; pemblokir "Langkah uji rancangan belum diputuskan" dan "Baris langkah uji tanpa langkah uji" berkurang satu | ✅ (19 Nov, URS-TP201-002, rentang 20–70 rpm): "Langkah uji rancangan yang disunting, versi 1", "Riwayat versi (1)"; rancangan belum diputuskan dan baris tanpa langkah uji masing-masing turun satu (kriteria penerimaan sudah 0 sebelumnya: rancangan yang belum diputuskan dihitung di "rancangan belum diputuskan") |
| K31 | Menulis satu langkah uji | Pada baris tanpa rancangan yang diterima (tolak rancangannya dulu bila perlu): "Tulis langkah uji" → deskripsi, metode, instrumen, bentuk kriteria penerimaan dengan nilainya → "Simpan versi" | "Langkah uji tertulis, versi 1"; pemblokir "Baris langkah uji tanpa langkah uji" berkurang satu. Bila rancangan baris itu sudah diterima: "Langkah uji rancangan persyaratan ini diterima. Tolak atau putuskan ulang dulu sebelum menulis langkah uji." | ✅ (19 Nov, URS-TP201-037 setelah rancangannya ditolak): "Langkah uji tertulis, versi 1", tanpa langkah uji 1 → 0; pada 003 pesan "Langkah uji rancangan persyaratan ini diterima. …" tampil |
| K32 | Pengajuan | Setelah semua jumlah nol ("Tidak ada yang memblokir: protokol dapat diajukan."): "Ajukan protokol" | Status "Diajukan"; "Salinan beku yang diajukan" dengan Penyusun Ayu dan hash SHA-256; baris tidak lagi dihitung dari keputusan | ✅ (19 Nov): Diajukan, Penyusun Ayu, hash `61a078dd…`. Sisa keputusan sebelum K32 diisi lewat API demo (36 Cakupan, 29 rancangan: 11 diterima, 18 disunting dengan kriteria "Ada"; 0 nomor terlewat) |
| K33 | Persetujuan ditolak untuk Penyusun | Masih sebagai Ayu, buka protokol yang Diajukan | Tidak ada tombol "Setujui protokol" (peran menyetujui tidak dipegang); lewat API jawabannya 403 "approving a Protocol needs the approving role". Ditolak karena peran, bukan karena Ayu Penyusun (lihat batas di atas) | ✅ (19 Nov): tidak ada tombol Setujui/Kembalikan untuk Ayu; API menjawab 403 "approving a Protocol needs the approving role" (teks API berbahasa Inggris) |
| K34 | Pengembalian | Keluar, masuk sebagai Dewi → isi "Alasan pengembalian" → "Kembalikan ke Draft" (tanpa alasan: ditahan browser) | Status "Draft (sedang disusun)"; riwayat "Dikembalikan ke Draft oleh Dewi Anggraini Lestari, …"; salinan lama tampil di "Salinan yang diajukan sebelumnya" | ✅ (19 Nov): tanpa alasan ditahan browser ("Please fill out this field."); "Dikembalikan ke Draft oleh Dewi Anggraini Lestari, …" dengan alasan; "Salinan yang diajukan sebelumnya" tampil |
| K35 | Pengajuan ulang | Keluar, masuk sebagai Bima (atau Ayu); ubah satu baris (misalnya sunting kriteria penerimaan satu baris) → "Ajukan protokol" | Status "Diajukan"; hash berbeda dari salinan sebelumnya; Penyusun adalah yang mengajukan ulang | ✅ (19 Nov, Bima, URS-TP201-002 batas bawah 20 → 21 rpm, "Langkah uji tertulis, versi 2"): Diajukan, hash `bec10438…` berbeda, Penyusun Bima |
| K36 | Persetujuan oleh persona keempat | Keluar, masuk sebagai Dewi → "Setujui protokol" | Status "Disetujui"; riwayat "Disetujui oleh Dewi Anggraini Lestari, …"; catatan "Versi baru protokol ini adalah langkah 6." (tanpa teks "bukan Tanda Tangan Elektronik"); mulai protokol baru ditolak API sampai database direset | ✅ (19 Nov): Disetujui, "Disetujui oleh Dewi Anggraini Lestari, …", tanpa teks "bukan Tanda Tangan Elektronik"; mulai protokol baru: API 409 "… is approved: a new version of an approved Protocol is step 6, not yet built" |
| K37 | Pembaca | Keluar, masuk sebagai Citra → tab Protokol | Semua terlihat; tidak ada tombol mulai, keputusan, sunting, tulis, ajukan, setujui atau kembalikan | ✅ (19 Nov): Disetujui terlihat, banner "Hanya membaca", tidak ada tombol mulai, keputusan, sunting, tulis, ajukan, setujui atau kembalikan |
| K38 | Tanpa masuk | Keluar, buka `/runs/<id>/protocol` | "Masuk untuk melihat protokol"; tidak ada baris | ✅ (19 Nov): "Masuk untuk melihat protokol"; tidak ada baris |

Kolom "Hasil" diisi oleh sesi utama setelah kasus dijalankan di browser pada stack yang dibangun dari cabang integrasi (bukan demo r10 yang berjalan).

## 12. Eksekusi & Deviasi (langkah 5b, spec #270–#276)

Layar "Eksekusi & Deviasi" (`/runs/<id>/execution`, tab di header run, terpisah dari tab "Protokol (disusun di TraceQ)") menjalankan Protokol yang sudah **Disetujui** berdasarkan salinan bekunya: satu baris per baris salinan beku sesuai urutannya (ADR 0013). Persona kelima, **Eko Prasetyo Wijaya** (`eko`), hanya memegang peran saksi (`qualification-witness`). Ayu Kartika Sari (`ayu`) dan Bima Arya Nugraha (`bima`) memegang peran pelaksana (`qualification-executor`) bersama peran memutuskan (`qualification-decider`); Dewi Anggraini Lestari (`dewi`) hanya memegang peran menyetujui (`qualification-approver`, untuk menutup atau mengembalikan Deviasi); Citra Maharani Putri (`citra`) hanya membaca. Tidak ada persona yang memegang peran pelaksana sekaligus penyetuju, ataupun peran pelaksana sekaligus saksi.

**Menyalakan & persiapan.** Sama dengan bagian 3 dan 11 (run TP-201 r10 biasa; cek siap: `/demo/personas` menampilkan 5 persona termasuk `eko` dan halaman masuk menawarkan "Masuk sebagai Eko Prasetyo Wijaya"). Eksekusi dimulai dari Protokol TP-201 berstatus **Disetujui** yang sudah disiapkan sebelum sesi (lihat bagian 11 langkah 5a: **38 kelas Cakupan**, **31 rancangan langkah uji** + 7 baris Referensi vendor, dan **21 kriteria penerimaan**).

**Gladi mulai dari database yang direset.** Hanya **satu Eksekusi** yang diizinkan per Protokol Disetujui, dan Eksekusi tidak dapat dibatalkan (ADR 0013). Jadi setiap gladi dimulai dari `demo.py` yang baru dijalankan (bagian 7: reset, lalu Keluar dan Masuk lagi).

**Aturan yang tidak bisa ditunjukkan oleh persona mana pun (hanya ditunjukkan oleh tes):**

- **Penutup Deviasi yang ikut terlibat (4-way Separation of Duties):** Penutup Deviasi tidak boleh merupakan penulis Investigasi, Pelaksana pada langkah uji terkait, ataupun pembuka Deviasi manual. Di demo, tidak ada persona yang memegang `qualification-executor` dan `qualification-approver` sekaligus — penolakan bagi Ayu/Bima terjadi karena peran, sedangkan aturan keterlibatan 4-arah dibuktikan oleh `tests/test_execution_deviations_api.py` (`test_close_four_way_separation_of_duties`).
- **Pelaksana yang memegang peran pelaksana dan saksi mengonfirmasi hasilnya sendiri:** Di demo, tidak ada persona yang memegang `qualification-executor` dan `qualification-witness` sekaligus — penolakan bagi Ayu/Bima terjadi karena peran, sedangkan penolakan 409 atas Pelaksana yang memegang kedua peran dibuktikan oleh `tests/test_execution_witness_api.py` (`test_performer_holding_both_executor_and_witness_roles_is_refused`).

**Batas yang harus diketahui presenter (panel "Batas yang diketahui" di layar):**

- Bukti adalah referensi teks (unggah berkas hadir pada tahap 6).
- Belum ada langkah uji yang mewajibkan Saksi.
- Uji ulang (Retest) tidak memerlukan izin sebelumnya.
- Angka dibandingkan tanpa pembulatan (toleransi ditulis sebagai rentang).
- Tanggal kedaluwarsa kalibrasi diketik oleh pelaksana, tanpa daftar instrumen.
- Hasil dicatat secara langsung; transkripsi dari kertas tidak didukung.
- Satu eksekusi per protokol yang disetujui dan tidak dapat dibatalkan.
- IQ dan OQ digabung dalam satu eksekusi.
- Tanda tangan dirancang untuk 21 CFR Part 11, CPOB Annex 7, dan draf EU GMP Annex 11 (2025), belum divalidasi; mode demo memakai tanda tangan demo (ADR 0007). Penyelesaian eksekusi dan penutupan ronde adalah status tercatat tanpa tanda tangan.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K39 | Memulai Eksekusi (dan penolakan jika belum Disetujui / Eksekusi kedua) | Sebelum Protokol Disetujui, buka tab "Eksekusi & Deviasi". Setelah Protokol TP-201 berstatus "Disetujui", masuk sebagai Ayu → tab "Eksekusi & Deviasi" → "Mulai eksekusi" | Sebelum Disetujui: "Belum ada protokol yang disetujui" dengan tautan "Buka Protokol IQ/OQ" (API `POST /protocols/{id}/execution` menjawab 409). Setelah dimulai: status "Sedang berjalan", "Riwayat eksekusi" mencatat "Dimulai oleh Ayu Kartika Sari, …", "Baris eksekusi (38)" sesuai salinan beku (7 baris "Referensi vendor" tanpa kontrol aksi), "Daftar periksa penyelesaian eksekusi" tampil. Eksekusi kedua untuk protokol yang sama ditolak API (409) | ✅ (25 Nov, `feat/execution-5b` build produksi + Chrome headless): dimulai lewat klik "Mulai eksekusi" di browser, status "Sedang berjalan", 0 overflow di `390x844`, `1366x768`, `1440x900` |
| K40 | Mencatat hasil Lulus | Pada satu baris "Langkah uji" (misalnya `URS-TP201-002` rentang 20–70 rpm): "Catat hasil" → pilih "Nilai teramati", isi nilai dalam rentang (mis. `45`), isi "ID instrumen" & "Kedaluwarsa kalibrasi (UTC)" di masa depan, referensi bukti (opsional) → "Simpan hasil" | "Percobaan #1" `v1` tersimpan, badge penilaian "Lulus", "Dicatat oleh Ayu Kartika Sari, …", pemblokir "Baris langkah uji tanpa hasil" berkurang satu | ✅ (25 Nov, API demo stack + Chrome): HTTP 201, `verdict: "pass"` |
| K41 | Mencatat hasil Gagal yang otomatis membuka Deviasi | Pada satu baris "Langkah uji" lain: "Catat hasil" → isi nilai di luar kriteria penerimaan (atau pilih "Tidak dapat dilaksanakan" / "Tidak ada instrumen terkalibrasi yang berlaku (membuka Deviasi)") → "Simpan hasil" | "Percobaan #1" `v1` tersimpan dengan badge "Gagal"; satu Deviasi baru berstatus "Terbuka" (sumber "Hasil gagal" atau "Tanpa instrumen terkalibrasi") otomatis muncul di "Deviasi" dan di pemblokir "Deviasi belum ditutup" | ✅ (25 Nov, API demo stack): HTTP 201, 1 Deviasi otomatis terbuka |
| K42 | Mengoreksi percobaan dengan Alasan perubahan | Pada baris yang sudah memiliki hasil (selama tidak ada Deviasi terkait berstatus "Diajukan"/"Ditutup"): buka detail baris (klik ID persyaratan / "Buka detail") → klik "Koreksi" → ubah nilai, isi "Alasan perubahan" (wajib) → "Simpan koreksi" | Versi bertambah menjadi `v2` ("Hasil saat ini") dengan alasan perubahan; `v1` tetap terlihat di riwayat. Bila Deviasi terkait berstatus "Diajukan" atau "Ditutup", tampil "Koreksi terkunci selama deviasi diajukan atau ditutup." | ✅ (25 Nov, API demo stack): HTTP 201, `v2` tersimpan dengan alasan |
| K43 | Uji ulang (Retest) pada langkah uji Gagal | Pada baris berstatus "Gagal" yang memiliki Deviasi "Terbuka": buka detail baris → klik "Uji ulang" → pilih "Deviasi terbuka terkait", isi "Alasan uji ulang" (wajib), isi nilai yang memenuhi kriteria & instrumen terkalibrasi → "Simpan uji ulang" | "Percobaan #2" `v1` tercatat dengan penilaian "Lulus"; "Percobaan #1" tetap ada di riwayat | ✅ (25 Nov, API demo stack): HTTP 201, percobaan #2 lulus |
| K44 | Kedaluwarsa kalibrasi lewat ditolak (409) | Saat mencatat hasil atau uji ulang, isi "Kedaluwarsa kalibrasi (UTC)" dengan tanggal sebelum hari UTC basis data → "Simpan hasil" | Ditolak API dengan HTTP 409 ("Ditolak API: perubahan tidak diizinkan pada status saat ini atau kalibrasi kedaluwarsa."); tidak ada percobaan baru yang tersimpan | ✅ (25 Nov, API demo stack): ditolak HTTP 409 |
| K45 | Konfirmasi Saksi oleh `eko` (dan penolakan untuk Pelaksana `ayu`) | Masih sebagai Ayu, buka detail baris yang baru dicatat. Lalu Keluar → masuk sebagai **Eko Prasetyo Wijaya** (`eko`) → filter "Menunggu Saksi" → buka detail baris → klik "Konfirmasi sebagai Saksi" pada versi terbaru suatu percobaan | Sebagai Ayu: tidak ada tombol "Konfirmasi sebagai Saksi" (via API `POST .../witness` menjawab 403). Sebagai Eko: badge "Dikonfirmasi Saksi", "Disaksikan oleh Eko Prasetyo Wijaya, …", dan lencana tanda tangan, tanpa catatan "bukan Tanda Tangan Elektronik" (bila versi baru dibuat setelahnya, konfirmasi lama bertanda "Dibatalkan oleh versi baru") | ✅ (25 Nov, API demo stack + `/signin` di Chrome): `/signin` menampilkan `Eko Prasetyo Wijaya`, `ayu` ditolak 403, `eko` 201 |
| K46 | Siklus hidup Deviasi (investigasi, ajukan, kembalikan, tutup) | Sebagai Ayu: buka tab "Deviasi" → buka detail Deviasi "Terbuka" → isi investigasi & "Kelas deviasi" → "Simpan investigasi" → "Ajukan deviasi". Keluar → masuk sebagai **Dewi Anggraini Lestari** (`dewi`) → tab "Deviasi" → isi "Alasan pengembalian" → "Kembalikan ke Terbuka". Masuk sebagai Ayu → simpan investigasi `v2` (dengan "Alasan perubahan (wajib untuk versi 2+)") → "Ajukan deviasi". Masuk sebagai Dewi → "Tutup deviasi" → konfirmasi di modal | Setelah diajukan: status "Diajukan". Setelah dikembalikan Dewi: status kembali "Terbuka", "Riwayat status" mencatat "Dikembalikan oleh Dewi Anggraini Lestari, …" dengan alasan. Setelah ditutup Dewi: status "Ditutup", "Riwayat status" mencatat "Ditutup oleh Dewi Anggraini Lestari, …", lencana tanda tangan penutupan, tanpa catatan "bukan Tanda Tangan Elektronik" | ✅ (25 Nov, API demo stack): investigasi v1 → ajukan → kembalikan (`dewi`) → v2 → ajukan → tutup (`dewi`) |
| K47 | Penyelesaian Eksekusi dan penolakan tulis setelah selesai | Sebelum semua langkah uji terisi & Deviasi ditutup, periksa "Daftar periksa penyelesaian eksekusi". Setelah semua 31 langkah uji memiliki hasil dan semua Deviasi "Ditutup": masuk sebagai Ayu → "Selesaikan eksekusi" → konfirmasi di modal | Sebelum siap: daftar periksa menampilkan jumlah pemblokir dan tombol belum aktif. Setelah selesai: status "Selesai", tab "Riwayat & salinan" mencatat "Diselesaikan oleh Ayu Kartika Sari, …", panel "Salinan beku eksekusi" menampilkan "Hash SHA-256 salinan beku"; tombol tulis hilang dan API menolak penulisan setelah selesai (409) | ✅ (25 Nov, API demo stack + Chrome): selesai, `copy_hash` 64-hex tampil di browser, penulisan lanjutan ditolak 409, 0 overflow di `390x844`, `1366x768`, `1440x900` |
| K48 | Pembaca (`citra`) dan tanpa masuk | Keluar → masuk sebagai **Citra Maharani Putri** (`citra`) → tab "Eksekusi & Deviasi". Lalu Keluar → buka `/runs/<id>/execution` | Sebagai Citra: seluruh baris, hasil, Saksi, dan Deviasi terlihat; tidak ada tombol mulai, catat hasil, koreksi, uji ulang, konfirmasi Saksi, deviasi, atau selesaikan. Tanpa masuk: tampil "Masuk untuk membaca atau memulai eksekusi" dan tautan "Masuk (identitas demo)"; tidak ada baris | ✅ (25 Nov, API demo stack + Vitest): `citra` GET 200; kontrol peran & tampilan tanpa masuk lulus di `ExecutionView.test.tsx` |

## 13. Versi Dokumen, Ronde Tinjauan & Ekspor Laporan Pra-Tinjauan (tahap 6, spec #318)

Layar **Dokumen & Ronde** (`/runs/<id>/rounds`, di bilah sisi antara Draf Protokol dan Protokol IQ/OQ) menampilkan versi dokumen peralatan (`Aktif` / `Digantikan`), riwayat ronde tinjauan pra-protokol (`R1`, `R2`, …), diff lintas-ronde, penutupan ronde (*"Tutup ronde"*), serta penerbitan dan pengunduhan **Laporan Pra-Tinjauan (PDF)**.

**Menyalakan & persiapan dua ronde (`--stage two-rounds`).** Setelah `scripts/demo.py` menyalakan stack demo, jalankan `uv run python scripts/demo_seed.py --stage two-rounds` untuk menutup ronde R1 (`returned_for_revision`) dan membuka ronde R2 dengan dokumen revisi pada peralatan `TP-201`. Pastikan `typst` terpasang bila menerbitkan ekspor PDF baru.

**Dua run harus ada di `runs-demo/` sebelum seeding.** `demo.py` hanya membuat satu run. Buat run kedua dari korpus dan rekaman yang sama (replay, tanpa panggilan API):

`uv run traceq run <CORPUS_DIR>/t0-2026-06-01 --equipment TP-201 --out runs-demo --recordings recordings/haiku-r10`

Run kedua tidak perlu langkah impor terpisah: API membaca folder `runs-demo/` pada setiap permintaan `/runs`, dan `demo_seed.py` memanggil `POST /runs/<id>/import` untuk kedua run. Tanpa `--run-id` / `--second-run-id`, seed mengurutkan run menurut `created`: run yang lebih lama menjadi **R1** (dikembalikan untuk revisi), yang lebih baru menjadi **R2**. Bila hanya ada satu run, seed berhenti dengan pesan yang menunjuk ke perintah ini. Id eksplisit tetap dihormati (`--run-id` = R1, `--second-run-id` = R2).

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K49 | Versi Dokumen & status lintas-ronde | Masuk sebagai **Ayu Kartika Sari** (`ayu`) → buka `/runs/<id>/rounds` pada tab **Versi Dokumen** | Tabel menampilkan `doc_id`, `rev`, tipe, sumber, prefix `sha256` + tombol salin, status `Aktif` / `Digantikan`, badge perubahan lintas-ronde (`Baru di ronde ini`, `Revisi baru`, `Tidak berubah`), dan tautan pratinjau `Buka PDF` | ✅ (26 Nov, `main` 6eda552, build produksi, Keycloak OIDC, `ayu`): 15 dokumen, semua `Aktif` dan `Tidak berubah`, `Salin hash` dan `Buka PDF` ada |
| K50 | Ronde Tinjauan & Diff lintas-ronde | Buka tab **Ronde Tinjauan & Diff** pada ronde ke-2 (`R2`) | Daftar ronde `R2` (`Terbuka`) dan `R1` (`Dikembalikan`) beserta riwayat peristiwa tampil; panel **Diff Lintas-Ronde (vs R1)** menampilkan hitungan perubahan dokumen, temuan (`Selesai` / `Bertahan` / `Baru`), dan keputusan (`Terbawa` / `Terbuka ulang / berubah` / `Belum diputuskan`) | ✅ (26 Nov, run kedua dibuat dengan perintah §13, seed `two-rounds`): R2 `Terbuka` (run lebih baru) dan R1 `Dikembalikan` (run lebih lama); Diff Lintas-Ronde tampil |
| K51 | Penutupan ronde & penjagaan peran | Sebagai `ayu` (`qualification-decider`): klik **Tutup ronde** → pilih `Kembalikan untuk revisi vendor` tanpa alasan → simpan (harus ditolak 422 dengan isian tetap utuh); isi alasan → simpan. Sebagai `dewi` / `citra`: periksa tab **Ronde Tinjauan & Diff** | Modal menampilkan catatan ADR 0007 (*"Status tercatat, bukan Tanda Tangan Elektronik."*), dirty-form guard muncul bila menutup modal dengan isian belum disimpan, `ayu` dapat menutup ronde, sedangkan `dewi`/`citra` tidak melihat tombol **Tutup ronde** | ✅ sebagian (26 Nov): modal menampilkan catatan "Status tercatat, bukan Tanda Tangan Elektronik."; alasan kosong ditahan browser ("Please fill out this field."), bukan 422 dari API; dengan alasan, R2 menjadi `Dikembalikan`. Penjagaan peran `dewi`/`citra` belum dicoba |
| K52 | Ekspor & unduh Laporan Pra-Tinjauan (PDF) | Sebagai `ayu` atau `dewi` (`qualification-approver`): buka tab **Ekspor Laporan** → klik **Terbitkan Laporan Pra-Tinjauan (PDF)** → klik **Unduh PDF**. Sebagai `citra`: buka tab **Ekspor Laporan** | Ekspor baru muncul di **Riwayat Ekspor** dengan timestamp UTC, penerbit, prefix `snapshot_hash` & `pdf_sha256`, dan tombol **Unduh PDF** mengunduh berkas `application/pdf` melalui `/api/rounds/{roundId}/exports/{exportId}/pdf`; `citra` dapat mengunduh PDF tanpa melihat tombol terbitkan | ✅ sebagian (26 Nov): ekspor baru muncul di Riwayat Ekspor (R2, UTC, penerbit Ayu, prefix hash). **Unduh PDF belum dicoba**; peran `citra` belum dicoba |

## 14. Laporan Kualifikasi & Daftar Equipment (tahap 7, spec #325)

Layar **Laporan Kualifikasi** (`/runs/<id>/report`, di bilah sisi setelah Eksekusi & Deviasi) menampilkan kesimpulan teknis, hitungan per tahap (`IQ`, `OQ`, `IQ/OQ (Belum Dipisah)`, `Referensi Vendor`), silsilah uji ulang, ringkasan deviasi & Saksi, pemberitahuan "Tanda tangan (ADR 0007)" (kalimat lindung nilai sebelum ekspor, label dari backend sesudahnya), formulir penerbitan oleh penyetuju (`dewi`), serta riwayat ekspor PDF yang tidak dapat diubah. Layar **Daftar Equipment** (`/equipment`) menampilkan ringkasan siklus hidup per peralatan.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K53 | Atribut tahap (`IQ`/`OQ`) & `Wajib Saksi` pada Protokol Draft | Masuk sebagai `ayu` → buka `/runs/<id>/protocol` pada protokol Draft → buka laci baris langkah uji → pilih tahap (`IQ`/`OQ`) dan centang **Wajib konfirmasi Saksi** → **Simpan atribut** | Badge tahap dan **Wajib Saksi** muncul di tabel Protokol & Eksekusi; pada Eksekusi, baris wajib Saksi yang belum dikonfirmasi memunculkan pemblokir penyelesaian `unconfirmed_witness_rows` | |
| K54 | Pratinjau & penerbitan Laporan Kualifikasi (PDF) | Setelah Eksekusi selesai: klik CTA **Buka Laporan Kualifikasi** → masuk sebagai `dewi` (`qualification-approver`) → isi catatan kesimpulan & tanggal rekualifikasi berikutnya → klik **Terbitkan Laporan Kualifikasi (PDF)** → klik **Unduh PDF** | Kesimpulan teknis, hitungan IQ/OQ, dan catatan ADR 0007 tampil; revisi baru (`Rev 1`) muncul di **Riwayat Ekspor** dengan `snapshot_hash`, `pdf_sha256`, dan tautan unduh `/api/executions/{executionId}/qualification-reports/{exportId}/pdf` mengembalikan `application/pdf`; bila kesimpulan `not_qualified`, tanggal rekualifikasi tidak ditampilkan | |
| K55 | Daftar Equipment (`/equipment`) | Buka `/equipment` saat belum masuk, lalu masuk dan muat ulang `/equipment` | Saat belum masuk: tampil `Alert` masuk + tautan `/signin`. Setelah masuk: tabel menampilkan peralatan, ronde terakhir, protokol, eksekusi (+ deviasi terbuka), kesimpulan Laporan Kualifikasi dengan tautan langsung ke masing-masing `run_id`, dan tanggal rekualifikasi (atau `"Belum dijadwalkan"`) | |

## 15. Keycloak 26 OIDC & Tanda Tangan Elektronik (tahap 8, spec #333 / #317)

Mode penyedia identitas OIDC menggunakan Keycloak 26 (`quay.io/keycloak/keycloak:26.8.2`, profil `keycloak` di `compose.yaml`) dengan realm `traceq` (`compose/keycloak/traceq-realm.json`). Untuk menyalakan demo dengan Keycloak:

```sh
uv run python scripts/demo.py dist/t0-2026-06-01 --recordings recordings/haiku-r10 --idp keycloak
```

Pada terminal terpisah untuk UI web (`web/`):

```sh
TRACEQ_OIDC_CLIENT_ID=traceq-web TRACEQ_ISSUER_URL=http://127.0.0.1:8080/realms/traceq TRACEQ_ROLE_CLAIM=realm_access.roles TRACEQ_PUBLIC_URL=http://127.0.0.1:3000 npm run dev
```

Akun demo Keycloak (kata sandi seluruhnya `demo`): `ayu` & `bima` (`qualification-decider`, `qualification-executor`), `dewi` (`qualification-approver`), `eko` (`qualification-witness`), dan `citra` (hanya baca).

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K56 | Masuk OIDC PKCE & pemisahan tugas | Buka `/signin` → klik **Masuk dengan Keycloak** → masuk sebagai `ayu` (`demo`). Coba setujui protokol yang disiapkan `ayu` | `/signin` hanya menampilkan tombol Keycloak; `ayu` dapat mengajukan protokol (`prepared`) lewat `ElectronicSignatureDialog` setelah re-auth, tetapi persetujuan oleh `ayu` tetap ditolak `409` (SoD) | |
| K57 | Autentikasi ulang 60 detik & `SignatureBadge` pada 5 aksi penandatanganan | Masuk sebagai `dewi` (`demo`) → buka `/runs/<id>/report`, isi `conclusion_note` & tanggal rekualifikasi → klik **Terbitkan Laporan Kualifikasi (PDF)** → klik **Autentikasi Ulang dengan Keycloak** | Redirect ke `/api/auth/reauth` (`prompt=login&max_age=0&login_hint`), setelah memasukkan kata sandi `demo`, dialog terbuka kembali otomatis dengan `conclusion_note` & tanggal tetap terisi (`sessionStorage`), hitungan mundur 60 detik tampil dari `auth_time`, dan konfirmasi 1-klik menerbitkan laporan dengan `SignatureBadge` berlabel *Electronic Signature — designed for 21 CFR Part 11, CPOB Annex 7, and draft EU GMP Annex 11 (2025), not validated (ADR 0007)* | |
| K58 | Penutupan & pembekuan sumber daya | Setelah verifikasi: `Ctrl-C` pada `demo.py`, hentikan server web, dan jalankan `docker compose --profile keycloak stop keycloak` | Proses web/API berhenti dan kontainer Keycloak berhenti untuk membebaskan RAM | |

Kolom "Hasil" diisi oleh sesi utama setelah kasus dijalankan di browser pada stack yang dibangun dari cabang integrasi.
