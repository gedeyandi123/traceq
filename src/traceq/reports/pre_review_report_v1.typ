#let data = json(bytes(sys.inputs.at("snapshot")))

#set page(
  paper: "a4",
  margin: (x: 18mm, y: 18mm),
  footer: context [
    #set text(font: "Libertinus Serif", size: 8pt, fill: luma(90))
    #grid(
      columns: (1fr, auto),
      [TraceQ — Laporan Pra-Tinjauan (Pre-Review) | #data.equipment | Putaran #data.round_number],
      [Halaman #counter(page).display() dari #counter(page).final().first()],
    )
  ],
)

#set text(font: "Libertinus Serif", size: 9.5pt, fill: luma(25))
#set heading(numbering: "1.")
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)

#let status_label(s) = {
  if s == "open" { "Terbuka" }
  else if s == "returned_for_revision" { "Dikembalikan untuk Revisi" }
  else if s == "ready_for_protocol" { "Siap untuk Protokol" }
  else { s }
}

#let badge(label) = box(
  inset: (x: 5pt, y: 2pt),
  radius: 2pt,
  fill: luma(238),
  stroke: 0.5pt + luma(180),
  text(size: 8pt, weight: "bold", label),
)

// Header
#block(
  width: 100%,
  inset: 10pt,
  fill: luma(246),
  stroke: 0.75pt + luma(190),
  radius: 3pt,
)[
  #text(size: 15pt, weight: "bold")[Laporan Pra-Tinjauan Kualifikasi (Pre-Review)]
  #v(4pt)
  #grid(
    columns: (auto, 1fr, auto, 1fr),
    gutter: 6pt,
    [*Peralatan:*], [#data.equipment],
    [*ID Run:*], [`#data.run_id`],
    [*Putaran:*], [Putaran #data.round_number (#status_label(data.round_status))],
    [*Dibuat (UTC):*], [`#data.generated_at`],
  )
]

#v(6pt)

// ADR 0002 & ADR 0007 Disclaimers
#block(
  width: 100%,
  inset: 8pt,
  fill: luma(250),
  stroke: (left: 2.5pt + luma(80), rest: 0.5pt + luma(210)),
)[
  #text(size: 8.5pt)[
    *Catatan Kepatuhan & Batasan Sistem (ADR 0002 & ADR 0007):* \
    1. *Temuan AI bersifat saran (advisori):* Seluruh temuan lapisan AI memerlukan verifikasi dan keputusan manusia sebelum tindakan kualifikasi diambil. \
    2. *Aturan deterministik & kutipan terverifikasi:* Pemeriksaan cakupan (coverage), aturan periksa (check/rule), dan kelengkapan URS dijalankan secara deterministik dengan kutipan halaman sumber. \
    3. *Jejak Audit Imutabel:* Laporan ini dirender dari cuplikan data (*snapshot*) yang tersimpan secara *append-only* dengan stempel waktu basis data UTC.
  ]
]

= Ringkasan Cakupan & Temuan

#let cov = data.coverage
#let fsum = data.findings_summary

#table(
  columns: (2fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  stroke: 0.5pt + luma(190),
  fill: (x, y) => if y == 0 { luma(236) },
  [*Kategori*], [*Diputuskan (k/n)*], [*Diterima*], [*Diubah*], [*Ditolak*], [*Berubah*], [*Belum Diputuskan*],
  [Cakupan Persyaratan (Coverage)],
  [#cov.decided / #cov.total],
  [#cov.accepted],
  [#cov.edited],
  [#cov.rejected],
  [#cov.changed],
  [#cov.undecided],
  [Temuan Pra-Tinjauan (Check + AI + Draft)],
  [#fsum.decided / #fsum.total],
  [#fsum.accepted],
  [#fsum.edited],
  [#fsum.rejected],
  [#fsum.changed],
  [#fsum.undecided],
)

= Versi Dokumen dalam Putaran Ini

#if data.documents.len() == 0 [
  _Tidak ada dokumen tercatat pada putaran ini._
] else [
  #table(
    columns: (1.5fr, 0.6fr, 1fr, 1.3fr, 2.5fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*ID Dokumen*], [*Rev*], [*Tipe*], [*Sumber*], [*SHA-256*],
    ..data.documents.map(d => (
      [`#d.doc_id`],
      [#d.rev],
      [#if d.doc_type != none { d.doc_type } else { "-" }],
      [#d.source],
      [`#d.sha256`],
    )).flatten(),
  )
]

#let render_findings_section(title, items) = {
  heading(level: 2, title)
  if items.len() == 0 {
    [_Tidak ada temuan pada kategori ini._]
  } else {
    for f in items {
      block(
        width: 100%,
        inset: 6pt,
        below: 6pt,
        stroke: 0.5pt + luma(200),
        radius: 2pt,
      )[
        #grid(
          columns: (1fr, auto),
          [*\# #(f.position + 1) — #f.finding_type* #if f.doc != none [(`#f.doc`)]],
          badge(if f.decision != none { f.decision } else { f.state }),
        )
        #v(3pt)
        #f.detail
        #if f.citations.len() > 0 [
          \ #text(size: 8pt, fill: luma(80))[Kutipan: #f.citations.join("; ")]
        ]
        #if f.reason != none [
          \ #text(size: 8.5pt)[*Alasan Perubahan (RfC):* #f.reason]
        ]
        #if f.decided_by != none [
          \ #text(size: 8pt, fill: luma(80))[Diputuskan oleh #f.decided_by]
        ]
      ]
    }
  }
}

= Rincian Temuan & Keputusan

#render_findings_section("Temuan Aturan Deterministik (Check)", data.check_findings)
#render_findings_section("Temuan AI (Advisori — ADR 0002)", data.ai_findings)
#render_findings_section("Temuan Draf Protokol (Review Package)", data.draft_findings)

= Dokumen yang Hilang (Missing Documents)

#if data.missing_documents.len() == 0 [
  _Tidak ada dokumen wajib VMP yang hilang dari korpus._
] else [
  #table(
    columns: (1.5fr, 1.2fr, 0.8fr, 2.5fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*ID Dokumen*], [*Tipe*], [*Tahap*], [*Kutipan VMP*],
    ..data.missing_documents.map(m => (
      [`#m.doc_id`],
      [#m.doc_type],
      [#m.stage],
      [#m.citation],
    )).flatten(),
  )
]

= Klaim yang Dibatalkan (Dropped Claims)

#if data.dropped_claims.len() == 0 [
  _Tidak ada klaim yang dibatalkan oleh pemeriksa kutipan._
] else [
  #table(
    columns: (1fr, 1.5fr, 3fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*Jenis Klaim*], [*ID*], [*Alasan*],
    ..data.dropped_claims.map(c => (
      [#c.claim],
      [`#c.id`],
      [#c.reason],
    )).flatten(),
  )
]

= Ringkasan Kelengkapan URS (URS Completeness)

#if data.completeness.len() == 0 [
  _Pemeriksaan kelengkapan URS tidak tersedia untuk run ini._
] else [
  #table(
    columns: (1.8fr, 0.6fr, 1.2fr, 0.9fr, 1fr, 1.2fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*Dokumen URS*], [*Rev*], [*Status Nomor*], [*Ditemukan*], [*Terlewat*], [*Teks Tanpa Kutipan*],
    ..data.completeness.map(u => (
      [`#u.doc`],
      [#u.rev],
      [#u.numbers],
      [#u.found],
      [#u.missed_count],
      [#u.unquoted_count],
    )).flatten(),
  )
]

#if data.round_diff != none [
  #let diff = data.round_diff
  = Perbandingan Antar Putaran (vs Putaran #diff.previous_round_number)
  Run sebelumnya: `#diff.previous_run_id`
  - *Dokumen Ditambahkan:* #if diff.documents_added.len() == 0 [tidak ada] else [#diff.documents_added.join(", ")]
  - *Dokumen Direvisi:* #if diff.documents_revised.len() == 0 [tidak ada] else [#diff.documents_revised.join(", ")]
  - *Dokumen Tetap:* #if diff.documents_unchanged.len() == 0 [tidak ada] else [#diff.documents_unchanged.join(", ")]
  - *Dokumen Dihapus:* #if diff.documents_removed.len() == 0 [tidak ada] else [#diff.documents_removed.join(", ")]
  - *Temuan:* #diff.findings_resolved selesai, #diff.findings_persisted bertahan, #diff.findings_new baru
  - *Keputusan:* #diff.decisions_carried_forward terbawa, #diff.decisions_changed berubah, #diff.decisions_undecided belum diputuskan
]
