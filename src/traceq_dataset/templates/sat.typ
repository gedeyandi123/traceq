// SAT protocol and report: a vendor form in English with bilingual headings, filled in
// by hand at site. Printed text and handwritten entries both come from render.py via
// sys.inputs.data; this file only lays them out. hand() records each entry's box.

#import "common.typ": hand, ink, overwrite, place, rows-table, stamp
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 9.5pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2.8cm, bottom: 2cm),
  header: grid(
    columns: (1fr, auto),
    [*#d.vendor*],
    context [#d.doc_id · Rev. #d.rev · Page #counter(page).get().first() of #counter(page).final().first()],
  ),
)
#set table(stroke: 0.5pt, inset: 5pt)
#show heading: set block(above: 1.2em, below: 0.6em)
#show heading: set text(size: 11pt)
#set heading(numbering: "1.")

#let sig(name) = text(font: "Caveat", size: 15pt, fill: ink, skew(ax: -10deg, name))
#let signatures(rows) = rows-table(
  (2.8cm, 1fr, 2.6cm, 1fr, 2.4cm),
  ([Role / Peran], [Name / Nama], [Company], [Signature / Paraf], [Date / Tanggal]),
  rows.map(a => (
    [#a.role],
    hand(a.key + ".name", a.name),
    [#a.company],
    sig(a.signature),
    hand(a.key + ".date", a.date),
  )),
)

#align(center, text(size: 14pt, weight: "bold")[Site Acceptance Test – Protocol and Report])
#align(center, text(size: 11pt)[Uji Penerimaan di Lokasi (SAT)])
#v(0.5em)

#table(
  columns: (4cm, 1fr),
  [Document no. / No. dokumen], [#d.doc_id],
  [Revision / Revisi], [#d.rev],
  [Issue date], [#d.issued_on],
  [Equipment / Peralatan], [#d.equipment],
  [Serial no. / No. seri], hand("serial", d.serial),
  [Manufacturer], [#d.vendor],
)

= Purpose / Tujuan
#d.purpose

= Approval before execution / Persetujuan sebelum pelaksanaan
#signatures(d.approvals)

= Test instruments / Alat ukur
#rows-table(
  (2cm, 1fr, 3cm, 3cm, 2.6cm),
  ([ID], [Instrument], [Serial no.], [Calibration cert.], [Cal. due / Berlaku s.d.]),
  d.instruments.map(i => (
    hand(i.key + ".id", i.id),
    [#i.name],
    hand(i.key + ".serial", i.serial),
    hand(i.key + ".certificate", i.certificate),
    hand(i.key + ".due", i.due),
  )),
)

= Test results / Hasil uji
Results are entered by hand at site. Pass/Fail is recorded against the acceptance criterion.
#rows-table(
  (1.3cm, 1fr, 2.5cm, 1.9cm, 3.4cm, 1.4cm),
  ([Step], [Test], [Acceptance criterion], [Instr.], [Result / Hasil], [P/F]),
  d.steps.map(s => (
    [#s.step],
    [#s.description],
    [#s.acceptance#place(s.step + ".acceptance")],
    if s.instruments.len() == 0 [] else { hand(s.step + ".instruments", s.instruments.join(linebreak())) },
    if "original" in s {
      overwrite(s.step + ".observed", s.original, s.observed)
    } else { hand(s.step + ".observed", s.observed) },
    hand(s.step + ".result", s.result),
  )),
)

= Deviations / Penyimpangan
#hand("deviations", d.deviations)

= Execution / Pelaksanaan
#signatures(d.execution)
#v(0.4em)
#align(right, stamp(d.stamp))
