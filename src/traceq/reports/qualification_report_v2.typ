#let data = json(bytes(sys.inputs.at("snapshot")))

#set page(
  paper: "a4",
  margin: (x: 18mm, y: 18mm),
  footer: context [
    #set text(font: "Libertinus Serif", size: 8pt, fill: luma(90))
    #grid(
      columns: (1fr, auto),
      [TraceQ — Laporan Kualifikasi (IQ/OQ) | #data.equipment | Revisi #data.revision_number],
      [Halaman #counter(page).display() dari #counter(page).final().first()],
    )
  ],
)

#set text(font: "Libertinus Serif", size: 9.5pt, fill: luma(25))
#set heading(numbering: "1.")
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)

#let conclusion_label(c) = {
  if c == "qualified" { "Memenuhi Syarat (Qualified)" }
  else if c == "qualified_with_deviations" { "Memenuhi Syarat dengan Deviasi (Qualified with Deviations)" }
  else if c == "not_qualified" { "Tidak Memenuhi Syarat (Not Qualified)" }
  else { c }
}

// Header
#block(
  width: 100%,
  inset: 10pt,
  fill: luma(246),
  stroke: 0.75pt + luma(190),
  radius: 3pt,
)[
  #text(size: 15pt, weight: "bold")[Laporan Kualifikasi Peralatan (Qualification Report)]
  #v(4pt)
  #grid(
    columns: (auto, 1fr, auto, 1fr),
    gutter: 6pt,
    [*Peralatan:*], [#data.equipment],
    [*ID Run:*], [`#data.run_id`],
    [*Protokol / Eksekusi:*], [Protokol \##data.protocol_id / Eksekusi \##data.execution_id],
    [*Revisi Laporan:*], [Revisi #data.revision_number],
    [*Kesimpulan Teknis:*], [*#conclusion_label(data.technical_conclusion)*],
    [*Dibuat (UTC):*], [`#data.generated_at`],
  )
]

#v(6pt)

// ADR 0007 Compliance & Signature Block
#block(
  width: 100%,
  inset: 8pt,
  fill: luma(250),
  stroke: (left: 2.5pt + luma(80), rest: 0.5pt + luma(210)),
)[
  #text(size: 8.5pt)[
    *Catatan Kepatuhan (ADR 0007):* \
    1. *Status Persetujuan:* #data.approval_note \
    2. *Hash Protokol Disetujui:* `#data.protocol_submission_hash` \
    3. *Hash Salinan Eksekusi:* `#data.execution_copy_hash`
    #if data.electronic_signature != none [
      \
      4. *Penandatangan:* #data.electronic_signature.signer_name (`#data.electronic_signature.signer_subject`) — #data.electronic_signature.signer_issuer \
      5. *Makna Tanda Tangan:* `#data.electronic_signature.signature_meaning` | *Auth Time (UTC):* `#data.electronic_signature.auth_time` | *Waktu Tanda Tangan (UTC):* `#data.electronic_signature.signed_at` \
      6. *Hash Konten Terikat:* `#data.electronic_signature.content_hash`
    ]
  ]
]

= Ringkasan Eksekusi & Persetujuan

#let c = data.counts

#table(
  columns: (2fr, 1fr, 1fr, 1fr),
  inset: 5pt,
  stroke: 0.5pt + luma(190),
  fill: (x, y) => if y == 0 { luma(236) },
  [*Tahap / Kategori*], [*Total*], [*Lulus (Pass)*], [*Gagal (Fail)*],
  [IQ (Installation Qualification)], [#c.iq_total], [#c.iq_passed], [#c.iq_failed],
  [OQ (Operational Qualification)], [#c.oq_total], [#c.oq_passed], [#c.oq_failed],
  [IQ/OQ (Belum Dipisah)], [#c.unsplit_total], [#c.unsplit_passed], [#c.unsplit_failed],
  [Vendor Reference], [#c.vendor_reference_count], [-], [-],
)

#v(4pt)
#grid(
  columns: (auto, 1fr),
  gutter: 6pt,
  [*Diselesaikan oleh:*], [#data.completer_name (`#data.completed_at`)],
  [*Disetujui oleh:*], [#data.approver_name (`#data.approver_subject`)],
  [*Total Deviasi:*], [#c.total_deviations],
  [*Catatan Kesimpulan:*], [#if data.conclusion_note != none { data.conclusion_note } else { "-" }],
  [*Rekualifikasi Berikutnya:*], [#if data.next_requalification_date != none { `#data.next_requalification_date` } else { "-" }],
)

= Rincian Persyaratan & Hasil Pengujian

#if data.rows.len() == 0 [
  _Tidak ada baris persyaratan pada eksekusi ini._
] else [
  #table(
    columns: (0.9fr, 2.2fr, 1fr, 0.7fr, 0.8fr, 1.2fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*ID*], [*Persyaratan*], [*Tahap*], [*Percobaan*], [*Hasil*], [*Saksi (Witness)*],
    ..data.rows.map(r => (
      [`#r.requirement`],
      [#r.text],
      [#r.stage_label],
      [#if r.kind == "vendor_reference" { "-" } else { [#r.attempt_count] }],
      [#if r.latest_verdict != none { r.latest_verdict } else { "-" }],
      [#if r.witness_names.len() > 0 { r.witness_names.join(", ") } else if r.witness_required { "Wajib" } else { "-" }],
    )).flatten(),
  )
]

= Ringkasan Deviasi

#if data.deviations.len() == 0 [
  _Tidak ada deviasi yang tercatat pada eksekusi ini._
] else [
  #table(
    columns: (0.6fr, 0.9fr, 1fr, 0.9fr, 0.8fr, 2.2fr),
    inset: 5pt,
    stroke: 0.5pt + luma(190),
    fill: (x, y) => if y == 0 { luma(236) },
    [*No.*], [*Persyaratan*], [*Penyebab*], [*Kelas*], [*Status*], [*Deskripsi*],
    ..data.deviations.map(d => (
      [\##d.deviation_number],
      [#if d.requirement != none { `#d.requirement` } else { "-" }],
      [#d.cause],
      [#if d.deviation_class != none { d.deviation_class } else { "-" }],
      [#d.status],
      [#d.description],
    )).flatten(),
  )
]
