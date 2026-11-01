# Krishi Advisor — web UI

Next.js chat UI for the Python agent. See the [root README](../README.md) for how to run both parts.

- `src/components/chat-app.tsx` + `src/lib/chat.ts` — `useChat` against the FastAPI app (same origin once built into `dist/`; `http://localhost:2024` under `npm run dev`, or `NEXT_PUBLIC_API_URL`), sidebar of the phone number's conversations.
- `src/components/assistant-reply.tsx` — renders the agent's openui-lang reply with OpenUI's `Renderer` and `openuiChatLibrary`; button and form actions are sent back as user messages.
- `src/components/profile-gate.tsx` + `src/lib/profile.ts` — sign-in form (name, division → district from `src/lib/bd-locations.ts`, area, phone), kept in localStorage. Name and location are sent with every run as `config.configurable` and land in the agent's system prompt.
- `src/components/genui/map.tsx` — custom `Map` / `MapMarker` OpenUI components (Leaflet + OpenStreetMap tiles), added to the chat library in `src/lib/library.ts`.
- `src/components/tool-activity.tsx` + `src/lib/narration.ts` — narrates each tool call ("Checking the 3-day forecast for Bogura" → "Checked the forecast for Bogura"). Add a narrator there when you add a tool.
- `src/lib/library.ts` — component library and extra prompt rules; `npm run generate:prompt` regenerates the backend system prompt from it.

`AGENTS.md` is OpenUI's guide for coding agents, added by the scaffold.
