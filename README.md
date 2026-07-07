<div align="center">

```
      _      _  __  _   
   __| |_ __(_)/ _|| |_ 
  / _` | '__| | |_ | __|
 | (_| | |  | |  _|| |_ 
  \__,_|_|  |_|_|   \__|
```

### **drift.jobs**
*Your resume, working while you sleep.*

![Python](https://img.shields.io/badge/Python-3.10+-black?style=flat-square)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15-black?style=flat-square)
![Groq](https://img.shields.io/badge/Groq-Llama_3-black?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-black?style=flat-square)

</div>

---

**drift** reads your resume, scrapes job boards in parallel, and scores every
listing against your profile — then surfaces only the ones worth your time,
tells you *why* each one fits (and what you're missing), and drafts a tailored
cover letter in one click.

Upload your CV. Pick your sources. Set a match threshold. Let it run.

> **No API key required.** Drift scores every job locally out of the box. Add a
> free [Groq](https://console.groq.com/keys) key in **⚙ Settings** for sharper
> AI scoring and AI-written cover letters.

---

## How it works

```
your resume (PDF/DOC/DOCX)
        │
        ▼
  extract skills, keywords, location
  (local, or Groq if a key is set)
        │
        ▼
  scrape sources in parallel
  RemoteOK · Remotive · Arbeitnow · …
        │
        ▼
  hybrid scoring
  free local baseline for every job,
  Groq refines the top matches
        │
        ▼
  results sorted by fit — matched vs
  missing skills, cover letters,
  save / apply / dismiss, live filters
```

---

## Features

- **Works with zero setup** — local, word-boundary skill matching scores every
  job with no key, no quota, no cloud.
- **Hybrid AI scoring** — the free local pass ranks everything; Groq (Llama 3)
  refines the most promising matches for a sharper 0–100 fit score.
- **Gap analysis** — every card shows the skills you **match** *and* the skills
  the job wants that you're **missing**.
- **One-click cover letters** — AI drafts a tailored, editable letter per job;
  copy it or save it as `.txt`. Falls back to a local template with no key.
- **Reliable, key-free sources** — RemoteOK, Remotive, and Arbeitnow are JSON
  APIs that return *real job descriptions* and don't get blocked. LinkedIn,
  Indeed, ZipRecruiter, web search, and any custom `/jobs` page are also there.
- **Parallel scraping** — sources run concurrently; a scan takes seconds, and a
  **Stop** button lets you score what's found so far at any moment.
- **Job states that stick** — **Save**, mark **Applied**, or **Dismiss** a job.
  Dismissed jobs never come back, and previously-seen jobs are flagged **NEW**.
- **Live filtering** — drag the match slider, search by title/company/skill, or
  filter by All / New / Saved / Applied — instantly, without re-scanning.
- **Export anywhere** — CSV, JSON, or a polished shareable HTML report.
- **In-app settings** — set your Groq key, model, and scoring depth from a
  dialog; it writes back to `.env` for you.

---

## Getting started

### Prerequisites

- Python 3.10+
- *(optional)* Google Chrome — only for the LinkedIn / Indeed scrapers
- *(optional)* A free Groq API key → [console.groq.com/keys](https://console.groq.com/keys)

### Installation

```bash
git clone https://github.com/farixdev/Drift-JobFinder.git
cd Drift-JobFinder

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
```

### Run

```bash
python main.py
```

That's it — Drift runs immediately with local scoring. To enable AI scoring and
cover letters, click **⚙ Settings** in the app and paste a free Groq key (or
create a `.env` with `GROQ_API_KEY=...`).

---

## Usage

1. **Upload your resume** — drag a `.pdf` / `.doc` / `.docx` onto the drop zone.
2. **Pick sources** — the ★ recommended ones (RemoteOK, Remotive, Arbeitnow) are
   on by default and need no login. Or paste a company `/jobs` URL.
3. **Set your threshold** — the minimum match score you care about.
4. **Start scanning** — watch sources stream in live; hit **Stop** any time.
5. **Review** — cards are sorted by fit, with matched (green) and missing
   (amber) skills. Drag the slider or search to refine on the fly.
6. **Act** — **Apply** opens the listing, **✎ Cover letter** drafts one,
   **★ Save** / **✓ Applied** / **✕ Dismiss** track your pipeline.
7. **Export** — CSV, JSON, or an HTML report.

---

## Project structure

```
drift/
├── main.py                     # entry point
├── models.py                   # Job model + states + fingerprinting
├── ui/
│   ├── app.py                  # window + screen manager
│   ├── screen_setup.py         # upload + sources + threshold
│   ├── screen_scan.py          # live parallel scan log + Stop
│   ├── screen_results.py       # cards, filters, actions, export
│   ├── dialogs.py              # Settings + Cover letter dialogs
│   ├── worker.py               # concurrent, cancellable scan pipeline
│   ├── widgets.py              # top bar, chips, source rows
│   └── styles.py               # dark design tokens
├── core/
│   ├── config.py               # .env read/write, settings
│   ├── parser.py               # PDF/DOC/DOCX text extraction
│   ├── ai_engine.py            # Groq: parse, score, cover letters
│   ├── local_engine.py         # offline scoring + gap analysis
│   ├── matcher.py              # hybrid local + AI ranking
│   ├── report.py               # CSV / JSON / HTML export
│   ├── skills_db.py            # skill vocabulary
│   └── scraper/
│       ├── remoteok.py         # ★ JSON API, no key
│       ├── remotive.py         # ★ JSON API, no key
│       ├── arbeitnow.py        # ★ JSON API, no key
│       ├── wwr.py              # We Work Remotely
│       ├── linkedin.py         # Selenium (needs Chrome)
│       ├── indeed.py           # Selenium (needs Chrome)
│       ├── ziprecruiter.py     # best-effort HTML
│       ├── internet_bing.py    # web search
│       ├── internet_google.py  # web search
│       ├── custom.py           # any company /jobs page
│       └── util.py             # HTML clean, dates, salary
├── db/                         # SQLite job store + states
└── templates/report.html       # HTML export template
```

---

## Tech stack

| | |
|---|---|
| Language | Python 3.10+ |
| UI | PyQt5 |
| Resume parsing | pdfplumber · pymupdf · pypdf · python-docx |
| AI / scoring | Groq — Llama 3 (free tier) · local fallback |
| Scraping | requests · BeautifulSoup · Selenium (optional) |
| Storage | SQLite3 |
| Export | Jinja2 · CSV · JSON |

---

## Groq free tier

Drift defaults to **Llama 3.1 8B Instant** — fast, free, generous limits. Switch
to **Llama 3.3 70B** in Settings for even sharper judgment. A typical scan of
~50 jobs makes ~2 API calls (one to parse the resume, one to batch-score the top
matches), so you stay well inside the free tier — and with no key at all, Drift
still scores every job locally.

---

## Roadmap

- [ ] Email digest — daily summary of new high matches
- [ ] Saved profiles — named resume + source presets, re-run on a schedule
- [ ] Auto-fetch full JDs for Selenium sources to sharpen scoring
- [ ] Resume gap coach — "learn these 3 skills to unlock 12 more jobs"
- [ ] More sources (Otta, Y Combinator, Wellfound)

---

## License

MIT — do whatever you want with it.

---

<div align="center">
  <sub>Built by <a href="https://github.com/farixdev">faris</a> · give it a ⭐ if it helped</sub>
</div>
