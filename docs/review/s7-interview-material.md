# Bahan wawancara praktisi S7: putaran tinjauan draf end-to-end (`#394`)

- **Cakupan:** bahan singkat wawancara untuk sesi sesudah demo putaran penuh (`#375`, `#245`) dan pengukuran Mode Pabrik (`#442`).
- **Pelengkap:** agenda demo, aturan presenter, dan lembar catatan ada di [`docs/review/practitioner-session-pack.md`](practitioner-session-pack.md) (bagian 1–6); agenda Q16 yang masih terbuka (`D9`, `D13`, `D14`, `D15`, `D16`, `A10`, `F1–F6`) ada di [`docs/review/tp201-practitioner-q16.md`](tp201-practitioner-q16.md).
- **Label kejujuran:** semua angka pada dokumen ini berlabel **`dev only`** (data sintetis `TP-201`, kunci ditulis proyek sendiri; bukan klaim mutu). Tiga jenis temuan baru (`ac_outside_documented_capability`, `unit_error`, `outdated_reference`) berlabel **`not reviewed by a practitioner`** (*"Belum ditinjau praktisi"*). Jangan membacakan skor atau menyebutkan temuan mana yang benar sebelum praktisi menilai.

---

## 1. Daftar pertanyaan singkat wawancara

Tanyakan dengan bahasa praktisi dan catat kata demi kata di lembar catatan (`practitioner-session-pack.md` bagian 6.4).

### A. Dua pertanyaan terbuka ADR 0010 (validasi tesis)

1. **Penyebab putaran tinjau-dan-revisi (ADR 0010):** dalam proses tinjau-dan-revisi protokol kualifikasi, waktu paling banyak habis di mana — pada cacat dokumen yang bisa diperiksa sebelum tanda tangan, atau pada antrean menunggu tinjauan dan persetujuan?
2. **Keterlihatan AC tidak terjangkau di dokumen vendor (ADR 0010):** apakah *Acceptance Criterion* (AC) yang disetujui tetapi tidak terjangkau oleh mesin biasanya sudah terlihat di dokumen vendor (Datasheet, DQ, FAT, SAT) sebelum eksekusi, atau baru ketahuan saat uji?
   - Saat menilai temuan demo (`ac_outside_documented_capability`, `unit_error`, `outdated_reference`), minta praktisi menilai setiap temuan sebagai **berguna / tidak berguna / ragu** beserta alasannya.
   - Tanyakan batas jenis baru: apakah satuan yang setara (`2 jam` vs `120 menit`, `1,5 cm` vs `15 mm`) serta acuan tanpa revisi / standar eksternal memang bukan temuan? Catat bila hasil FAT/SAT dan kemampuan utilitas pabrik (udara tekan, HVAC) juga seharusnya masuk atau tetap di luar jangkauan Datasheet.

### B. Apakah pabrik menjalankan draf yang ditinjaunya? (ADR 0012 & `#245`)

3. **Jalur draf ke eksekusi (pertanyaan inti ADR 0012):** setelah draf protokol OQ ditinjau dan direvisi, apakah pabrik benar-benar mengeksekusi draf tersebut, atau menyusun protokol terpisah di dalam sistem sendiri?
4. **Cakupan dan bawaan (`[D]`) penyusunan Protocol dari draf:**
   - Apakah gabungan satu Protocol dengan Tahap `IQ` atau `OQ` per Langkah uji sesuai praktik, atau pabrik memisahkan Protocol IQ dan OQ?
   - Apakah wajar mewajibkan keputusan manusia per Langkah uji dan per AC (satu baris memakai satu sumber: draf untuk baris yang tercakup, rancangan TraceQ/manual untuk sisanya seperti IQ), serta mewajibkan **alasan tertulis** bila baris yang punya temuan disetujui diajukan tanpa perubahan?
   - Bagaimana aturan pemisahan tugas di pabrik: apakah penyetuju (QA/Approver) memang dilarang merangkap Penyusun, pemutus temuan, pemeta langkah, sekaligus pengunggah/pengimpor revisi draf yang dipakai (ADR 0012)?
   - Bila revisi draf baru masuk saat Protocol dari revisi lama masih terbuka, apakah menolak pengajuan/persetujuan salinan lama (`409`, harus Kembalikan lalu Tarik dan mulai ulang) sesuai kebiasaan pabrik?
   - Apakah kriteria batas eksklusif (`< 0,8 µm`) dan toleransi (`380 V ± 10 %`) wajib dinilai persis (dan teks bebas dibentuk dulu sebelum eksekusi)? Apakah ketiadaan **cetak/ekspor Protocol** untuk tanda tangan basah menjadi penghalang (`#245`)?

### C. Apakah pabrik menerima model cloud? (`#343`, `#442`, ADR 0004)

5. **Penerimaan model cloud vs wajib on-prem:** Mode Cloud mengirim teks dokumen ke penyedia LLM eksternal (hanya boleh dengan izin tertulis QA, IT, dan manajemen untuk dokumen nyata; ADR 0001). Apakah pabrik menerima pemrosesan cloud dengan syarat tertentu (klasifikasi data, de-identifikasi, pengawasan vendor SaaS, persetujuan tertulis), atau menolak penuh sehingga wajib berjalan lokal (*on-premise*, Mode Pabrik)?

**Data rujukan untuk pertanyaan C (`dev only`, [`docs/eval/mode-pabrik-spike.md`](../eval/mode-pabrik-spike.md)):**

Gunakan tabel ringkas ini hanya sebagai konteks fakta proyek bila praktisi menanyakan alternatif model lokal (*jangan* dibacakan sebagai klaim mutu lapangan; `n = 13` cacat, `6` Clean Traps, `2` Injection Probes pada `TP-201-OQ-draft` `0.2.0` rev 0):

| Ukuran / Aspek (`dev only`, `TP-201`) | Mode Cloud (`claude-haiku-5-5`, `haiku-r10` & `haiku-oq-draft-r8`) | Mode Pabrik (`#343a`, `aisingapore/Qwen-SEA-LION-v4.5-27B-IT`, hosted trial API) |
|---|---|---|
| **Verdict Rule 4 (Format)** | Selesai lengkap (Equipment & Draft rev 0) | **`tidak layak (format)`** — berhenti di Equipment; kedua run penuh yang diizinkan gagal pada jawaban tak terpakai (batas 2 kali ulang) |
| **Detail kegagalan format** | – | Run 1 (`json_schema`, suhu `0`, berpikir mati): panggilan `1–42` lulus (latensi min `1.904 s`, median `2.384 s`, maks `45.739 s`), lalu panggilan `#43` (`facts`, `FAT-TP201-M`) timeout `300 s` setelah 5 coba dan saat dilanjutkan gagal 3 kali dengan `finish_reason: 'length'` (`max_tokens=16000`). Run 2 (`tool`): panggilan `1–3` lulus, panggilan `#4` (`extract`) gagal 3 kali (`schema violation: 'None' is not of type 'number', 'null'`). |
| **Skor Equipment (`TP-201`)** | `fabrication.rate` `0.0`, `probes.fabrication_rate` `0.0`, `citations.verified_rate` `1.0`, `requirements.value_accuracy` `0.7632` (`29/38`) | Tidak terskor (berhenti pada format; Rule 1 & Rule 3 tidak tercapai) |
| **Skor Review Package (`TP-201-OQ-draft` 0.2.0 rev 0)** | `recall` `12/13` (`0.9231`: `ac_deviates_from_urs` `4/5`, `requirement_not_tested` `2/2`, `ac_outside_documented_capability` `2/2`, `unit_error` `2/2`, `outdated_reference` `2/2`), `wrong_findings` `0`, `clean_trap_rate` `6/6` (`1.0`), `injection_probe_pass_rate` `2/2` (`1.0`), `citations.verified_rate` `1.0` | Tidak dijalankan (Equipment berhenti pada format; Rule 2 tidak terskor) |
| **Token & biaya** | Equipment `523,136` in / `51,461` out (USD `0.039022`); Draft rev 0 live `19,670` in / `12,204` out (USD `0.004034`) | Parsial (`42` panggilan Run 1; `3` panggilan Run 2); biaya **`unknown (trial)`** (tabel harga `0`; biaya Anthropic `#343a` = USD `0`) |
| **Latensi** | `154.818 s` (Equipment) + `123.611 s` (Draft) via Batch API *(tidak sebanding per panggilan dengan API trial hosted)* | Run 1 parsial (`42` panggilan): min `1.904 s`, median `2.384 s`, maks `45.739 s` *(hosted trial API)* |

**Konsekuensi `#343a`:** dengan verdict **`tidak layak (format)`**, `#343b` (*self-hosting* GPU sewaan dengan prompt/skema yang sama) tetap **ditunda** dan **ADR 0004 tidak diamandemen**. Evaluasi model lokal lain atau penyesuaian prompt/skema merupakan keputusan baru di bawah `#343`.

---

## 2. Daftar kerja ulang bila bawaan (`[D]`) dibantah

Catat setiap jawaban praktisi yang membantah bawaan. Tidak ada perubahan yang diputuskan selama sesi berlangsung; setiap bantahan masuk ke daftar kerja ulang berikut:

| # | Bawaan (`[D]`) yang diuji | Jika praktisi membantah | Dampak ADR / klaim | Kerja ulang yang diperlukan |
|---|---|---|---|---|
| R1 | **ADR 0010 Q1:** putaran tinjau-dan-revisi disebabkan cacat yang bisa diperiksa | Putaran terutama disebabkan antrean tanda tangan / penjadwalan lintas bagian | Kedalaman bergeser ke alur tinjauan (*review workflow*); klaim utama ADR 0010 menyusut | Revisi ADR 0010 (`docs/adr/0010-pre-review-of-site-documents-is-the-claim.md`); prioritaskan pengingat/routing persetujuan di atas ekspansi aturan cacat baru |
| R2 | **ADR 0010 Q2 & jenis temuan baru:** `ac_outside_documented_capability`, `unit_error`, `outdated_reference` valid dan terlihat di dokumen paket | AC tak terjangkau tidak tampak di Datasheet/dokumen vendor, atau salah satu jenis/Clean Trap ditolak | Jenis yang ditolak tidak boleh diklaim (`#375`, ADR 0010 amandemen 26 Nov 2026) | Hapus atau ubah jenis terkait di aturan (`src/traceq/review/draft_rules.py`), manifes & kunci `0.2.0` (`world/tp201-oq-draft-0.2.0.yaml`), dan `baselines/TP-201-OQ-draft.json`; tarik angkanya |
| R3 | **ADR 0012 (26 Nov 2026):** pabrik mengeksekusi draf OQ yang ditinjaunya | Pabrik **tidak** mengeksekusi draf tersebut (selalu menyusun protokol terpisah) | ADR 0012 mewajibkan jalur draf-ke-Protocol **dihapus, bukan ditambal** | Hapus alur mulai Protocol dari draf di backend & UI (`#375` S4a/S4b); pertahankan Pre-review draf sebagai tinjauan terpisah dari Protocol TraceQ |
| R4 | **Struktur Protocol (`ADR 0012`):** satu Protocol gabungan IQ/OQ, tanpa cetak/ekspor (`#245`) | Pabrik mewajibkan Protocol IQ dan OQ terpisah, dan/atau wajib cetak kertas bertanda tangan basah | Perlu revisi `ADR 0012` dan lingkup di luar `#375` | Pisahkan pembuatan & penguncian Protocol per Tahap (`IQ` vs `OQ`), dan/atau tambah ekspor/cetak Protocol yang menyertakan salinan beku & daftar catatan |
| R5 | **Pemisahan tugas & alasan tertulis (`ADR 0012` 26–28 Nov):** penyetuju bukan Penyusun/pemutus/pemeta/pengunggah/pengimpor; temuan diterima tanpa suntingan wajib alasan tertulis | Peran QA di pabrik berbeda (mis. pengunggah admin boleh menyetujui, atau temuan diterima harus memblokir keras tanpa pengecualian) | Revisi `ADR 0012` (aturan `authors` / `uploader_approves`) | Ubah aturan persetujuan & validasi pengajuan di backend (`src/traceq/assembly/` & `src/traceq/proposals/`) serta tes v2 terkait |
| R6 | **Pin revisi (`409 pinned_behind`) & bentuk AC (`S4a3`):** salinan lama ditolak keras; teks bebas dibentuk manual sebelum eksekusi | Pabrik mengizinkan melanjutkan revisi lama dengan persetujuan/catatan, atau beban membentuk AC teks bebas terlalu berat (gladi 27 Nov: `18/35` baris draf tanpa bentuk terstruktur) | Penyesuaian kontrak status Protocol atau bentuk kriteria eksekusi | Ubah penolakan `409 pinned_behind` menjadi peringatan teraudit atau tambah bentuk evaluasi pass/fail terstruktur untuk langkah fungsional |
| R7 | **Mode Cloud vs lokal (`#343`, `#442`, ADR 0004):** Mode Cloud dapat diterima dengan syarat tertentu, atau Mode Pabrik belum aktif | Pabrik **menolak penuh** model cloud untuk dokumen nyata | Mode Cloud terblokir untuk pilot nyata (`docs/pilot-readiness.md` §3–4); karena `#343a` **`tidak layak (format)`**, `#343b` tidak langsung jalan | Buka keputusan pemilihan model lokal baru di `#343`: uji kandidat model *open-weights* lain pada aturan `#442`, atau jalankan eksperimen eval penyesuaian prompt/skema sebelum *self-hosting* |
| R8 | **Bawaan Q16 / RA (`tp201-practitioner-q16.md`):** `D9` (`-017`), `D13` (QA/Witness), `D14` (pemutus alat baru), `D15` (`-010`), `A10` (`-037`), `D16` (`TP-202`) | Praktisi mengubah kekritisan, syarat Witness, atau pengambil keputusan alat baru | Memperbarui `docs/pilot-readiness.md` (§1, §3, §6) dan set data berikutnya | Buat PR versi dataset baru (`world/` + `answer_key/` + `baselines/`) tanpa mengubah byte `0.1.1`/`0.2.0` yang beku |

---

## 3. Kesiapan penjadwalan `#245`

Bahan wawancara untuk putaran tinjauan draf (`#394`) dan hasil `#343a` (`#442`) sudah lengkap di `docs/review/`. Untuk menjalankan sesi setelah tanggal ditetapkan pada `#245`:

1. Ikuti urutan demo dan aturan presenter di [`docs/review/practitioner-session-pack.md`](practitioner-session-pack.md) (bagian 1–6) dan [`docs/demo-runbook.md`](../demo-runbook.md) (bagian 16).
2. Gunakan [`docs/review/tp201-practitioner-q16.md`](tp201-practitioner-q16.md) (bagian D) untuk menuntaskan pertanyaan `F1–F6`, `D13`, `D14`, `D9`, `D15`, dan `D16`.
3. Catat semua bantahan terhadap bawaan pada bagian 2 di atas sebagai dasar PR tindak lanjut sesudah sesi.
