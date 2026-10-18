// Listener-panel manifest (PRD G1 human-likeness test). Loaded with a <script> tag so the
// panel works straight from disk (file://) with no server.
//
// PLACEHOLDERS: none of these clips exist yet. Each pair should be the same ~30 s scenario in
// the same language: one recorded human telecaller ("human") and one Mitra call ("mitra"),
// both at phone quality (8 kHz mono, loudness-matched). Put the files next to this manifest,
// keep `id`s stable, and bump `id` at the top whenever the clip set changes.
//
// Never show `source` to listeners. The page randomises A/B order and trial order itself.
window.PANEL_MANIFEST = {
  id: "g1-pilot-placeholder",
  title: "Which caller is the AI?",
  pairs: [
    { id: "te-clinic-fee", language: "te", scenario: "Clinic fee + booking",
      clips: [{ source: "human", src: "clips/te-clinic-fee-human.wav" },
              { source: "mitra", src: "clips/te-clinic-fee-mitra.wav" }] },
    { id: "te-realestate-visit", language: "te", scenario: "Site-visit booking",
      clips: [{ source: "human", src: "clips/te-realestate-visit-human.wav" },
              { source: "mitra", src: "clips/te-realestate-visit-mitra.wav" }] },
    { id: "hi-clinic-reschedule", language: "hi", scenario: "Reschedule appointment",
      clips: [{ source: "human", src: "clips/hi-clinic-reschedule-human.wav" },
              { source: "mitra", src: "clips/hi-clinic-reschedule-mitra.wav" }] },
    { id: "en-realestate-price", language: "en", scenario: "Price question",
      clips: [{ source: "human", src: "clips/en-realestate-price-human.wav" },
              { source: "mitra", src: "clips/en-realestate-price-mitra.wav" }] },
    { id: "te-en-clinic-report", language: "te-en", scenario: "Report status (Tenglish)",
      clips: [{ source: "human", src: "clips/te-en-clinic-report-human.wav" },
              { source: "mitra", src: "clips/te-en-clinic-report-mitra.wav" }] },
    { id: "hi-en-realestate-qualify", language: "hi-en", scenario: "Budget qualification (Hinglish)",
      clips: [{ source: "human", src: "clips/hi-en-realestate-qualify-human.wav" },
              { source: "mitra", src: "clips/hi-en-realestate-qualify-mitra.wav" }] }
  ]
};
