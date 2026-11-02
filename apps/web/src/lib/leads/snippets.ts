// Copy-paste setup snippets for each lead source. Pure strings, safe in client components.
// The secret is only known right after it is created or rotated; otherwise a placeholder is
// shown and the owner pastes the secret they saved.

export const SECRET_PLACEHOLDER = "PASTE_YOUR_MITRA_SECRET";

/** Website form (INT-02): no secret in the browser; the form endpoint needs the consent box. */
export function websiteFormSnippet(formUrl: string, businessName: string): string {
  return `<!-- Mitra enquiry form: paste where the form should appear -->
<form id="mitra-lead-form">
  <input name="name" placeholder="Your name" required>
  <input name="phone" type="tel" placeholder="Mobile number" required>
  <input name="message" placeholder="What are you looking for?">
  <input name="website" tabindex="-1" autocomplete="off" style="display:none">
  <label><input type="checkbox" name="consent" value="yes" required>
    I agree to get a call from ${businessName} about my enquiry.</label>
  <button type="submit">Call me back</button>
  <p id="mitra-lead-status" role="status"></p>
</form>
<script>
document.getElementById("mitra-lead-form").addEventListener("submit", async function (e) {
  e.preventDefault();
  var status = document.getElementById("mitra-lead-status");
  var res = await fetch("${formUrl}", { method: "POST", body: new URLSearchParams(new FormData(e.target)) });
  status.textContent = res.ok ? "Thank you! We will call you shortly." : "Sorry, please try again.";
  if (res.ok) e.target.reset();
});
</script>`;
}

/** Google Sheets (INT-03): sends every new row once and marks it "Sent to Mitra". */
export function sheetsSnippet(url: string, secret: string | null): string {
  return `// Extensions → Apps Script → paste → Save. Then Triggers → Add trigger:
// function "sendNewRowsToMitra", time-driven, every minute.
// Row 1 must have headers such as Name, Phone, City.
var MITRA_URL = "${url}";
var MITRA_SECRET = "${secret ?? SECRET_PLACEHOLDER}";

function sendNewRowsToMitra() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  var rows = sheet.getDataRange().getValues();
  var headers = rows[0];
  var statusCol = headers.indexOf("Mitra");
  if (statusCol < 0) {
    statusCol = headers.length;
    sheet.getRange(1, statusCol + 1).setValue("Mitra");
  }
  for (var r = 1; r < rows.length; r++) {
    if (rows[r][statusCol]) continue;
    var lead = { source: "google_sheets", external_id: sheet.getSheetId() + "-" + (r + 1) };
    headers.forEach(function (h, c) { if (h && c !== statusCol) lead[h] = rows[r][c]; });
    var res = UrlFetchApp.fetch(MITRA_URL, {
      method: "post", contentType: "application/json", muteHttpExceptions: true,
      headers: { "X-Mitra-Secret": MITRA_SECRET }, payload: JSON.stringify(lead)
    });
    sheet.getRange(r + 1, statusCol + 1).setValue(res.getResponseCode() === 202 ? "Sent to Mitra" : "Error " + res.getResponseCode());
  }
}`;
}

/** Google Forms (INT-14): runs on every response. */
export function formsSnippet(url: string, secret: string | null): string {
  return `// In the Google Form: ⋮ → Apps Script → paste → Save. Then Triggers → Add trigger:
// function "onFormSubmit", event source "From form", event type "On form submit".
// Name a question "Phone" (and "Name"); other questions become details for the call.
var MITRA_URL = "${url}";
var MITRA_SECRET = "${secret ?? SECRET_PLACEHOLDER}";

function onFormSubmit(e) {
  var lead = { source: "google_forms", external_id: e.response.getId() };
  e.response.getItemResponses().forEach(function (item) {
    lead[item.getItem().getTitle()] = String(item.getResponse());
  });
  UrlFetchApp.fetch(MITRA_URL, {
    method: "post", contentType: "application/json", muteHttpExceptions: true,
    headers: { "X-Mitra-Secret": MITRA_SECRET }, payload: JSON.stringify(lead)
  });
}`;
}

/** Zapier / Make / Pabbly / n8n / own code (INT-06, INT-12). */
export function curlSnippet(url: string, secret: string | null, source = "zapier"): string {
  return `curl -X POST "${url}" \\
  -H "Content-Type: application/json" \\
  -H "X-Mitra-Secret: ${secret ?? SECRET_PLACEHOLDER}" \\
  -d '{"name": "Ravi Kumar", "phone": "98765 43210", "city": "Kondapur", "source": "${source}"}'`;
}

/** Portals that cannot send headers take the secret as ?key=. */
export function keyedUrl(url: string, secret: string | null): string {
  return `${url}?key=${secret ?? SECRET_PLACEHOLDER}`;
}
