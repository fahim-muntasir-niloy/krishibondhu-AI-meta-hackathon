Build me a cinematic, auto-playing **90-second** product video as a single self-contained React artifact. Make it 16:9 and fill the window. It plays from start to finish on its own, with a pause/play button, a scrubbable progress bar and a replay button at the end. I'll screen-record it, so it has to look like a polished product launch film. No placeholder text and no external image URLs: draw everything with CSS/SVG.

# The product
**KrishiBondhu.AI (কৃষিবন্ধু)**: "কৃষকের ডিজিটাল বন্ধু", the farmer's digital friend. It's a Bangla AI crop-health advisor for Bangladeshi farmers. A farmer sends a photo or speaks in Bangla and gets a treatment plan from official government sources. The agent follows up day by day, books a real agriculture officer when needed, and **remembers each farmer**. Powered by Meta's **Muse**, **SAM 3.1** and **Meta ASR**, on LangGraph, with Postgres row-level security.

# Style
- Colours: brand green #1f7a4d, light green #4cc38a, mint #e3f2e9, ink #08130d, paddy gold #e9b949.
- Font: "Anek Bangla" (Google Fonts) for all text. Use Bangla numerals in the app UI.
- Logo: a sprout (two leaves) in a rounded green square, plus the wordmark "KrishiBondhu.AI".
- Feel: warm, hopeful, human, like a product film set in rural Bangladesh. Fast, smooth easing, quick cuts and no dead air.
- The app is shown inside a phone mockup with chat bubbles, live tool steps (spinner → ✓) and rich cards.
- Captions at the bottom: Bangla on top, English underneath, smaller.

# Story: one farmer, রহিম চাচা (Rahim Chacha), a rice farmer in বগুড়া

**1. Hook (0–8s)**
Dawn over paddy fields; zoom into a rice leaf with brown "eye" spots. Caption: "ধানের পাতায় দাগ… এখন কী করবেন?" / "Spots on the rice. Now what?" The sprout logo grows from the soil, then the wordmark and tagline appear with three badges: Muse · SAM 3.1 · Meta ASR.

**2. Voice + photo (8–16s)**
Rahim holds the mic (push-to-talk). A waveform pulses and a Bangla transcript types itself: "আমার ধানের পাতায় চোখের মতো দাগ পড়ছে। কী করব?" He attaches the leaf photo and sends it. Caption: "বাংলায় বলুন" / "Just speak Bangla."

**3. The agent at work (16–40s): the core scene**
Narrated tool steps stack up in the chat, each ticking from spinner to ✓, with the label changing from "…খুঁজছি" to "…খোঁজা হয়েছে":
- 🧠 "আগের কথাবার্তা থেকে আপনার তথ্য দেখছি" (memory)
- 🔍 "ছবিতে দাগ খুঁজছি" (SAM 3.1): labelled boxes snap around each lesion: "ব্লাস্ট রোগের দাগ"
- 📖 "কৃষকের জানালায় ধান-এর সমস্যা খুঁজছি": a card for "ধানের ব্লাস্ট রোগ" with source Krishoker Janala (DAE), "998 problems · 122 crops"
- 🧪 "DAE-র নিবন্ধিত কীটনাশকের তালিকায় ওষুধ খুঁজছি": pesticide cards (ingredient, dose per bigha, WHO hazard chip), then a red warning: "this product is registered for tea, NOT rice — not recommended"
- 🌤️ "বগুড়ার আবহাওয়ার পূর্বাভাস দেখছি": a mini rain chart highlighting "স্প্রে করার ভালো দিন: বৃহস্পতিবার"
- 🖼️ Reference photos from Wikimedia Commons, and 🌐 web sources as small chips
Caption: "সরকারি তথ্য, শুধু নিবন্ধিত কীটনাশক" / "Official advice. Only registered pesticides."

**4. Plan → officer (40–56s)**
A treatment timeline pane slides open with a progress ring: Day 0 spray, Day 3 send a photo, Day 7 check new leaves. Jump to Day 3: Rahim taps "খারাপ" (worse), and the ring turns amber. Officer time slots appear (Sun–Thu, ১০:০০ / ১১:০০ / ১৪:০০), he taps one, and a booking card lands: "উপজেলা কৃষি কর্মকর্তা, বগুড়া — ফোন কল" with a call button. Caption: "দরকার হলে আসল মানুষ" / "A real officer when it matters."

**5. IT REMEMBERS YOU (56–74s): the emotional peak, so give it the most polish**
Caption card: "কয়েক সপ্তাহ পর…" / "Weeks later…". Rahim says: "এবার বোরো লাগাব।" A glowing memory panel unfolds and chips float in one by one:
- "রহিম · বগুড়া, শাজাহানপুর"
- "জমি: ২ বিঘা, দোআঁশ মাটি"
- "গত আমনে ব্লাস্ট — ৭ দিনে সেরেছে"
- "পছন্দ: ফোনে কথা বলা"
The agent replies: "রহিম চাচা, গতবার আপনার জমিতে ব্লাস্ট হয়েছিল — এবার আগে থেকেই সাবধান থাকি।" He says "আমার জমি এখন ৩ বিঘা" and the chip updates live: "২" strikes through and becomes "৩". Then a Boro season timeline unrolls through its phases (বীজতলা → রোপণ → কুশি → থোড় → পাকা), with a "BRRI" source chip on each fertiliser dose. Caption: "আপনাকে মনে রাখে" / "It remembers you: your land, your crops, last season."

**Scene 6. Grow, not just cure: cultivation plan (118–130s)**
🌱 start_cultivation_plan: a full Boro rice season timeline unrolls left to right in phases (বীজতলা → রোপণ → কুশি → থোড় → পাকা), with fertiliser steps "ইউরিয়া ১ম কিস্তি — দিন ১৫" and a source chip "BRRI" on every dose. Then a quick 🗺️ map moment (geocode_location): an OpenStreetMap-style map of Bogura with pins for his field and the Upazila agriculture office.

**Scene 7. Private by design (130–138s)**
Abstract visual: many farmers' data as separate glowing locked vaults. A query beam tries to cross from one vault to another and bounces off. Caption: "প্রতিটি কৃষকের তথ্য আলাদা ও সুরক্ষিত" / "Each farmer's data isolated with Postgres row-level security."

**Scene 8. Finale (138–150s)**
Pull back from the phone to golden-hour fields, now healthy and swaying, with Rahim smiling silhouetted against the sun. A quick grid flashes all the capabilities as icons: 📸 sees · 📚 official sources · 🧪 registered pesticides · 🌤️ weather · 🗓️ plans · 👩‍🌾 officer · 🎙️ voice · 🧠 memory · 🔒 private. Logo and tagline land, then: "Built with Muse · SAM 3.1 · Meta ASR · LangGraph" and "Meta Global AI Developer Hackathon 2026". End with the replay button.

# Technical requirements
- Use a central timeline (scene start/end times) with requestAnimationFrame or CSS keyframes, plus a pause/play button and a scrubbable progress bar, so I can re-record any part.
- Phone mockup: realistic rounded frame, status bar, a chat header "KrishiBondhu" with the sprout avatar, light theme in brand colours.
- Tool steps must animate: spinner → ✓, the Bangla label changing from present tense (…খুঁজছি) to done (…খোঁজা হয়েছে).
- The SAM box overlay, the memory chips, the timeline progress ring and the pesticide warning are the hero animations. Spend the most polish on them.
- All Bangla must render correctly (load Anek Bangla). Use Bangla numerals in the app UI (১, ২, ৩).
- Optional: a subtle ambient sound toggle (generated with WebAudio, soft and pastoral), off by default.
- The officer and all people are fictional. Pesticide doses are illustrative.