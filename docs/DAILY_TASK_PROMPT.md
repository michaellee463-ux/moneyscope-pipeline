# Daily task prompt (paste into the scheduled task)

You are producing today's MONEYSCOPE video (YouTube Shorts + TikTok) with zero input from the owner. The repo `moneyscope-pipeline` is checked out in your working directory.

1. Read `README.md`, `docs/PRODUCTION_STANDARDS.md`, `config/publish.json` and `posted.md`. Follow the standards exactly; they override anything below if they conflict.
2. Run `bash pipeline/setup.sh`.
3. Pick today's topic (most viral personal-finance angle right now: season, news, data releases). It must not repeat any topic in `posted.md`. Prefer a recurring series about twice a week.
4. Research every number from primary sources (Census, BLS, IRS, SSA, Federal Reserve, BEA, Treasury, CFPB…). Open the source page and read the figure yourself. Use the latest year; note release date and URL. Cut anything you cannot verify.
5. Create `episodes/<YYYY-MM-DD>-<slug>/spec.json` by copying the newest episode's spec as a template: sentences (`say` numbers as words; `caption` numerals; `kind`), scenes, facts, checks (all math as code via `pipeline/moneymath.py`), allowed_numbers, thumbnail, metadata. Post date = today, 4:00 PM America/New_York.
6. Run `bash pipeline/run.sh episodes/<slug>`. Read `build/phonemes.txt`; respell any mispronounced word and re-run. All QC must pass (`verify`, `audio_qc.json`, `video_qc.json`). If a step fails, fix the spec and retry up to 2 times; if it still fails go to step 10.
7. Commit `spec.json`, `video.mp4`, `thumbnail.jpg` (not `build/`), push, and get the commit SHA. Media URLs: `https://raw.githubusercontent.com/<owner>/moneyscope-pipeline/<sha>/episodes/<slug>/video.mp4` (and `thumbnail.jpg`). Never use `/main/`. Check each URL returns HTTP 200 before posting.
8. Post, using ONLY the accounts in `config/publish.json` (`service` says which connector). Refuse any account in `forbidden` (Explorer Man). Before scheduling, count this month's published + pending posts on that service; if a plan limit would be hit, stop and go to step 10.
   - vidIQ: `vidiq_video_upload` (url = raw MP4 URL), `vidiq_upload_image` for the thumbnail, `vidiq_social_post_draft_create` with YouTube (title, description as text, tags, privacyStatus public, categoryId 27, thumbnailImageId, publishAt 16:00 ET) and TikTok (caption, settings from config, publishAt 16:00 ET; 17:00 if pacing flagged), then `vidiq_social_post_publish`. The owner has given standing approval in this task for posts that pass every check in these standards.
   - Metricool (if `service` is metricool): `createScheduledPost` on `metricool.brand_id` only, YouTube type short + TikTok, media = raw URL, `videoThumbnailUrl` = raw thumbnail URL.
9. Append a row to `posted.md` (date, topic, series, key numbers, sources, post IDs, media URLs), commit and push.
10. On any failure: do not post anything broken. Finish the steps you still can, write `runs/<date>-FAILED.md` (what failed, exact error, what the owner must do), commit and push it, and end with that summary.
