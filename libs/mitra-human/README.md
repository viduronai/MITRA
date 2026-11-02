# mitra-human

The human layer for Mitra voice employees. It makes the AI sound like a real Indian
telecaller. It is pure Python (3.12 or later) with zero runtime dependencies, and it runs
in-process inside the voice workers.

| Piece | What it does |
|---|---|
| `speakable(text, lang)` | Rewrites ₹ amounts, numbers, times, dates, phones, ranges and % into spoken form (lakh/crore system), in the script the LLM wrote |
| `BackchannelPolicy` | Decides when to say "mm-hmm / हाँ जी / అవును" while the caller is talking |
| `FillerPolicy` | Returns a short "Let me check." when the answer will be slow |
| `truncate_to_heard(text, n)` | Barge-in: keeps only the words the caller actually heard |
| `honorific(name, lang, formality)` | "Ravi garu", "Ravi ji", "Mr. Ravi" |
| `spell_phone`, `spell_email`, `spell_digits`, `number_to_words` | Read-aloud helpers |

> TODO: native-speaker review for the hi/te tables. See [Choices to confirm](#choices-to-confirm).

## Usage

```python
from mitra_human import (
    BackchannelPolicy,
    FillerPolicy,
    honorific,
    speakable,
    truncate_to_heard,
)

speakable("Your fee is ₹1,20,000/-, payable by 18 Oct.", "en")
# 'Your fee is one lakh twenty thousand rupees, payable by eighteenth October.'

speakable("आपकी अपॉइंटमेंट 18 Oct को 6:15 pm पर है", "hi")
# 'आपकी अपॉइंटमेंट अठारह अक्टूबर को शाम सवा छह बजे पर है'

speakable("మీ అపాయింట్‌మెంట్ 6 pm కి, ఫీజు ₹500", "te")
# 'మీ అపాయింట్‌మెంట్ సాయంత్రం ఆరు గంటలకి, ఫీజు ఐదు వందల రూపాయలు'

bc = BackchannelPolicy("hi", seed=1)
bc.on_user_speech(elapsed_ms=4200, partial_text="मैंने पिछले हफ़्ते बुक किया था और फिर,", pause_ms=400)
# 'हाँ जी'  (seeded; never the same token twice in a row)

fp = FillerPolicy("hi", seed=1, gender="female")
fp.filler_for(expected_latency_ms=1200, turn_index=3)  # 'जी, एक सेकंड…'
fp.filler_for(expected_latency_ms=1200, turn_index=4)  # None (at most one every 2 turns)

truncate_to_heard("Your slot is at six. See you then.", 2)  # 'Your slot…'
honorific("Ravi", "te")  # 'Ravi garu'
honorific("Ravi", "en", "formal", gender="male")  # 'Mr. Ravi'
```

## `speakable` examples

| Input | en | hi | te |
|---|---|---|---|
| `₹500` | five hundred rupees | पाँच सौ रुपये | ఐదు వందల రూపాయలు |
| `₹1,20,000` | one lakh twenty thousand rupees | एक लाख बीस हज़ार रुपये | ఒక లక్ష ఇరవై వేల రూపాయలు |
| `₹2.5 crore` | two and a half crore rupees | ढाई करोड़ रुपये | రెండున్నర కోట్ల రూపాయలు |
| `₹4,200/-` | four thousand two hundred rupees | चार हज़ार दो सौ रुपये | నాలుగు వేల రెండు వందల రూపాయలు |
| `₹10.50` | ten rupees and fifty paise | दस रुपये पचास पैसे | పది రూపాయల యాభై పైసలు |
| `120000` | one lakh twenty thousand | एक लाख बीस हज़ार | ఒక లక్ష ఇరవై వేలు |
| `6:15 pm` | six fifteen in the evening | शाम सवा छह बजे | సాయంత్రం ఆరు పదిహేను |
| `6:45 pm` | six forty-five in the evening | शाम पौने सात बजे | సాయంత్రం ఆరు నలభై ఐదు |
| `1:30 pm` | one thirty in the afternoon | दोपहर डेढ़ बजे | మధ్యాహ్నం ఒకటిన్నర |
| `18 Oct` | eighteenth October | अठारह अक्टूबर | అక్టోబర్ పద్దెనిమిది |
| `18/10/2026` | eighteenth October two thousand twenty-six | अठारह अक्टूबर दो हज़ार छब्बीस | అక్టోబర్ పద్దెనిమిది, రెండు వేల ఇరవై ఆరు |
| `+91 98765 43210` | nine eight seven six five, four three two one zero | नौ आठ सात छह पाँच, चार तीन दो एक ज़ीरो | తొమ్మిది ఎనిమిది ఏడు ఆరు ఐదు, నాలుగు మూడు రెండు ఒకటి సున్నా |
| `Mon–Sat` | Monday to Saturday | सोमवार से शनिवार तक | సోమవారం నుండి శనివారం వరకు |
| `9 am – 9 pm` | nine in the morning to nine at night | सुबह नौ बजे से रात नौ बजे तक | ఉదయం తొమ్మిది గంటల నుండి రాత్రి తొమ్మిది గంటల వరకు |
| `₹500–800` | five hundred to eight hundred rupees | पाँच सौ से आठ सौ रुपये | ఐదు వందల నుండి ఎనిమిది వందల రూపాయల వరకు |
| `50%` | fifty percent | पचास परसेंट | యాభై శాతం |

`speakable` never changes URLs or email addresses. Words like `tomorrow` and any other
text pass through byte-for-byte. Devanagari and Telugu digits (५००, ౫౦౦) are also
recognised.

### Telugu numeral forms

A Telugu number changes shape depending on the word that follows it. `speakable` looks
at that next word:

| Context | Example |
|---|---|
| alone | `500` -> ఐదు వందలు |
| before a noun | `500 రూపాయలు` -> ఐదు వందల రూపాయలు, `1 రోజు` -> ఒక రోజు, `21 రోజులు` -> ఇరవై ఒక్క రోజులు |
| before a postposition | `200 వరకు` -> రెండు వందల వరకు |
| before కి / కు | `500 కి` -> ఐదు వందలకి, `6 pm కి` -> సాయంత్రం ఆరు గంటలకి |

1100-1999 are read as a count of hundreds: `1100` -> పదకొండు వందలు, `1250` -> పన్నెండు
వందల యాభై, `₹1500 కి` -> పదిహేను వందల రూపాయలకి. 1000-1099 keep వెయ్యి (`1050` -> వెయ్యి
యాభై), and numbers with a lakh or crore part are unchanged.

For Telugu, `speakable(text, "te", colloquial_quarters=True)` reads 6:15 / 6:45 as
ఆరుంబావు / ఆరుముప్పావు instead of ఆరు పదిహేను / ఆరు నలభై ఐదు. The flag is off by default
and has no effect on en/hi.

### Code-mixed speech: `te-en` (Tenglish) and `hi-en` (Hinglish)

When the caller code-mixes, pass `"te-en"` or `"hi-en"` to `speakable`, the policies
and the helpers. This follows the founder's rule (confirmed by the founder): **times,
dates and phone numbers are said in English, while amounts and plain numbers stay in
Telugu or Hindi.** Native connectors are kept.

| Input | `te-en` | `hi-en` |
|---|---|---|
| `6:30 pm` (+ కి in te-en) | evening six thirty కి | evening six thirty बजे |
| `evening 11 am` | evening eleven | evening eleven बजे |
| `9 am – 8 pm` | morning nine నుండి night eight వరకు | morning nine बजे से night eight बजे तक |
| `9876543210` | nine eight seven six five, four three two one zero | (same) |
| `18 Oct` | eighteenth October | eighteenth October |
| `Mon–Sat` | Monday నుండి Saturday వరకు | Monday से Saturday तक |
| `₹500` | ఐదు వందల రూపాయలు | पाँच सौ रुपये |
| `₹1500 కి` | పదిహేను వందల రూపాయలకి | — |

- The English time-of-day word (morning / afternoon / evening / night) is added in
  front, unless the text already has one just before the time ("evening 6:30 pm", or a
  native సాయంత్రం / शाम), in which case that word is kept as it is.
- Telugu keeps కి / కు as a separate word after English phrases ("six thirty కి").
  Telugu amounts still merge it (రూపాయలకి). Hinglish adds बजे once, never twice.
- `colloquial_quarters` has no effect in code-mixed mode (times are in English).
- `spell_phone`, `spell_digits` and `spell_email` read in English; `number_to_words`
  and `honorific` follow the native language (ఐదు వందలు, Ravi garu, Ravi ji).
- Back-channels: te-en `అవును / సరే / okay`, hi-en `हाँ जी / अच्छा / okay`. Question cues
  from either language block a back-channel.
- Fillers lean English: te-en `one minute అండి… / check చేస్తాను… / just a second అండి…`,
  hi-en `just one minute जी… / check करती हूँ… / one second जी…` (करता with `gender="male"`).

## Timing rules

**BackchannelPolicy** fires only when all of these hold. The per-turn state resets when
`elapsed_ms` goes backwards or when you call `new_turn()`.

- the caller has spoken for at least 3500 ms in this turn;
- the current pause is 250-700 ms long, i.e. a clause boundary;
- at least 4000 ms have passed since the last back-channel;
- there has been no other back-channel in the same 6-second block of the turn (0-6 s, 6-12 s, …);
- the partial transcript has at least 5 words and its latest clause is not a question.

Tokens rotate without immediate repeats: en `mm-hmm / okay / right`, hi `हाँ जी / अच्छा /
हम्म`, te `అవును / సరే / హ్మ్`. Passing `seed` makes the choice deterministic.

**FillerPolicy** fires only when `expected_latency_ms > 700`. It speaks at most once every
2 turns and never repeats the previous filler. `gender="male"` switches the Hindi verbs
(देखता / करता).

**truncate_to_heard** keeps exactly the first `n` whitespace-separated words, in any
script. When the cut lands mid-sentence it adds `…` and drops a dangling comma or dash.
`n = 0` gives `""`. If `n` is at or past the word count, the text comes back unchanged.

## Choices to confirm

Confirmed by the founder (native Telugu speaker):

- **Code-mixed speech (te-en / hi-en):** times, dates and phone numbers in English,
  amounts in Telugu/Hindi, as described in the code-mixed section above.
- **Telugu times:** hh:30 uses the half form ఆరున్నర. Other minutes are read as
  "hour minute" (ఆరు పదిహేను). The founder said the traditional ఆరుంబావు is equally
  fine, so it is available with `colloquial_quarters=True`. Minutes 1-9 are read as
  ఆరు గంటల ఐదు నిమిషాలు, and 1:00 is ఒంటి గంట.
- **Telugu 1100-1999:** a count of hundreds (పదకొండు వందలు, పంతొమ్మిది వందల తొంభై
  తొమ్మిది), as described above. 19 is spelled పంతొమ్మిది.

Still judgement calls. A native-speaker review should confirm or change them:

- **Telugu "1" before nouns:** ఒక on its own (ఒక లక్ష, ఒక రోజు). Inside a compound it is
  ఒక్క (ఇరవై ఒక్క రూపాయలు, ఇరవై ఒక్క వేలు).
- **Telugu years:** read after the day and month, e.g. అక్టోబర్ పద్దెనిమిది, రెండు వేల ఇరవై ఆరు.
- **Half amounts:** n.5 lakh/crore (n = 1-19) use the spoken half: two and a half crore,
  ढाई करोड़, डेढ़ लाख, రెండున్నర కోట్లు. Every other decimal is expanded exactly
  (₹1.2 lakh -> one lakh twenty thousand).
- **Hindi phone zero:** ज़ीरो, because telecallers say it that way; elsewhere 0 is शून्य.
- **Decimal point:** hi पॉइंट and te పాయింట్, both colloquial, not दशमलव / దశాంశం.
- **Percent:** hi परसेंट (colloquial) and te శాతం.
- **English style:** British "and" (one hundred and one). Years are read as "two thousand
  twenty-six". Ordinal day first: "eighteenth October".
- **Hindi ordinals** are masculine (पहला, दूसरा).
- **Times without am/pm** for hours 1-12 ("9:30") get no morning/evening word.
- **Indian mobiles** drop the +91 / 0 prefix and are grouped 5-5 unless the text already
  groups them.

## Development

```bash
uv sync
uv run pytest            # 663 tests, including Hypothesis property tests
uv run ruff check . && uv run ruff format --check .
uv run mypy              # --strict, src + tests
```
