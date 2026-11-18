# iliaCollections | Stories

Automated daily publishing for the Instagram page **@iliacollectionstories**: 100 short human stories, one per day.

## How it works

- Every day at **17:37 (Bucharest time)** GitHub Actions runs `publish.py`.
- The script looks in `schedule.json` for today's story, publishes its 7 slides as a carousel with the hashtags, and writes the result in `posted.json`.
- A backup run at 19:07 posts only if the first run didn't. A story is never posted twice.
- The Story (9:16, with "Day N.") is posted **manually** from the phone, with music: `stories/NNN/story.jpg`.

## Files

| Path | What it is |
|---|---|
| `stories/NNN/1.jpg … 7.jpg` | the carousel slides (JPEG, 1080×1350) |
| `stories/NNN/story.jpg` | the Instagram Story image (1080×1920) |
| `schedule.json` | story number, title, date, caption (hashtags) |
| `posted.json` | log of what was published, with links |
| `publish.py` | the publishing script |
| `.github/workflows/publish.yml` | the daily schedule |

## Common tasks

- **Test without publishing:** Actions → *Publish daily story* → *Run workflow* → leave "Test only" checked.
- **Publish a story manually:** same, enter the story number and uncheck "Test only".
- **Change hashtags or a date:** edit `schedule.json` directly on GitHub.
- **Change the posting time:** edit the `cron` lines in `.github/workflows/publish.yml` (times are UTC; Bucharest = UTC+2 in winter).
- **New token:** Settings → Secrets and variables → Actions → `IG_TOKEN` → Update.
