# Runbook demo irisan 1 (Proposal Decisions)

Panduan menjalankan demo TraceQ irisan 1 untuk sesi praktisi: persiapan, alur end to end, kasus uji langkah demi langkah, hal yang diketahui salah, dan pemulihan. Perintah dasarnya ada di `README.md` (bagian "Demo"). Dokumen ini tidak mengulanginya kecuali bila urutannya penting.

**Status:** dilatih penuh pada 16–17 Nov 2026 (UTC) di laptop Windows 11 dengan korpus rilis 0.1.0 asli, rekaman `haiku-r7`, dan web UI di Chrome; semua 17 kasus lulus. Setelah restyle UI (#135), kasus yang menyentuh UI (K1–K9, K12–K15, bagian 4 dan "Cek siap") dijalankan ulang pada 17 Nov 2026 (UTC) di integrasi `feat/135-ui-restyle`; K10, K11, K16 dan K17 tidak berubah. Hasil per kasus ada di kolom "Hasil" pada bagian 5. Sesi praktisi diadakan sesudah freeze 25 Nov: runbook ini dijalankan ulang di atas rilis dan rekaman freeze.

## 1. Apa yang ditunjukkan demo, dan apa yang tidak

- **Ditunjukkan:** matriks ketertelusuran TP-201 (38 persyaratan) dengan bukti yang dikutip sampai halaman PDF, temuan pra-tinjauan (aturan dan AI), keputusan manusia (terima, ubah kelas, tolak) yang tercatat di Audit Trail, peran baca saja, dan skor eval dengan k/n.
- **Bukan panggilan LLM langsung:** run diputar ulang dari rekaman `recordings/haiku-r7` dan tidak mengirim apa pun ke API. "Biaya run 0,0422 USD" di layar eval adalah biaya panggilan yang direkam saat dijalankan live (`cost_usd`), bukan biaya demo (`live_cost_usd` = 0).
- **Data fiktif:** pabrik, vendor (Pressora Maschinenbau GmbH), mesin dan persona demo semuanya sintetis (ADR 0001).
- **AI hanya memberi saran:** setiap Proposal menunggu keputusan manusia (ADR 0002, ADR 0009).
- **Bukan kontrol akses sungguhan:** persona demo tidak memakai kata sandi. Keycloak dan tanda tangan elektronik datang belakangan (ADR 0005, ADR 0007).
- **Rekaman r7 dibuat sebelum label form lanjutan (#128):** tanda kritis dan transport-sensitive pada URS-TP201-013/020/028/035/036 dan 002/017 di layar masih versi korpus 0.1.0.

## 2. Persiapan (H-1)

| # | Langkah | Cek |
|---|---|---|
| P1 | Docker Desktop menyala | `docker info` menjawab |
| P2 | `uv sync` di root repo | tanpa error |
| P3 | Node 24 dan dependensi UI: `cd web && npm ci` | `npm ci` selesai. Tanpa langkah ini `npm run dev` gagal di checkout baru |
| P4 | Unduh dan cek korpus: `gh release download corpus-v0.1.0 --repo gedeyandi123/traceq --pattern 'corpus-0.1.0.tar.gz*'`, lalu `sha256sum -c corpus-0.1.0.tar.gz.sha256` dan `tar -xzf corpus-0.1.0.tar.gz` | `OK`; folder `t0-2026-06-01/` berisi `manifest.json`, `TP-201/`, `TP-202/` |
| P5 | Port 5432 (Postgres), 8000 (API), 9000 (issuer), 8001 (eval), 3000 (UI) bebas, atau 5432 dipakai Postgres TraceQ sendiri | `netstat -ano` |
| P6 | Build UI untuk produksi: `cd web && npm run build` | daftar route tampil (`/`, `/runs/[runId]`, …, `/signin`) |
| P7 | Jalankan seluruh bagian 3 dan 5 sekali sebagai gladi | semua kasus sesuai harapan |
| P8 | Matikan mode tidur laptop selama sesi | — |

Pakai **mode produksi** (`npm run build` lalu `npm start`), bukan `npm run dev`. Mode dev menampilkan ikon "N" Next.js di pojok kiri bawah, dan setiap halaman lambat saat pertama kali dikompilasi. Pada latihan, kunjungan pertama ke `/signin` belum tampil sebelum kompilasi selesai. Mode produksi melayani halaman dalam 14–90 ms dan tidak menampilkan ikon dev.

## 3. Menyalakan (hari H)

Jalankan dari root repo, masing-masing di terminal sendiri:

1. **Demo** (Postgres, reset database, replay, issuer, API, import):
   `uv run python scripts/demo.py <CORPUS_DIR>/t0-2026-06-01`
   Tambahkan `--no-compose` bila Postgres sudah jalan. Perintah ini tetap di foreground. Replay butuh sekitar 0,2 detik. Tunggu baris `demo: ready. …`; saran `npm run dev` di baris itu abaikan, pakai mode produksi (langkah 3).
2. **Eval (opsional, disarankan):** tanpa langkah ini halaman "Hasil evaluasi" menulis "Run ini belum dinilai". Ambil run id dari `runs-demo/`, lalu:
   - `uv run python -m traceq_eval world/tp201.yaml runs-demo/<run id>/submission.json --out runs-demo/<run id>` (sekitar 7 detik, keluar dengan `gates PASS`)
   - `uv run python -m traceq_eval.screen serve --runs runs-demo --port 8001`

   Penilaian sengaja tidak masuk `demo.py`: sistem tidak boleh membaca answer key (`tests/test_isolation.py`), dan penilaian adalah tugas harness.
3. **UI:** `cd web && npm start`, lalu buka http://localhost:3000.

**Cek siap (2 menit):** http://127.0.0.1:9000/demo/personas menampilkan 3 persona. Di `/`, daftar "Run analisis" berisi satu run TP-201 dengan mode "Putar ulang". Matriks menampilkan 38 baris dan baris "0/38 usulan sudah diputuskan"; buka "Jumlah keputusan" untuk melihat "Belum diputuskan 38".

## 4. Alur demo end to end (urutan cerita)

1. **Masuk** di `/signin` → "Masuk sebagai Ayu Kartika Sari" (dapat memutuskan). Header menampilkan "Masuk sebagai Ayu Kartika Sari (identitas demo)".
2. **Daftar run** `/` → klik run TP-201.
3. **Matriks ketertelusuran**: per persyaratan ada nilai yang disyaratkan, kelas cakupan, alasan, bukti (langkah FAT/SAT dengan nilai teramati dan data desain), dan kolom Keputusan. Di atas ada ringkasan cakupan (Konflik, Celah, Sebagian, dst.) dan baris "k/n usulan sudah diputuskan"; tabel "Jumlah keputusan" terlipat di bawahnya dan dibuka dengan klik.
4. **Buka sitasi**: buka lipatan bukti "Semua bukti dan kutipan" (▸ sebelum chip) pada URS-TP201-020, lalu klik "SAT-TP201 rev 0, hlm. 2" PDF terbuka di tab baru tepat di halaman 2 (SAT-05..07). Arahkan kursor ke link untuk melihat kutipan verbatimnya.
5. **Keputusan pada baris cakupan**: "Terima" (kasus K3), lalu "Ubah kelas" dengan alasan (K5). Baris cakupan tidak punya tombol "Tolak": usulan cakupan yang salah diperbaiki dengan mengubah kelasnya.
6. **Temuan pra-tinjauan** (tab Temuan pra-tinjauan): temuan aturan (deterministik, tanpa model) dan "Temuan AI (saran)" lengkap dengan model, hash prompt dan kutipan. Terima temuan yang benar dan tolak yang salah, dengan alasan (K6, K7).
7. **Yang tidak dimasukkan sistem** (tab): klaim yang dibuang pemeriksaan kutipan, beserta alasannya, dan kriteria penerimaan yang diserahkan ke manusia. Ini bukti bahwa sistem membuang klaim yang tidak bisa dikutip, bukan mengarangnya.
8. **Hasil evaluasi** (tab): k/n per ukuran untuk set pengembangan TP-201 dan gerbang fabrikasi (bagian 6).
9. **Peran baca saja**: "Keluar", lalu masuk sebagai Citra Maharani Putri. Keputusan Ayu terlihat, tetapi tidak ada tombol keputusan (K9).
10. **Reset**: hentikan demo (Ctrl-C) dan jalankan lagi. Database kosong lagi (K11), lalu **Keluar dan Masuk lagi** (bagian 7).

## 5. Kasus uji langkah demi langkah

Kolom "Hasil" berisi hasil latihan: 16–17 Nov, dan "17 Nov, UI baru" untuk kasus yang dijalankan ulang pada UI hasil restyle. ✅ = sesuai harapan dan sudah diamati. "Belum" = belum diuji pada latihan.

| ID | Kasus | Langkah | Hasil yang diharapkan | Hasil |
|---|---|---|---|---|
| K1 | Masuk sebagai pemutus | `/signin` → Ayu | Header "Masuk sebagai Ayu Kartika Sari (identitas demo)"; daftar run (tabel) tampil | ✅ (17 Nov, UI baru) |
| K2 | Sitasi membuka PDF asli di halaman yang benar | Buka lipatan bukti "Semua bukti dan kutipan" (▸ sebelum chip), lalu klik link sitasi mana pun; untuk halaman 2 pakai sitasi SAT-05/06/07 | PDF terbuka di halaman yang dikutip. Pada latihan, 113 link (93 di matriks, 20 di temuan; sebelum restyle 146 = 126 + 20) mengarah ke 11 PDF, semuanya HTTP 200 `application/pdf`, `target=_blank` dengan kutipan di `title` | ✅ (17 Nov, UI baru) |
| K3 | Terima usulan cakupan | URS-TP201-001 → "Terima" | Baris menjadi "Sudah diputuskan / Diterima oleh Ayu Kartika Sari, <tanggal> UTC"; baris "1/38"; di tabel "Jumlah keputusan" (dibuka): Belum diputuskan 37, Diterima 1 | ✅ (17 Nov, UI baru) |
| K4 | Ubah kelas tanpa alasan ditolak | URS-TP201-002 → buka "Ubah kelas…" → pilih "Celah" → "Ubah kelas" tanpa alasan | Browser menahan form ("Please fill out this field", pesan bawaan browser dalam bahasa Inggris) | ✅ (17 Nov, UI baru) |
| K5 | Ubah kelas dengan alasan | Sama, dengan alasan diisi | "Diubah ke Celah oleh Ayu Kartika Sari", alasan tampil miring; kolom Cakupan "Sebagian → Celah"; baris "2/38"; di tabel "Jumlah keputusan": Diubah 1 | ✅ (17 Nov, UI baru) |
| K6 | Tolak temuan yang salah | Temuan pra-tinjauan → "Tanda tangan atau tanggal tidak ada" (CAL-TP201-01) → buka "Tolak…" → isi alasan → "Tolak" | "Ditolak oleh …" dengan alasan; baris temuan "1/9"; Ditolak 1 di tabel "Jumlah keputusan" (Temuan pemeriksaan). Temuan ini false positive yang diketahui (#101) | ✅ (dilatih pada temuan "Protokol vendor belum disetujui", yang sebenarnya benar; untuk demo pakai false positive ini; 17 Nov, UI baru: dijalankan pada false positive ini) |
| K7 | Terima temuan AI yang benar | Temuan AI "Data tidak konsisten" (nomor seri RTP36-25-0417 vs -0471) → "Terima" (tombol terlihat) | Diterima; baris temuan "2/9"; Temuan AI Diterima 1 di tabel "Jumlah keputusan" | ✅ (17 Nov, UI baru) |
| K8 | Memutuskan ulang wajib beralasan, dan penolakan API tampil | Pada baris yang sudah diputuskan, buka "Putuskan ulang", kirim "Terima" lagi dengan alasan kosong atau hanya spasi | Alasan kosong: ditahan browser. Hanya spasi: muncul banner "Keputusan ditolak API. Alasan perubahan wajib …" (`?error=refused`); hitungan tetap 2/38 | ✅ (17 Nov, UI baru) |
| K9 | Peran baca saja | Keluar → masuk sebagai Citra → buka matriks | Keputusan Ayu terlihat; tidak ada tombol Terima, Ubah kelas atau Tolak, dan tidak ada lipatan "Ubah kelas…", "Tolak…" atau "Putuskan ulang"; muncul pemberitahuan "Hanya membaca: …" | ✅ (17 Nov, UI baru) |
| K10 | Server menolak penulisan tanpa hak | `POST /runs/<id>/proposals/<n>/decisions` ke API: dengan token Citra, lalu tanpa token | 403, lalu 401. Pembatasannya ada di API, bukan hanya di UI | ✅ |
| K11 | Audit Trail mencatat dan reset mengosongkan | Setelah K3–K6: `docker exec traceq-postgres-1 psql -U postgres -d traceq -c "select id, at, name, action, record_id, reason from audit_trail order by 1"`; lalu reset | Sebelum reset: 1 "run imported" ditambah 1 baris per keputusan. Setelah reset: hanya 1 "run imported" | ✅ |
| K12 | Hasil evaluasi | Jalankan langkah eval di bagian 3 → "Hasil evaluasi" | Gerbang fabrikasi lulus, nilai 26/38, kutipan 122/122, recall cacat 5/7, fabrikasi 0/179 dan 0/6 (sama dengan `recordings/haiku-r7/report-TP-201.json`); panel "Gerbang dan biaya" menulis "Gerbang fabrikasi: lulus" dan "Biaya run: 0,0422 USD" | ✅ (17 Nov, UI baru) |
| K13 | Halaman eval tanpa harness | Lewati langkah eval | Judul "Belum ada hasil evaluasi" dan teks "Run ini belum dinilai, atau API evaluasi tidak dapat dihubungi"; halaman lain tetap jalan | ✅ (17 Nov, UI baru) |
| K14 | Mode produksi | `npm run build` lalu `npm start`, lalu satu keputusan | Halaman dan PDF terlayani, keputusan tersimpan, tidak ada ikon dev | ✅ (17 Nov, UI baru) |
| K15 | Pemutus kedua | Masuk sebagai Bima, buka "Putuskan ulang" pada baris yang diputuskan Ayu dan putuskan (dengan alasan) | "Diterima oleh Bima Arya Nugraha" dengan alasan dan "Keputusan sebelumnya atas isi ini"; Audit Trail punya baris baru dengan `old_value` (keputusan Ayu), `new_value` dan `reason` | ✅ (17 Nov, UI baru) |
| K16 | Ctrl-C di terminal sungguhan | Ctrl-C pada `demo.py` | Issuer dan API berhenti ("Application shutdown complete"), exit 0, port 8000 dan 9000 bebas, Postgres tetap jalan | ✅ (17 Nov, CTRL_C_EVENT asli ke console demo) |
| K17 | Docker mati | Jalankan `demo.py` (tanpa `--no-compose`) saat Docker tidak bisa dihubungi | "could not start Postgres with Docker Compose (…); is Docker running?", exit 2 | ✅ (17 Nov, Docker disimulasikan tidak terjangkau) |

## 6. Yang diketahui salah di rekaman r7 (TP-201, set pengembangan)

Siapkan jawabannya sebelum praktisi menemukannya. Angka di bawah dari laporan scorer `recordings/haiku-r7/report-TP-201.json`.

- **Kelas cakupan benar 25/38**, nilai benar 26/38. Ukuran pertama tidak muncul di layar eval, yang hanya menampilkan akurasi nilai. Ke-13 kelas yang salah adalah alasan setiap usulan menunggu keputusan manusia.
  - Pola utama: usulan "Sebagian" dengan alasan "condition 2: date ambiguous" untuk langkah SAT yang sebenarnya *covered_by_vendor* (005, 019, 020, 021, 023).
  - Usulan "Celah" yang seharusnya "Sebagian" (014, 015, 016, 022).
  - Usulan "Hanya di lokasi" yang seharusnya "Celah" (025, 032).
  - 011 "Konflik" yang seharusnya *covered_by_vendor*.
  - 034 "Sebagian" yang seharusnya *covered_by_vendor*.
- **URS-TP201-005** menampilkan "Teramati: 204 kN" untuk nilai yang dicatat SAT sebagai 20,4 kN.
- **Recall cacat 5/7, presisi temuan 5/10.** Lima false positive:
  - tiga temuan aturan "Tanda tangan atau tanggal tidak ada" pada sertifikat kalibrasi (#101);
  - dua temuan AI "Kriteria penerimaan menyimpang dari URS" untuk FAT-M-02 dan FAT-M-09 (#100). Ini dibahas di sesi sebagai D9.

  Dua cacat yang terlewat sebagai temuan adalah koreksi GDP (S1) dan konflik desain (S6). Konflik tooling S6 tetap tampil sebagai kelas "Konflik" pada URS-TP201-008 di matriks.
- **Alasan dalam bahasa Inggris:** kolom Alasan, rincian temuan dan alasan pada "Yang tidak dimasukkan sistem" berbahasa Inggris di dalam UI berbahasa Indonesia. Tanyakan ke praktisi apakah ini mengganggu (bagian 9).
- **Waktu dalam UTC:** keputusan ditulis "… 16.32 UTC", bukan WIB.
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
- D9 (#100): apakah FAT-M-02 dan FAT-M-09 layak menjadi temuan?
