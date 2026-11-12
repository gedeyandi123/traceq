// Design qualification report (Indonesian, born-digital): the site's review of the vendor
// datasheet against the URS. All text comes from render.py; this file only lays it out.

#import "common.typ": rows-table
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: "Site")
#set text(lang: "id", size: 9pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2.6cm, bottom: 2cm),
  header: grid(
    columns: (1fr, auto),
    [*#d.title_short*],
    context [#d.doc_id · Rev. #d.rev · Halaman #counter(page).get().first() dari #counter(page).final().first()],
  ),
)
#set table(stroke: 0.5pt, inset: 4pt)
#show heading: set block(above: 1.1em, below: 0.6em)
#show heading: set text(size: 10.5pt)
#set heading(numbering: "1.")

#align(center, text(size: 14pt, weight: "bold")[#d.title])
#v(0.5em)
#table(
  columns: (4cm, 1fr),
  [No. dokumen], [#d.doc_id],
  [Revisi], [#d.rev],
  [Tanggal terbit], [#d.issued_on],
  [Peralatan], [#d.equipment],
)

= Tujuan
#d.purpose

= Dokumen yang ditinjau
#rows-table((3.6cm, 1.4cm, 1fr), ([No. dokumen], [Revisi], [Judul]), d.reviewed.map(r => ([#r.doc], [#r.rev], [#r.title])))

= Hasil tinjauan
#rows-table(
  (2.6cm, 1fr, 4.6cm, 2.8cm),
  ([No. SKP], [Persyaratan], [Data desain (#d.datasheet)], [Hasil]),
  d.rows.map(r => ([#r.id], [#r.text], [#r.design], [#r.result])),
)

= Butir terbuka
#if d.open.len() == 0 [Tidak ada.] else { enum(..d.open.map(o => [#o])) }

= Kesimpulan
#d.conclusion

= Persetujuan
#rows-table(
  (3cm, 1fr, 1fr, 2.4cm),
  ([Peran], [Nama], [Tanda tangan], [Tanggal]),
  d.signatures.map(s => ([#s.role], [#s.name], [#emph[#s.signature]], [#s.date])),
)
