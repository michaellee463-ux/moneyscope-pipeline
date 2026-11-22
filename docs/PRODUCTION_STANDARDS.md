# MONEYSCOPE production standards

The daily task reads this file at the start of every run and follows it exactly.
If a rule here cannot be met, the run does **not** post; it writes a failure note (see the end).

## 1. Topic
- Pick the most viral personal-finance topic available **today**: seasonal moments (tax season, Black Friday/holidays, new contribution limits, Social Security COLA, Fed rate decisions, back-to-school) and current news.
- Format: "money math you can see". Shocking true numbers, scale comparisons, side-by-side ladders (pay in full vs. minimum payment, $5/day invested for 40 years, rent vs. buy, median vs. average).
- **The most extreme TRUE number is on screen at frame 1**, at full value (no count-up on the hook).
- Some videos open with a cliffhanger wh-question.
- Recurring series: **"The Real Cost of…"** and **"What If You Invested…"**, plus many one-offs. Roughly 2 series episodes per week.
- Never repeat a topic in `posted.md` (same core comparison = repeat, even with new numbers, unless the data year changed and the hook is new).
- **Never**: individual stock, fund or crypto picks; "buy X"; guaranteed returns; get-rich-quick claims. Teach the math and the trade-off.

## 2. Accuracy (non-negotiable)
- Every number comes from a **primary source** (Census, BLS, IRS, SSA, Federal Reserve, BEA, Treasury, CFPB, FDIC…) read in this run, using the most recent year available.
- Label the year on screen (scene `tag`). Never mix years in one comparison without saying so on screen.
- All math runs in code: add helpers to `pipeline/moneymath.py`, put every computed value in `spec.checks` (expression + expected value). `pipeline/verify.py` must pass; it fails on any number that is not a sourced fact, a computed check, or an explained constant.
- If a number cannot be verified, cut it. Examples/hypotheticals (e.g. "$35 a month") must be labelled as an example on screen.

## 3. Script and voice
- Length: final video 61–90 s. Hook sentence first, CTA last ("Follow MoneyScope for …").
- Spoken text (`say`) writes every number as words ("twenty-two point three six percent"); captions (`caption`) use numerals.
- Questions: **wh-questions only** (why/what/where/which/how). No yes/no, tag ("right?") or fragment questions; rewrite those as statements. `voice.py` enforces this.
- Kokoro TTS, voice **am_puck**, speed **1.0**, model files only from the kokoro-onnx GitHub release (`pipeline/setup.sh`). Never try Hugging Face first.
- One synth call per **whole sentence**. Never split at commas. Never pitch-bend. Never peak-normalize phrases.
- Pauses: comma ≈ 0.22 s (≈ 0.12 s inside spoken numbers); 0.30–0.45 s between sentences; 0.50–0.65 s after the hook, questions and big reveals (`kind`: hook / question / reveal).
- Every sentence levelled to the same loudness, then one compressor + limiter on the whole narration. Final mix −16 LUFS (±1), true peak ≤ −1 dBFS. Music low underneath (17 dB under voice).
- Read `build/phonemes.txt` every run and fix any word that is mis-phonemized (respell it in `say`).
- `audio.py` QC must pass: no question > 1 dB louder than its neighbours, no clicks at pauses, no clipping, peak ≤ −1 dBFS.

## 4. Visuals
- 1080×1920, 30 fps, H.264 + AAC, rendered headless in Blender (`pipeline/render.py`, Cycles, flat emission shading).
- Dark navy background; accents green (good), gold (neutral/brand), red (cost/danger); Archivo Black font; burned-in captions.
- Scene types available: `big_number`, `statement`, `title`, `ladder`, `compare`, `end_card`. Each scene starts at a sentence index (`at`); ladder rows reveal at sentence indices.
- Every data scene has a `tag` with the source and year (e.g. "Q3 2026 · Federal Reserve G.19").
- Thumbnail 1280×720 (`pipeline/thumbnail.py`): kicker + the two numbers that make the point.

## 5. Post text
- YouTube title ≤ 70 characters, curiosity + number. Shorts type, not made for kids, public, AI-content declaration on (synthetic voice).
- Description: the math in bullets, how the math works, hashtags, then **Sources:** (name, release date, figure, URL), and it **ends with "Not financial advice."**
- TikTok caption: hook line, the key number with source + year, a wh-question, 4–6 hashtags, Source line, ends with "Not financial advice."

## 6. Posting
- Posting time **4:00 PM America/New_York** on both platforms. If TikTok flags spam/pacing, post TikTok at 5:00 PM (≥ 1 h apart).
- Media URL: commit the MP4 + thumbnail, then use the **commit-pinned raw URL** `https://raw.githubusercontent.com/<owner>/<repo>/<sha>/<path>`. Never `/main/`.
- Destinations come **only** from `config/publish.json`. Never post to Explorer Man (Metricool brand 7928588, YouTube `UCxg5spwhAkHj7STl7kJswrg`, TikTok `Explorerman-s4r`). If a destination ID is not in `config/publish.json` → do not post.
- Before scheduling, count this month's published + pending posts for the posting service. If the plan limit would be hit → stop and leave a note.

## 7. Failure handling
- If any step fails (connector down, plan limit, render error, QC fail, unverifiable number): finish every step that can still be done, **do not post a broken video**, and write `runs/<date>-FAILED.md` saying what failed, the exact error, and what the owner must do. Commit it.
- On success append to `posted.md`: date, topic, series, key numbers, sources, post IDs, media URLs.
