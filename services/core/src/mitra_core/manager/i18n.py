"""Owner-facing Manager phrases in English, Hindi and Telugu (07-SCREENS §6: numbers first,
≤ 6 lines, owner's language). Values are ``str.format`` templates filled from tool results.
"""

from __future__ import annotations

from typing import Any

from mitra_core.manager.intents import Lang

PERIOD = {
    "today": {"en": "Today", "hi": "आज", "te": "ఈ రోజు"},
    "yesterday": {"en": "Yesterday", "hi": "कल", "te": "నిన్న"},
    "week": {"en": "This week", "hi": "इस हफ्ते", "te": "ఈ వారం"},
}

RESULT = {
    "booked": {"en": "booked", "hi": "बुक हुए", "te": "బుక్ అయ్యాయి"},
    "interested": {"en": "interested", "hi": "इंटरेस्टेड", "te": "ఆసక్తి ఉంది"},
    "call_back": {"en": "call back", "hi": "कॉल बैक", "te": "మళ్ళీ కాల్"},
    "transferred": {"en": "passed to staff", "hi": "स्टाफ को दिए", "te": "స్టాఫ్‌కు ఇచ్చారు"},
    "not_interested": {"en": "not interested", "hi": "इंटरेस्ट नहीं", "te": "ఆసక్తి లేదు"},
    "info_only": {"en": "info only", "hi": "सिर्फ जानकारी", "te": "సమాచారం మాత్రమే"},
    "missed": {"en": "missed", "hi": "मिस्ड", "te": "మిస్డ్"},
}

T: dict[str, dict[str, str]] = {
    "summary_head": {
        "en": "{period}: {total} calls",
        "hi": "{period}: {total} कॉल",
        "te": "{period}: {total} కాల్స్",
    },
    "summary_none": {
        "en": "{period}: no calls yet.",
        "hi": "{period}: अभी तक कोई कॉल नहीं।",
        "te": "{period}: ఇంకా కాల్స్ లేవు.",
    },
    "unknown_line": {
        "en": "{count} questions we could not answer",
        "hi": "{count} सवालों का जवाब नहीं दे पाए",
        "te": "{count} ప్రశ్నలకు జవాబు ఇవ్వలేకపోయాం",
    },
    "attention_head": {
        "en": "{count} need you:",
        "hi": "{count} चीज़ों पर आपका ध्यान चाहिए:",
        "te": "{count} విషయాలు మీ కోసం:",
    },
    "attention_none": {
        "en": "Nothing needs you right now.",
        "hi": "अभी कुछ भी आपका इंतज़ार नहीं कर रहा।",
        "te": "ప్రస్తుతం మీ కోసం ఏమీ లేదు.",
    },
    "bookings_head": {
        "en": "{day}: {count} bookings",
        "hi": "{day}: {count} बुकिंग",
        "te": "{day}: {count} బుకింగ్స్",
    },
    "bookings_none": {
        "en": "{day}: no bookings.",
        "hi": "{day}: कोई बुकिंग नहीं।",
        "te": "{day}: బుకింగ్స్ లేవు.",
    },
    "search_head": {
        "en": "{count} calls about “{query}” (last 30 days):",
        "hi": "“{query}” के बारे में {count} कॉल (पिछले 30 दिन):",
        "te": "“{query}” గురించి {count} కాల్స్ (గత 30 రోజులు):",
    },
    "search_none": {
        "en": "No calls about “{query}” in the last 30 days.",
        "hi": "पिछले 30 दिनों में “{query}” के बारे में कोई कॉल नहीं।",
        "te": "గత 30 రోజుల్లో “{query}” గురించి కాల్స్ లేవు.",
    },
    "customer_none": {
        "en": "I could not find a customer called “{query}”.",
        "hi": "“{query}” नाम का कोई ग्राहक नहीं मिला।",
        "te": "“{query}” అనే కస్టమర్ దొరకలేదు.",
    },
    "wallet": {
        "en": "Wallet balance: {amount}",
        "hi": "वॉलेट बैलेंस: {amount}",
        "te": "వాలెట్ బ్యాలెన్స్: {amount}",
    },
    "wallet_none": {
        "en": "No wallet yet: top up in the app to start calling.",
        "hi": "अभी वॉलेट नहीं है: कॉल शुरू करने के लिए ऐप में टॉप-अप करें।",
        "te": "ఇంకా వాలెట్ లేదు: కాల్స్ కోసం యాప్‌లో టాప్-అప్ చేయండి.",
    },
    "unknown_head": {
        "en": "Questions we could not answer ({period}):",
        "hi": "जिन सवालों का जवाब नहीं दे पाए ({period}):",
        "te": "జవాబు ఇవ్వలేకపోయిన ప్రశ్నలు ({period}):",
    },
    "unknown_none": {
        "en": "{period}: every question was answered.",
        "hi": "{period}: हर सवाल का जवाब दिया गया।",
        "te": "{period}: అన్ని ప్రశ్నలకు జవాబు ఇచ్చాం.",
    },
    "team_line": {"en": "{name}: {status}", "hi": "{name}: {status}", "te": "{name}: {status}"},
    "confirm_payment_link": {
        "en": "Send {name} a payment link for {amount} ({purpose}) on WhatsApp. Confirm?",
        "hi": "{name} को {amount} ({purpose}) का पेमेंट लिंक WhatsApp पर भेजें। पक्का करें?",
        "te": "{name}కి {amount} ({purpose}) పేమెంట్ లింక్ WhatsAppలో పంపాలా? నిర్ధారించండి.",
    },
    "payment_amount_missing": {
        "en": "How much? Say it like “Send Ramesh a payment link for ₹2,000”.",
        "hi": "कितने का? ऐसे कहिए: “Send Ramesh a payment link for ₹2,000”।",
        "te": "ఎంత? ఇలా చెప్పండి: “Send Ramesh a payment link for ₹2,000”.",
    },
    "payments_not_set_up": {
        "en": "Set up payment collection first (app → Payments → How you collect).",
        "hi": "पहले पेमेंट लेना सेट करें (ऐप → Payments → How you collect)।",
        "te": "ముందు పేమెంట్ సేకరణ సెట్ చేయండి (యాప్ → Payments → How you collect).",
    },
    "team_none": {
        "en": "You have not hired an AI employee yet.",
        "hi": "आपने अभी तक कोई AI कर्मचारी नहीं रखा है।",
        "te": "మీరు ఇంకా AI ఉద్యోగిని నియమించలేదు.",
    },
    "help": {
        "en": "Ask me: “What happened this week?”, “What needs my attention today?”, "
        "“Who called about MRI?”. Or tell me: “Pause Priya”, “Call Ramesh back at 5”.",
        "hi": "पूछिए: “इस हफ्ते क्या हुआ?”, “आज मुझे किस पर ध्यान देना है?”। "
        "या कहिए: “Pause Priya”, “Call Ramesh back at 5”।",
        "te": "అడగండి: “ఈ వారం ఏమైంది?”, “ఈ రోజు నేను ఏం చూడాలి?”. "
        "లేదా చెప్పండి: “Pause Priya”, “Call Ramesh back at 5”.",
    },
    "no_employee": {
        "en": "I could not find an employee called “{query}”.",
        "hi": "“{query}” नाम का कोई कर्मचारी नहीं मिला।",
        "te": "“{query}” అనే ఉద్యోగి దొరకలేదు.",
    },
    "confirm_pause": {
        "en": "Pause {name}? They will stop taking and making calls.",
        "hi": "{name} को रोकें? वह कॉल लेना और करना बंद कर देंगी।",
        "te": "{name}ని ఆపాలా? కాల్స్ తీసుకోవడం, చేయడం ఆపేస్తారు.",
    },
    "confirm_resume": {
        "en": "Start {name} again?",
        "hi": "{name} को फिर से शुरू करें?",
        "te": "{name}ని మళ్ళీ మొదలుపెట్టాలా?",
    },
    "confirm_callback": {
        "en": "{employee} will call {name} back at {when}. Confirm?",
        "hi": "{employee} {name} को {when} पर वापस कॉल करेंगी। पक्का करें?",
        "te": "{employee} {name}కి {when}కి మళ్ళీ కాల్ చేస్తారు. నిర్ధారించాలా?",
    },
    "confirm_call_list": {
        "en": "Call {count} people ({period}, {results})? "
        "{employee} will call within allowed hours.",
        "hi": "{count} लोगों को कॉल करें ({period}, {results})? {employee} तय समय में कॉल करेंगी।",
        "te": "{count} మందికి కాల్ చేయాలా ({period}, {results})? {employee} అనుమతి ఉన్న సమయంలో చేస్తారు.",
    },
    "call_list_none": {
        "en": "Nobody matches ({period}, {results}), so there is no one to call.",
        "hi": "({period}, {results}) में कोई नहीं मिला, कॉल करने के लिए कोई नहीं।",
        "te": "({period}, {results})లో ఎవరూ లేరు, కాల్ చేయడానికి ఎవరూ లేరు.",
    },
    "confirm_coach": {
        "en": "I'll change how {name} behaves: “{note}”. Confirm?",
        "hi": "मैं {name} का तरीका बदलूँगा: “{note}”. पक्का करें?",
        "te": "{name} ప్రవర్తన మారుస్తాను: “{note}”. నిర్ధారించాలా?",
    },
    "staff_only_questions": {
        "en": "Only the owner or a manager can give commands. Ask them to confirm.",
        "hi": "सिर्फ मालिक या मैनेजर ही आदेश दे सकते हैं।",
        "te": "యజమాని లేదా మేనేజర్ మాత్రమే ఆదేశాలు ఇవ్వగలరు.",
    },
    "voice_unavailable": {
        "en": "I could not listen to that voice note yet. Please type it.",
        "hi": "मैं अभी यह वॉइस नोट नहीं सुन पाया। कृपया लिखकर भेजें।",
        "te": "ఈ వాయిస్ నోట్ ఇంకా వినలేకపోయాను. దయచేసి టైప్ చేయండి.",
    },
    "open_app": {"en": "Open in app: {link}", "hi": "ऐप में देखें: {link}", "te": "యాప్‌లో చూడండి: {link}"},
    "done": {"en": "Done.", "hi": "हो गया।", "te": "అయిపోయింది."},
    "declined": {"en": "OK, cancelled.", "hi": "ठीक है, रद्द किया।", "te": "సరే, రద్దు చేశాను."},
    "stale": {
        "en": "That card has changed or was already used. Open the app to review.",
        "hi": "यह कार्ड बदल गया है या पहले ही इस्तेमाल हो चुका है। ऐप में देखें।",
        "te": "ఈ కార్డ్ మారింది లేదా ఇప్పటికే వాడారు. యాప్‌లో చూడండి.",
    },
}

STATUS = {
    "working": {"en": "working", "hi": "काम पर", "te": "పనిలో ఉన్నారు"},
    "paused": {"en": "paused", "hi": "रुकी हुई", "te": "ఆపబడింది"},
    "training": {"en": "learning", "hi": "सीख रही है", "te": "నేర్చుకుంటున్నారు"},
}


def t(key: str, lang: Lang, **values: Any) -> str:
    template = T[key].get(lang) or T[key]["en"]
    return template.format(**values)


def word(table: dict[str, dict[str, str]], key: str, lang: Lang) -> str:
    entry = table.get(key)
    return (entry.get(lang) or entry["en"]) if entry else key
