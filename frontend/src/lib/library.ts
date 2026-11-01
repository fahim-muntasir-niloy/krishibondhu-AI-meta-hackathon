/**
 * Component library the agent writes openui-lang against.
 * `npm run generate:prompt` turns it into the backend system prompt
 * (src/meta_hackathon/prompts/openui_prompt.md) — rerun after changing this file.
 */
import { openuiChatLibrary } from "@openuidev/react-ui/genui-lib";
import { openuiChatPromptOptions } from "@openuidev/react-ui/genui-lib/prompt-options";
import { createLibrary, defineComponent, type PromptOptions } from "@openuidev/react-lang";
import { chartRenderers } from "@/components/genui/charts";
import { BentoGrid, BentoItem } from "@/components/genui/bento";
import { GeoMap, MapMarker } from "@/components/genui/map";
import { PesticideCard, PesticideCards } from "@/components/genui/pesticide";

// The stock charts with renderers that follow the app's theme (see charts.tsx); same props.
const charts = Object.entries(chartRenderers).map(([name, component]) => {
  const stock = openuiChatLibrary.components[name];
  return defineComponent({ name, props: stock.props, description: stock.description, component });
});

// The stock library minus its advice to use placeholder image services: every image comes
// from search_images, get_crop_problem or segment_image.
const stock = createLibrary({
  root: openuiChatLibrary.root,
  components: Object.values(openuiChatLibrary.components),
  componentGroups: openuiChatLibrary.componentGroups?.map((group) => ({
    ...group,
    notes: group.notes?.filter((note) => !/picsum/i.test(note)),
  })),
});

// Created at module scope: parsers memoize by library identity.
export const library = stock.extend({
  components: {
    add: [
      { component: GeoMap, slots: ["Card.children", "TabItem.content"] },
      MapMarker,
      { component: BentoGrid, slots: ["Card.children", "TabItem.content"] },
      BentoItem,
      { component: PesticideCards, slots: ["Card.children", "TabItem.content"] },
      PesticideCard,
    ],
    override: charts,
  },
});

export const promptOptions: PromptOptions = {
  ...openuiChatPromptOptions,
  additionalRules: [
    ...(openuiChatPromptOptions.additionalRules ?? []),
    "Write all user-facing text in simple Bangla, including headings, buttons, form labels, placeholders and follow-ups, even if the farmer writes in English. Keep it short and practical.",
    "When you recommend a pesticide (from get_crop_problem or find_registered_pesticides), show the 1-3 choices as PesticideCards (never a Table), each PesticideCard filled from that tool's result, with hazard copied from human_hazard.who_class and hazardNote from human_hazard.note; when the most hazardous choice is class Ia/Ib, put a safer registered one first and say why. When the Krishoker Janala advice names a chemical that is not registered for this crop, say so in a warning Callout and never show it as a PesticideCard. Add the DAE register as a Card source (no url). When advice comes from get_crop_problem, add কৃষকের জানালা as a Card source with its source_url; from search_internet, pass those results as Card sources. Cite sources inline as [1], [2]. Only set a source url if the tool result contains one; never invent URLs.",
    "For a diagnosis, lead with a Callout naming the likely problem and your confidence, then numbered Steps for what to do.",
    "Images come only from tool results: segment_image's annotated_image_url, make_picture_card's card_image_url, get_crop_problem's reference_photos and search_images. Never write an image URL yourself. Show reference photos (get_crop_problem's first, they are the official ones for the problem; search_images only when those are missing or do not help) in a BentoGrid (even a single photo; never ImageBlock or Image for them), one BentoItem per photo (the clearest first, it is shown large): Bangla title and one-line description of what to notice, image = url; credit and source as the BentoItem description says. Do not repeat the credits in text. Use reference photos to help the farmer recognise a problem, next to their own annotated photo when there is one (that one with ImageBlock).",
    "When a tool returns an image URL, show it with Image or ImageBlock. After segment_image, show its annotated_image_url near the top with ImageBlock, then explain each marked label in plain words (what it is, how serious), and give measurement.pest_count as the number of insects and measurement.lesion_pct as the share of the leaf affected when they are there (never 0%).",
    "After make_picture_card, show its card_image_url with ImageBlock right after the advice it illustrates; do not repeat its captions as a list.",
    "Show weather charts only when the farmer asks about the weather or forecast. When you checked the weather just to time advice (spraying, fertiliser, harvest) or for a diagnosis, do not show charts; say it in one or two sentences or a Callout (e.g. \"কাল বৃষ্টি হবে, পরশু স্প্রে করুন\"). When weather charts are shown: never as a Table. Use Tabs with two TabItems: \"আগামী ২৪ ঘণ্টা\" (labels from next_24h[].label: LineChart of temp_c, and BarChart of rain_chance_pct) and \"দৈনিক পূর্বাভাস\" (labels from forecast[].label: LineChart with two Series, সর্বোচ্চ and সর্বনিম্ন temperature, and BarChart of rain_chance_pct; add rain_mm as a second BarChart Series when it rains). Put the tab for the farmer's question first. Use the \"natural\" variant for lines, Bangla Series names and axis labels with units (°সে, %, মিমি). Before the charts, say in one Callout whether the coming hours/days suit the planned field work.",
    "Use a Map only when it shows something beyond the farmer's own location: two or more places (farmer and the officer's office after a booking, nearby markets, places being compared), or an area such as an outbreak zone (radiusKm). Never add a Map that is just a single pin of the farmer's area unless they ask to see it on a map. Reuse lat/lng from a get_weather result's place; call geocode_location only for places not located yet. Never guess coordinates. Label pins in Bangla.",
    "When you need details from the farmer (location, crop, booking date, session type), ask with a Form instead of plain questions.",
    // OpenUI's `required` validator treats Date objects as empty, so a required DatePicker can never submit.
    "Never put validation rules on a DatePicker.",
    "After book_officer_session or change_officer_booking, the app shows the booking as a card under your reply: do not repeat it as a Card; say in a sentence or two what happens next and what to have ready.",
    "End every reply with a FollowUpBlock of 2-3 short next questions the farmer is likely to ask.",
  ],
};
