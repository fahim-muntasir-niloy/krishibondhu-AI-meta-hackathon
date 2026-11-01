/**
 * Turns raw tool calls into plain-language Bangla activity lines, e.g.
 * "বগুড়ার ৩ দিনের আবহাওয়ার পূর্বাভাস দেখছি" → "বগুড়ার আবহাওয়া দেখা হয়েছে".
 */
import type { LucideIcon } from "lucide-react";
import { BookOpenCheck, Brain, CalendarCheck, ClipboardList, CloudSun, FlaskConical, Globe, ImagePlus, Images, MapPin, ScanSearch, Wrench } from "lucide-react";
import { bnDigits, term } from "./bn";

export type StepStatus = "running" | "done" | "error" | "stopped";

export type Narration = {
  icon: LucideIcon;
  title: string;
  detail?: string;
};

type Args = Record<string, unknown>;
type Narrator = (args: Args, status: StepStatus, result: unknown) => Narration;

const str = (v: unknown, fallback = "") => (typeof v === "string" && v.trim() ? v.trim() : fallback);
const quote = (v: unknown) => `“${str(v, "…")}”`;
const asArray = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v : []);

const narrators: Record<string, Narrator> = {
  search_crop_problems: (args, status, result) => {
    const crop = str(args.crop);
    if (status !== "done") return { icon: BookOpenCheck, title: `কৃষকের জানালায় ${crop ? `${crop}-এর ` : ""}সমস্যা খুঁজছি` };
    const hits = asArray((result as Args | undefined)?.results);
    return {
      icon: BookOpenCheck,
      title: hits.length ? `কৃষকের জানালায় ${bnDigits(hits.length)}টি মিল পাওয়া গেছে` : "কৃষকের জানালায় মিলে যায় এমন সমস্যা পাওয়া যায়নি",
      detail: hits.slice(0, 3).map((h) => str(h.problem)).join(" · ") || undefined,
    };
  },

  get_crop_problem: (_args, status, result) => {
    if (status !== "done") return { icon: BookOpenCheck, title: "কৃষকের জানালার পরামর্শ পড়ছি" };
    const r = (result ?? {}) as Args;
    const unregistered = Number(r.unregistered_in_advice ?? 0);
    return {
      icon: BookOpenCheck,
      title: `${str(r.problem, "সমস্যাটির")} সম্পর্কে পরামর্শ পড়া হয়েছে`,
      detail: unregistered
        ? `পরামর্শের ${bnDigits(unregistered)}টি ওষুধ এই ফসলের জন্য নিবন্ধিত নয়, সেগুলো বাদ`
        : "ওষুধগুলো DAE-র নিবন্ধিত তালিকার সাথে মেলানো হয়েছে",
    };
  },

  get_weather: (args, status, result) => {
    const place = str(args.location, "আপনার এলাকা");
    if (status !== "done")
      return { icon: CloudSun, title: `${place}-এর ${bnDigits(Number(args.days ?? 3))} দিনের আবহাওয়ার পূর্বাভাস দেখছি` };
    const days = asArray((result as Args | undefined)?.forecast);
    const labels = ["আজ", "আগামীকাল"];
    return {
      icon: CloudSun,
      title: `${place}-এর আবহাওয়া দেখা হয়েছে`,
      detail:
        days
          .slice(0, 2)
          .map((d, i) => `${labels[i]}: ${term(str(d.condition))}, বৃষ্টির সম্ভাবনা ${bnDigits(Number(d.rain_chance_pct))}%`)
          .join(" · ") || undefined,
    };
  },

  search_internet: (args, status, result) => {
    if (status !== "done") return { icon: Globe, title: `ইন্টারনেটে ${quote(args.query)} খুঁজছি` };
    const sources = asArray((result as Args | undefined)?.sources);
    return {
      icon: Globe,
      title: sources.length ? `ইন্টারনেটে ${bnDigits(sources.length)}টি উৎস পড়া হয়েছে` : "ইন্টারনেটে খোঁজা হয়েছে",
      detail: sources.map((s) => str(s.title)).join(" · ") || undefined,
    };
  },

  find_officer_slots: (args, status, result) => {
    const kind = term(str(args.session_type, "session"));
    if (status !== "done") return { icon: CalendarCheck, title: `আপনার এলাকার কৃষি কর্মকর্তার ${kind}-এর খালি সময় দেখছি` };
    const officers = typeof result === "string" ? [...result.matchAll(/officer_id: \S+ -- ([^,]+)/g)].map((m) => m[1]) : [];
    return {
      icon: CalendarCheck,
      title: officers.length ? "কৃষি কর্মকর্তার খালি সময় পাওয়া গেছে" : "এলাকার কৃষি কর্মকর্তা খুঁজে পাওয়া যায়নি",
      detail: officers.join(" · ") || undefined,
    };
  },

  book_officer_session: (args, status, result) => {
    const kind = term(str(args.session_type, "session"));
    if (status !== "done") return { icon: CalendarCheck, title: `কৃষি কর্মকর্তার সাথে ${kind} বুক করছি` };
    const id = typeof result === "string" ? result.match(/booking_id: (\S+)/)?.[1] : undefined;
    return { icon: CalendarCheck, title: `কৃষি কর্মকর্তার সাথে ${kind} বুক হয়েছে`, detail: id ? `বুকিং নং ${id}` : undefined };
  },

  change_officer_booking: (args, status) => {
    const cancel = args.action === "cancel";
    if (status !== "done") return { icon: CalendarCheck, title: cancel ? "সাক্ষাৎ বাতিল করছি" : "সাক্ষাতের সময় বদলাচ্ছি" };
    return { icon: CalendarCheck, title: cancel ? "সাক্ষাৎ বাতিল হয়েছে" : "সাক্ষাতের সময় বদলানো হয়েছে" };
  },

  create_or_update_user_memory: (args, status) => {
    if (args.forget) return { icon: Brain, title: status === "done" ? "একটি তথ্য ভুলে যাওয়া হয়েছে" : "তথ্যটি মুছে ফেলছি" };
    return status !== "done"
      ? { icon: Brain, title: "আপনার সম্পর্কে মনে রাখছি" }
      : { icon: Brain, title: "মনে রাখা হয়েছে", detail: str(args.content) || undefined };
  },

  fetch_user_memory: (_args, status) =>
    status !== "done"
      ? { icon: Brain, title: "আগের কথাবার্তা থেকে আপনার তথ্য দেখছি" }
      : { icon: Brain, title: "আপনার আগের তথ্য দেখা হয়েছে" },

  segment_image: (args, status, result) => {
    const labels = asArray(args.targets).map((t) => str(t.label)).filter(Boolean);
    if (status !== "done") return { icon: ScanSearch, title: `ছবিতে ${labels.join(", ") || "সমস্যা"} চিহ্নিত করছি` };
    const r = (result ?? {}) as Args;
    const found = asArray(r.found);
    const pct = (r.measurement as Args | undefined)?.lesion_pct;
    return found.length
      ? {
          icon: ScanSearch,
          title: typeof pct === "number" ? `পাতার ${bnDigits(pct)}% আক্রান্ত, মেপে দেখা হয়েছে` : "ছবিতে চিহ্নিত করা হয়েছে",
          detail: found.map((f) => `${str(f.label)}: ${bnDigits(Number(f.count))}টি`).join(" · "),
        }
      : { icon: ScanSearch, title: "ছবিতে চিহ্নিত করার মতো কিছু পাওয়া যায়নি" };
  },

  make_picture_card: (args, status, result) => {
    if (status !== "done") return { icon: ImagePlus, title: `ছবিতে বোঝানোর কার্ড আঁকছি: ${str(args.title, "কাজের নিয়ম")}` };
    return (result as Args | undefined)?.card_image_url
      ? { icon: ImagePlus, title: "ছবির কার্ড তৈরি হয়েছে", detail: str(args.title) || undefined }
      : { icon: ImagePlus, title: "ছবির কার্ড তৈরি করা গেল না" };
  },

  find_registered_pesticides: (args, status, result) => {
    const what = `${str(args.crop)}-এর ${str(args.pest, "সমস্যা")}`;
    if (status !== "done") return { icon: FlaskConical, title: `DAE-র নিবন্ধিত কীটনাশকের তালিকায় ${what}-এর ওষুধ খুঁজছি` };
    const r = (result ?? {}) as Args;
    const ingredients = asArray(r.ingredients);
    return {
      icon: FlaskConical,
      title: ingredients.length
        ? `${bnDigits(Number(r.total_products ?? 0))}টি নিবন্ধিত পণ্য, ${bnDigits(Number(r.total_ingredients ?? 0))}টি উপাদান পাওয়া গেছে`
        : `${what}-এর জন্য নিবন্ধিত কোনো ওষুধ পাওয়া যায়নি`,
      detail: ingredients.slice(0, 4).map((i) => str(i.active_ingredient)).join(" · ") || undefined,
    };
  },

  lookup_pesticide_product: (args, status, result) => {
    if (status !== "done") return { icon: FlaskConical, title: `নিবন্ধিত তালিকায় ${quote(args.query)} যাচাই করছি` };
    const products = asArray((result as Args | undefined)?.products);
    return products.length
      ? {
          icon: FlaskConical,
          title: `${str(products[0].brand)} নিবন্ধিত (${str(products[0].reg_no)})`,
          detail: `${str(products[0].active_ingredient)} · ${str(products[0].holder)}`,
        }
      : { icon: FlaskConical, title: `${quote(args.query)} নিবন্ধিত তালিকায় পাওয়া যায়নি` };
  },

  search_images: (args, status, result) => {
    const queries = Array.isArray(args.queries) ? args.queries.map((q) => str(q)).filter(Boolean) : [];
    if (status !== "done") return { icon: Images, title: `উইকিমিডিয়া কমন্সে ${queries.map(quote).join(", ") || "ছবি"} খুঁজছি` };
    const found = Object.values(((result as Args | undefined)?.images ?? {}) as Record<string, unknown>).flatMap(asArray);
    return {
      icon: Images,
      title: found.length ? `${bnDigits(found.length)}টি উদাহরণ ছবি পাওয়া গেছে` : "মিলে যায় এমন ছবি পাওয়া যায়নি",
      detail: found.map((img) => str(img.title)).join(" · ") || undefined,
    };
  },

  start_crop_case: (args, status) => {
    const problem = str(args.problem, "সমস্যা");
    if (status !== "done") return { icon: ClipboardList, title: `${problem}-এর চিকিৎসার পরিকল্পনা সাজাচ্ছি` };
    return {
      icon: ClipboardList,
      title: `${problem}-এর পরিকল্পনা তৈরি হয়েছে`,
      detail: `${bnDigits(asArray(args.steps).length)}টি ধাপ, পাশের প্যানেলে দেখুন`,
    };
  },

  start_cultivation_plan: (args, status) => {
    const title = str(args.title, "চাষের");
    if (status !== "done") return { icon: ClipboardList, title: `${title}: পরিকল্পনা সাজাচ্ছি` };
    return {
      icon: ClipboardList,
      title: `${title}: পরিকল্পনা তৈরি হয়েছে`,
      detail: `${bnDigits(asArray(args.steps).length)}টি ধাপ, পাশের প্যানেলে দেখুন`,
    };
  },

  update_crop_case: (_args, status) =>
    status !== "done"
      ? { icon: ClipboardList, title: "পরিকল্পনায় লিখে রাখছি" }
      : { icon: ClipboardList, title: "পরিকল্পনা আপডেট হয়েছে" },

  get_crop_case: (_args, status) =>
    status !== "done"
      ? { icon: ClipboardList, title: "আপনার পরিকল্পনা দেখছি" }
      : { icon: ClipboardList, title: "পরিকল্পনা দেখা হয়েছে" },

  geocode_location: (args, status, result) => {
    const place = str(args.place, "জায়গাটি");
    if (status !== "done") return { icon: MapPin, title: `ম্যাপে ${place} খুঁজছি` };
    const hit = asArray((result as Args | undefined)?.results)[0];
    return hit
      ? { icon: MapPin, title: `ম্যাপে ${place} পাওয়া গেছে`, detail: str(hit.display_name) || undefined }
      : { icon: MapPin, title: `ম্যাপে ${place} পাওয়া যায়নি` };
  },
};

export function narrate(name: string, args: Args, status: StepStatus, result: unknown): Narration {
  const narration = (narrators[name] ?? fallback(name))(args, status, result);
  if (status === "error") return { ...narration, detail: "এই ধাপে একটি সমস্যা হয়েছে" };
  if (status === "stopped") return { ...narration, detail: "থামানো হয়েছে" };
  return narration;
}

const fallback =
  (name: string): Narrator =>
  (_args, status) => ({
    icon: Wrench,
    title: status === "done" ? `${name.replaceAll("_", " ")} ব্যবহার করা হয়েছে` : `${name.replaceAll("_", " ")} ব্যবহার করছি`,
  });
