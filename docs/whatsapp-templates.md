# WhatsApp message templates (Meta Cloud API, direct)

Drafts for submission in **WhatsApp Manager → Message templates**. Status: **draft, 3 Nov 2026**. The Telugu and Hindi need a native-speaker review before submission (Telugu: founder).

## Why we need these

WhatsApp allows free-form messages only within **24 hours of the person's last message to us**. Anything outside that window (a heads-up before a call, a morning report, a reminder) must use an approved template. Inside the window Mitra sends normal text.

## Rules followed

- **Category: Utility** for every template. Each one is about something the person asked for or already has (an enquiry, a booking, a payment, their own business). None of them carry offers. If Meta reclassifies one as Marketing, it still works but costs more and needs marketing consent, so reword it instead of accepting the change.
- **Named variables** (`{{name}}`). They match the field names the code sends. Meta needs a sample value for each; the samples are in the tables.
- **Telugu `{{name}}` carries the honorific.** The code sends "Ravi గారు" (sample for Meta: `Ravi గారు`), so when the name is unknown it sends "అండి" and the greeting reads "నమస్కారం అండి," (pending founder review). Hindi falls back to "जी" ("नमस्ते जी,"), English to "there".
- **App links** ("Open in Mitra", "Open report") are `https://app.viduronai.in/{{1}}` (founder decision, 3 Nov 2026: Viduron's own domain, which also matches Meta business verification). The code reads it from one setting (`MITRA_APP_BASE_URL`); if Mitra moves to its own domain later, change the setting and re-submit these two templates.
- A variable can't contain a line break or tab and can't be the first or last thing in the body. The code must flatten text before filling a variable (see "Code changes" below).
- **Languages:** `en`, `hi`, `te`. Each language is a separate submission under the same template name.
- Business names go in a variable (`{{business}}`), so one approved template works for every Mitra customer while we send from Mitra's number. When a business connects its own WhatsApp number later (Embedded Signup), the same templates are copied to its account.

---

## A. Messages to customers

### 1. `call_heads_up`: before Mitra calls a new lead (NUM-07)
Quick-reply buttons: **Call me later** · **Don't call me**

| | Body |
|---|---|
| en | Hi {{name}}, this is {{business}}. We'll call you in about {{minutes}} minutes about your enquiry. |
| hi | नमस्ते {{name}}, हम {{business}} से हैं। आपकी enquiry के बारे में हम लगभग {{minutes}} मिनट में आपको call करेंगे। |
| te | నమస్కారం {{name}}, మేము {{business}} నుంచి. మీ enquiry గురించి సుమారు {{minutes}} నిమిషాల్లో మీకు call చేస్తాం. |

Samples: name = Ravi · business = Sunrise Homes · minutes = 2

### 2. `missed_call_callback`: missed-call number, outside calling hours (CALL-20)
| | Body |
|---|---|
| en | Thanks for calling {{business}}. We'll call you back at {{time}}. |
| hi | नमस्ते! {{business}} को call करने के लिए धन्यवाद। हम आपको {{time}} बजे call करेंगे। |
| te | నమస్కారం! {{business}}కి call చేసినందుకు ధన్యవాదాలు. మేము మీకు {{time}}కి తిరిగి call చేస్తాం. |

Samples: business = Sunrise Clinic · time = 9:00 am

### 3. `booking_confirmation`: after a booking on a call (ACT-02)
Buttons: quick reply **Change time** · URL **Get directions** (`https://maps.app.goo.gl/{{1}}`; the code sends the place link suffix)

| | Body |
|---|---|
| en | Hi {{name}}, your appointment at {{business}} is confirmed for {{when}}. |
| hi | नमस्ते {{name}}, {{business}} में आपकी appointment {{when}} के लिए confirm हो गई है। |
| te | నమస్కారం {{name}}, {{business}}లో మీ appointment {{when}}కి confirm అయింది. |

Samples: name = Ravi · business = Sunrise Clinic · when = Tue 21 Oct, 6:15 pm

### 4. `appointment_reminder`: routine before the visit (AUTO-03)
Quick-reply buttons: **I'll come** · **Change time**

| | Body |
|---|---|
| en | Reminder: your appointment at {{business}} is on {{when}}. |
| hi | याद दिला रहे हैं: {{business}} में आपकी appointment {{when}} को है। |
| te | గుర్తు చేస్తున్నాం: {{business}}లో మీ appointment {{when}}న ఉంది. |

Samples: business = Sunrise Clinic · when = tomorrow, 6:15 pm

### 5. `share_document`: brochure, price list, report (ACT-02)
Header: **Document** (the PDF). Body:

| | Body |
|---|---|
| en | Here is the {{document}} from {{business}} that you asked for. |
| hi | आपने जो {{document}} माँगा था, वह {{business}} की ओर से यहाँ है। |
| te | మీరు అడిగిన {{document}} ఇదిగో, {{business}} నుంచి. |

Samples: document = price list · business = Sunrise Homes

### 6. `share_location`: directions (ACT-02)
Button: URL **Open map** (`https://maps.app.goo.gl/{{1}}`)

| | Body |
|---|---|
| en | You can find {{business}} at {{address}}. Tap below for directions. |
| hi | पता: {{business}}, {{address}}. रास्ते के लिए नीचे tap करें। |
| te | అడ్రస్: {{business}}, {{address}}. దారి కోసం కింద tap చేయండి. |

Samples: business = Sunrise Clinic · address = Road No. 12, Banjara Hills, Hyderabad

### 7. `enquiry_follow_up`: follow-up on the person's own enquiry (ACT-07, hand-offs)
Quick-reply buttons: **Call me** · **Not now**

| | Body |
|---|---|
| en | Hi {{name}}, {{business}} here, following up on your enquiry about {{topic}}. Reply here or tap below and we'll call you. |
| hi | नमस्ते {{name}}, {{business}} से बात कर रहे हैं, {{topic}} के बारे में आपकी enquiry पर follow-up। यहाँ reply करें या नीचे tap करें, हम call करेंगे। |
| te | నమస్కారం {{name}}, {{business}} నుంచి, {{topic}} గురించి మీ enquiry మీద follow-up. ఇక్కడ reply చేయండి లేదా కింద tap చేయండి, మేము call చేస్తాం. |

Samples: name = Ravi · business = Sunrise Homes · topic = 2BHK in Kondapur

### 8. `payment_link`: collect a payment (ACT-05)
Button: URL **Pay now** (`https://rzp.io/{{1}}`; the code sends the link id)

| | Body |
|---|---|
| en | Hi {{name}}, here is your payment link from {{business}} for {{purpose}}: ₹{{amount}}. You can pay by UPI or card. |
| hi | नमस्ते {{name}}, {{business}} की ओर से {{purpose}} के लिए आपका payment link: ₹{{amount}}. UPI या card से pay कर सकते हैं। |
| te | నమస్కారం {{name}}, {{purpose}} కోసం {{business}} నుంచి మీ payment link: ₹{{amount}}. UPI లేదా card తో pay చేయవచ్చు. |

Samples: name = Ravi · business = Sunrise Clinic · purpose = consultation · amount = 500

### 9. `payment_reminder`: unpaid by the due date (ACT-11)
Button: URL **Pay now** · quick reply **Already paid**

| | Body |
|---|---|
| en | A gentle reminder from {{business}}: ₹{{amount}} for {{purpose}} is due on {{due}}. |
| hi | एक reminder, {{business}} की ओर से: {{purpose}} के ₹{{amount}} की due date {{due}} है। |
| te | ఒక reminder, {{business}} నుంచి: {{purpose}} కోసం ₹{{amount}} చెల్లించాల్సిన తేదీ {{due}}. |

Samples: business = Sunrise Clinic · amount = 500 · purpose = consultation · due = 5 Nov

### 10. `payment_received`: thank-you after auto-matching (ACT-11)
| | Body |
|---|---|
| en | Thank you, {{name}}. {{business}} has received ₹{{amount}} for {{purpose}}. |
| hi | धन्यवाद {{name}}। {{business}} को {{purpose}} के लिए ₹{{amount}} मिल गए हैं। |
| te | ధన్యవాదాలు {{name}}. {{purpose}} కోసం ₹{{amount}} {{business}}కి అందాయి. |

Samples: name = Ravi · business = Sunrise Clinic · amount = 500 · purpose = consultation

### 10a. `payment_upi_request`: UPI-only collection, no payment gateway (ACT-05)
No buttons (a UPI ID can't be a link button). The customer replies **PAID**; Mitra flags it for the owner to confirm, it never marks a request paid by itself.

| | Body |
|---|---|
| en | Hi {{name}}, {{business}} has requested ₹{{amount}} for {{purpose}}. Please pay to UPI ID {{upi_id}}. Reply PAID once done. |
| hi | नमस्ते {{name}}, {{business}} ने {{purpose}} के लिए ₹{{amount}} का request भेजा है। कृपया UPI ID {{upi_id}} पर pay करें। Pay करने के बाद PAID reply करें। |
| te | నమస్కారం {{name}}, {{purpose}} కోసం {{business}} ₹{{amount}} request చేసింది. దయచేసి UPI ID {{upi_id}}కి pay చేయండి. Pay చేశాక PAID అని reply చేయండి. |

Samples: name = Ravi · business = Sunrise Clinic · amount = 500 · purpose = consultation · upi_id = sunriseclinic@okicici

---

## B. Messages to owners, managers and staff

### 11. `owner_alert`: hot lead, upset customer, VIP, urgent, payment failed, campaign paused (MGR-05, TEAM-05)
Button: URL **Open in Mitra** (`https://app.viduronai.in/{{1}}`; the code sends the path)

| | Body |
|---|---|
| en | Alert: {{title}} at {{business}}. {{detail}} Open Mitra for details. |
| hi | Alert: {{business}} में {{title}}। {{detail}} पूरी जानकारी Mitra में देखें। |
| te | Alert: {{business}}లో {{title}}. {{detail}} పూర్తి వివరాలు Mitraలో చూడండి. |

Samples: title = Hot lead · business = Sunrise Homes · detail = Ravi is interested in a 2BHK and wants a site visit on Saturday.

### 12. `daily_report`: morning summary (MGR-01)
Button: URL **Open report** (`https://app.viduronai.in/{{1}}`; the code sends `?from=whatsapp`)

| | Body |
|---|---|
| en | Good morning! Yesterday at {{business}}: {{calls}} calls, {{booked}} booked, {{attention}} need your attention. |
| hi | सुप्रभात! कल {{business}} में: {{calls}} calls, {{booked}} booking, {{attention}} पर आपका ध्यान चाहिए। |
| te | శుభోదయం! నిన్న {{business}}లో: {{calls}} calls, {{booked}} bookings, {{attention}} విషయాలు మీరు చూడాలి. |

Samples: business = Sunrise Clinic · calls = 42 · booked = 11 · attention = 3

### 13. `approval_request`: "Ask me first" (APPR-02)
Quick-reply buttons: **Approve** · **Decline** (the code sets each button's payload to the approval id and version)

| | Body |
|---|---|
| en | Approval needed at {{business}}: {{employee}} needs your OK. {{summary}} Tap a button below. |
| hi | मंज़ूरी चाहिए, {{business}}: {{employee}} को आपकी मंज़ूरी चाहिए। {{summary}} नीचे एक button tap करें। |
| te | Approval కావాలి, {{business}}: {{employee}}కి మీ approval కావాలి. {{summary}} కింద ఒక button tap చేయండి. |

Samples: business = Sunrise Homes · employee = Priya · summary = Call 120 people from the October expo list.

### 14. `staff_handoff`: brief or call-back card for a staff member (TEAM-04, CALL-19)
Quick-reply button: **Done**

| | Body |
|---|---|
| en | Task from {{business}}: please {{action}} {{customer}}. {{brief}} Tap Done when finished. |
| hi | नया काम, {{business}} से: कृपया {{customer}} को {{action}}। {{brief}} हो जाने पर Done tap करें। |
| te | కొత్త పని, {{business}} నుంచి: దయచేసి {{customer}}కి {{action}}. {{brief}} అయ్యాక Done tap చేయండి. |

Samples: business = Sunrise Clinic · action = call back · customer = Ravi (…5678) · brief = Wants an evening slot, asked about parking.

The `action` values must be translated per language by the code (en "call back", hi "call करें", te "call చేయండి").

---

## Code changes needed before going live

Status 3 Nov 2026: all five are built (`services/core/src/mitra_core/whatsapp/`; the registry in `templates.py` is tested to match this page word for word). Still open: native-speaker review.

1. **Send templates outside the 24-hour window.** Today only `call_heads_up` uses a template; alerts, reports, approvals, staff messages and customer messages are sent as free text, which Meta drops outside the window. The WhatsApp service should check the window per recipient and switch to the matching template above.
2. **Flatten variables:** no line breaks, tabs or more than 4 spaces in a row; trim long values (alert `detail` to about 300 characters).
3. **Named parameters:** send `parameter_format: NAMED` with the names above.
4. **Name fallback:** done per language (see Rules: Telugu sends the honorific inside `{{name}}`).
5. **STOP and opt-out:** treat "STOP", "Don't call me", and the Hindi/Telugu equivalents as an opt-out (CMP-06).

## What Meta needs from you

- Business verification for Viduron AI, a WhatsApp Business account and a sending number.
- Submit each template in all three languages with the samples above. Utility templates are usually reviewed within a day.
