![KrishiBondhu.AI: a Bangla crop-health advisor for Bangladeshi farmers, built for the Meta Global AI Developer Hackathon 2026](assets/banner_v2.png)

<h1 align="center">KrishiBondhu.AI 🌱</h1>

<p align="center">
  <b>কৃষকের ডিজিটাল বন্ধু</b>: the farmer's digital friend.<br/>
  Snap a photo of a sick leaf, get a Bangla treatment plan you can trust, and a follow-up until the crop recovers.
</p>

<p align="center">
  <img alt="Meta Global AI Developer Hackathon 2026" src="https://img.shields.io/badge/Meta%20Global%20AI%20Hackathon-2026-0866FF?style=flat-square">
  <img alt="Muse · SAM 3.1 · Meta ASR" src="https://img.shields.io/badge/Muse%20·%20SAM%203.1%20·%20Meta%20ASR-1C2730?style=flat-square">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-agent-1C3C3C?style=flat-square">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=nextdotjs">
  <img alt="Postgres" src="https://img.shields.io/badge/Postgres-RLS-336791?style=flat-square&logo=postgresql&logoColor=white">
  <img alt="MIT License" src="https://img.shields.io/badge/License-MIT-green?style=flat-square">
  <img alt="Python 3.14" src="https://img.shields.io/badge/Python-3.14-3776AB?style=flat-square&logo=python&logoColor=white">
</p>

---

## Why

A Bangladeshi farmer who spots brown patches on their rice usually asks the pesticide seller, who sells
whatever is on the shelf. The government's agriculture department publishes good advice and a register of
which pesticides are approved for which crop, but it sits on websites and in PDFs few farmers will ever
read, and the local agriculture officer looks after thousands of farmers.

**KrishiBondhu** puts that official knowledge in the farmer's pocket, in Bangla, by voice or photo, and
stays with them after the first answer.

## What it does

|  |  |
| --- | --- |
| 📸 **Sees the problem** | Send a photo; SAM 3.1 marks the lesions or pests on it, so the farmer sees exactly what the diagnosis is based on. Unsure? It says so and asks for a clearer photo. |
| 📚 **Answers from official sources** | Advice comes from *Krishoker Janala* (কৃষকের জানালা), the Department of Agricultural Extension's guidance on 998 problems across 122 crops, with reference photos to compare. |
| 🧪 **Only registered pesticides** | Every chemical is checked against the DAE pesticide register for *that* crop. Unregistered ones are flagged, never recommended. Doses per bigha, with the WHO hazard class. |
| 🗓️ **A plan, day by day** | Treatment becomes a timeline: spray on a dry day (it checks the forecast), look again on day 3, send a photo. Also for growing things: a full Boro rice season, mushrooms, a fertiliser schedule, every dose with its source. |
| 👩‍🌾 **A real person when needed** | Getting worse? It books a phone call, field visit or office visit with the district's agriculture officer and sends them a summary of the case. |
| 🎙️ **Talk, don't type** | Push to talk in Bangla (Meta ASR). It remembers your land, crops and what worked last season. |
| 🔒 **Private by design** | Each farmer's data is isolated in Postgres with row-level security: one farmer's queries can never see another's rows. |

## How it works

```mermaid
flowchart LR
    F(["👩‍🌾 Farmer<br/>photo · voice · text"]) --> UI["Web app<br/>Next.js + OpenUI"]
    UI --> A{{"KrishiBondhu agent<br/>Muse on LangGraph"}}
    A --> S["SAM 3.1<br/>marks the problem"]
    A --> K["Krishoker Janala<br/>+ pesticide register"]
    A --> W["Weather · web search<br/>reference photos"]
    A --> P["Plans · officer bookings<br/>memory"]
    A -- "Bangla reply as cards,<br/>forms and a timeline" --> UI
```

The agent writes its replies in [OpenUI](https://www.openui.com) so answers arrive as real interface:
pesticide cards, maps, photo grids, forms and follow-up buttons, not walls of text. Every tool call is
narrated live in Bangla ("ছবিতে দাগ খুঁজছি…"), so the farmer sees what it is doing.

➡️ The full architecture, data flow and development guide are in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Quick start

You need Docker, a Postgres database and access to the Meta model APIs.

```bash
git clone https://github.com/fahim-muntasir-niloy/meta-hackathon.git
cd meta-hackathon
cp .env.example .env        # fill in META_*, DB_URI, LANGSMITH_*, NGROK_AUTHTOKEN
uv run krishi-db migrate    # tables, row-level security, officer roster
uv run krishi-db load-agri  # pesticide register + Krishoker Janala advice
docker compose up --build
```

Open **http://localhost:3000**, tap *শুরু করুন*, and sign in with any mobile number.

Try:

- *"আমার ধানের পাতায় চোখের মতো দাগ পড়ছে। কী করব?"* (plus a photo)
- *"আমি ২ বিঘায় বোরো ধান লাগাব। কবে কোন সার কতটা দিতে হবে?"*
- *"কৃষি অফিসারের সাথে ফোনে কথা বলতে চাই।"*

## Built with

| Layer | Tech |
| --- | --- |
| Models | **Muse** (reasoning, Bangla, web search) · **SAM 3.1** (segmentation) · **Meta ASR** (voice) |
| Agent | LangChain `create_agent` on the LangGraph Agent Server, Postgres checkpoints and memory store |
| Web | Next.js 16, React 19, OpenUI generative UI, Leaflet, Anek Bangla |
| Data | Postgres with row-level security, Krishoker Janala, DAE pesticide register, Open-Meteo, Wikimedia Commons |
| Ops | Docker Compose, Caddy, ngrok, LangSmith |

## Project layout

```text
src/meta_hackathon/
├── agent/          the agent: model, middleware, system prompt
├── tools/          what the agent can do (diagnose, advise, plan, book, remember)
├── api/            REST routes for the web app and text channels
├── sql/            schema with row-level security
├── knowledge.py    Krishoker Janala retrieval + register check
├── cases.py        treatment and cultivation plans
└── bookings.py     officer roster and slots
frontend/           Next.js app: landing page, chat, plan pane
assets/             banner, officer roster, reference data
```

## Upcoming

- 💬 **WhatsApp and Messenger**: the same advisor where farmers already are; the plain-text chat API is ready for it.
- ⏰ **Reminders on the day**: a message on the morning a step is due ("আজ দ্বিতীয় কিস্তি ইউরিয়া দিন"), and a nudge when a check goes unanswered.
- 📞 **Voice replies for low-literacy users**: answers read aloud in Bangla, so a farmer who can't read can still use it end to end.
- 🧮 **Verified fertiliser schedules**: BARC-recommended doses for the major crops built in, so cultivation plans don't depend on web search.
- 🗺️ **Outbreak alerts for officers**: anonymised, district-level maps of what farmers are reporting, so officers can warn a whole area early.

## Data and credits

- **Krishoker Janala** (কৃষকের জানালা) and the **pesticide register** (Dec 2020): Department of Agricultural Extension, Bangladesh.
- WHO Recommended Classification of Pesticides by Hazard.
- Weather by [Open-Meteo](https://open-meteo.com); maps © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.
- Reference and landing-page photos from [Wikimedia Commons](https://commons.wikimedia.org), credited where shown.
- The officer roster in `assets/officers.csv` is **fictional** demo data.

## License

The code is under the [MIT License](LICENSE). The reference data (Krishoker Janala, the pesticide
register, photos) belongs to its sources above and keeps their terms.

> [!IMPORTANT]
> KrishiBondhu is an AI assistant, not a replacement for your local agriculture officer. Always check
> chemical use, doses and safety with them before spraying.

<p align="center"><sub>Built with 🌾 for farmers of Bangladesh at the Meta Global AI Developer Hackathon 2026.</sub></p>
