# Mitra voice recording kit

Mitra's AI phone employees will speak with the voices of our own team members. Each
voice is cloned with the person's written consent, using Sarvam Bulbul v3. Bulbul needs
**10–60 seconds of clean speech** per voice. This kit explains how to record that clip
so the clone sounds warm, natural and clearly Indian, like a good receptionist or
telecaller.

## Who records

- Team members who have **read and signed** [`consent-form.md`](consent-form.md). Nobody
  records before the form is signed and entered in
  [`consent-register-template.csv`](consent-register-template.csv).
- One person records one or more languages: Telugu, Hindi, English, or code-mixed
  (Tenglish / Hinglish). Record only the languages you speak comfortably every day.

## Why it matters

The cloned voice copies *everything* in your recording: room echo, fan hum, a tired
voice, a "reading from paper" tone. Five careful minutes here decide how every Mitra
call sounds.

## Before you start

| Check | Why |
|---|---|
| **Quiet, small, soft room.** A bedroom with curtains, a bed and cupboards is ideal. Avoid empty rooms, bathrooms and stairwells. | Hard, bare walls cause echo. |
| **Fan, AC and cooler OFF.** Close the windows. Put phones on silent. Ask others not to talk or play TV nearby. | Steady hum is the most common reason a clone sounds bad. |
| **Drink water** 10 minutes before. Avoid tea, coffee or milk just before. Record when you are fresh, not after a long day. | Dry mouth causes clicks. |
| **Read the script aloud twice** before recording. | You should *say* it, not read it. |

## Recording setup

1. **Device:** a recent phone or a laptop with a decent mic. A wired earphone mic
   (clipped near the chest) also works well. Don't use Bluetooth earbuds, because they
   compress the sound.
2. **Distance:** hold the mic **about 20 cm away** (one hand-span), slightly to the side
   of your mouth so your breath doesn't hit it directly. Keep the same distance the whole
   time.
3. **Settings:**
   - **Format: WAV**, 44.1 kHz or 48 kHz, 16-bit or higher, **mono** if there's an option.
   - **Android:** use an app that records WAV, such as "Voice Recorder" set to WAV, or
     "ASR Voice Recorder". If WAV isn't possible, use the highest-quality setting (for
     example M4A / AAC at 256 kbps or more).
   - **iPhone:** Voice Memos → Settings → Audio Quality → **Lossless**.
   - **Laptop:** Audacity (free). Set Project Rate to 48000 Hz and Mono, then
     File → Export → WAV.
   - Turn **off** any "noise reduction", "voice enhance" or "auto gain" options. We
     want the raw voice.
4. **Level test:** record 5 seconds of normal speech and play it back. It should be
   clear and not distorted. Then record 5 seconds of silence and listen with earphones.
   You should hear nothing (no hum, no traffic).

## How to speak

- Speak in **natural telecaller tone**: friendly, calm, smiling, at a normal speed. Imagine a
  real customer is on the line and you're happy to help. **Smile while you speak.**
  Callers can hear it.
- Do **not** perform, read like news, or put on an accent. Use your everyday way of talking,
  including the English words you normally mix in.
- Small natural pauses at commas are good. Don't rush, and don't stretch words.
- If you stumble, pause for 2 seconds and restart the **sentence**. Don't restart the
  whole script. We can trim later.
- Keep the same energy from start to end.

## What to record

For **each language** you speak:

1. **Full script, 3 takes.** Each take is 60–90 seconds, from the matching script file:
   - [`scripts-te.md`](scripts-te.md) (Telugu)
   - [`scripts-hi.md`](scripts-hi.md) (Hindi)
   - [`scripts-en.md`](scripts-en.md) (Indian English)
   - [`scripts-code-mixed.md`](scripts-code-mixed.md) (Tenglish / Hinglish)
2. **Short clip, 3 takes.** Each is about 10 seconds, from the "short clip" section of
   the same file.

Leave about 1 second of silence at the start and end of each take. Take a short break
and sip water between takes.

## File naming

```
<name>_<lang>_<take>.wav
```

- `name`: first name, lower case, no spaces (for example `priya`, `ravi`)
- `lang`: `te`, `hi`, `en`, `te-en` (Tenglish) or `hi-en` (Hinglish). Add `-short`
  for short clips.
- `take`: `1`, `2`, `3`

Examples: `priya_te_1.wav`, `priya_te-short_2.wav`, `ravi_hi-en_3.wav`

## Self-check before you send

Listen to each take with earphones and ask:

- [ ] No fan, AC, traffic, TV, other voices, phone buzz or keyboard clicks?
- [ ] No echo ("bathroom sound")?
- [ ] Nothing distorted or crackling on loud words?
- [ ] Does it sound like *talking to a customer*, not reading?
- [ ] Is the file named correctly?

Re-record any take that fails a check. One clean take is worth more than three noisy ones.

## Upload

1. Put your files in the shared **Mitra voice-kit** folder that the founder gives you
   access to. Don't send them on WhatsApp, because it compresses audio.
2. The founder or voice lead picks the best take and uploads it in the **Sarvam dashboard
   voice-cloning flow** (Bulbul v3). Trim it to the cleanest 10–60 seconds, name the voice
   `<name>_<lang>` and tick the consent confirmation. Check Sarvam's current documentation
   for the exact steps, because the dashboard may change.
3. The voice lead records the resulting `voice_id` in the consent register and test-calls
   the cloned voice. You'll be asked to listen to a sample and approve it before it goes live.

## If you change your mind

You can withdraw consent at any time. Tell the founder in writing (email or WhatsApp
message is fine). The clone will be deleted as described in the consent form.
