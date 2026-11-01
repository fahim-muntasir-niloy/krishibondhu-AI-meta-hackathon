"use client";

import type { ActionEvent } from "@openuidev/react-lang";
import { ThemeProvider, useThemeModePreference } from "@openuidev/react-ui";
import {
  AlertTriangle,
  CalendarCheck,
  ClipboardList,
  FlaskConical,
  Leaf,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  Pin,
  PinOff,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Sprout,
  Sun,
  Target,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AssistantReply } from "@/components/assistant-reply";
import { BookingCard, BookingList } from "@/components/bookings";
import { CasePane } from "@/components/case-pane";
import { Composer, type ComposerHandle } from "@/components/composer";
import { IconTile, type Tone } from "@/components/icon-tile";
import { PhotoFolder } from "@/components/photo-folder";
import { PlanFolder } from "@/components/plan-folder";
import { PaneResizer, usePaneWidth } from "@/components/pane-resizer";
import { ToolActivity } from "@/components/tool-activity";
import { UserMessage } from "@/components/user-message";
import { bnDigits } from "@/lib/bn";
import { BOOKING_TOOLS, type Booking, cancelBooking, isBooking, listBookings } from "@/lib/bookings";
import { CASE_TOOLS, type CropCase, deleteCase, isCase, listCases, updateCase, updateStep } from "@/lib/cases";
import { API_URL } from "@/lib/config";
import { deleteThread, listThreads, pinThread, type Thread, useChat } from "@/lib/chat";
import { type GalleryImage, listImages } from "@/lib/gallery";
import { decodeFormMessage, encodeFormMessage, flattenFormState, withDetails } from "@/lib/form-message";
import { imageBlock } from "@/lib/images";
import { placeLabel, profileContext, type Profile } from "@/lib/profile";
import { buildTurns, type Step } from "@/lib/turns";

const SIDEBAR_KEY = "krishi.sidebar";

const BRAND = { light: "#1f7a4d", dark: "#4cc38a" };

// Inter for Latin, Anek Bangla for Bangla — also inside OpenUI-rendered replies.
const FONT_STACK = "var(--font-inter), var(--font-bangla), sans-serif";
const FONTS = { fontBody: FONT_STACK, fontHeading: FONT_STACK, fontLabel: FONT_STACK };

const STARTERS: { icon: typeof Leaf; tone: Tone; title: string; prompt: string }[] = [
  {
    icon: Leaf,
    tone: "green",
    title: "ধানের পাতায় দাগ",
    prompt: "আমার ধানের পাতায় চোখের মতো দাগ পড়ছে। কী করব?",
  },
  {
    icon: FlaskConical,
    tone: "cyan",
    title: "বোরো ধানে কবে কোন সার",
    prompt: "আমি ২ বিঘায় বোরো ধান লাগাব। কবে কোন সার কতটা দিতে হবে, একটা পরিকল্পনা করে দিন।",
  },
  {
    icon: Sprout,
    tone: "yellow",
    title: "মাশরুম চাষ শুরু",
    prompt: "আমি ঘরে ঝিনুক মাশরুম চাষ শুরু করতে চাই। ধাপে ধাপে কবে কী করতে হবে?",
  },
  {
    icon: CalendarCheck,
    tone: "magenta",
    title: "কৃষি অফিসারের সাথে কথা",
    prompt: "আমি আমার এলাকার কৃষি অফিসারের সাথে একটি সেশন বুক করতে চাই।",
  },
];

export function ChatApp({ profile, onSignOut }: { profile: Profile; onSignOut: () => void }) {
  const { mode, setPreference } = useThemeModePreference();
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  return (
    <ThemeProvider
      mode={mode}
      lightTheme={{ ...FONTS, interactiveAccentDefault: BRAND.light, textBrand: BRAND.light }}
      darkTheme={{ ...FONTS, interactiveAccentDefault: BRAND.dark, textBrand: BRAND.dark }}
    >
      <Chat
        profile={profile}
        onSignOut={onSignOut}
        mode={mode}
        onToggleTheme={() => setPreference(mode === "dark" ? "light" : "dark")}
      />
    </ThemeProvider>
  );
}

type ChatProps = {
  profile: Profile;
  onSignOut: () => void;
  mode: "light" | "dark";
  onToggleTheme: () => void;
};

function Chat({ profile, onSignOut, mode, onToggleTheme }: ChatProps) {
  const { phone, name } = profile;
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);

  // The farmer's crop cases, and the one open in the tracker pane (messages are then about it).
  const [cases, setCases] = useState<CropCase[]>([]);
  const [openCaseId, setOpenCaseId] = useState<string | null>(null);
  const openCase = cases.find((c) => c.id === openCaseId) ?? null;
  const [paneWidth, setPaneWidth] = usePaneWidth();
  // Desktop: the sidebar folds to an icon rail (remembered). Phones: it opens as a drawer.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === "collapsed";
    } catch {
      return false;
    }
  });
  const toggleSidebar = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem(SIDEBAR_KEY, c ? "open" : "collapsed");
      } catch {
        // Not remembered; still works.
      }
      return !c;
    });
  const [drawerOpen, setDrawerOpen] = useState(false);
  /** From the rail: unfold it, unless the plan pane leaves no room (narrower screens), then as a drawer. */
  const expandSidebar = () => {
    if (!collapsed || (openCaseId && window.matchMedia("(max-width: 1280px)").matches)) setDrawerOpen(true);
    else toggleSidebar();
  };
  /** Every pick in the sidebar also closes the drawer on phones. */
  const openThread = (id: string | null) => {
    setThreadId(id);
    setDrawerOpen(false);
  };
  const composerRef = useRef<ComposerHandle>(null);

  const context = useMemo(
    () => ({ ...profileContext(profile), ...(openCase ? { case_id: openCase.id } : {}) }),
    [profile, openCase],
  );

  const refreshThreads = useCallback(() => {
    listThreads(phone)
      .then(setThreads)
      .catch(() => setThreads([]));
  }, [phone]);
  useEffect(refreshThreads, [refreshThreads]);

  const refreshCases = useCallback(() => {
    listCases(phone)
      .then(setCases)
      .catch(() => {
        // The tracker stays as it was; chat still works.
      });
  }, [phone]);
  useEffect(refreshCases, [refreshCases]);

  // Photos KrishiBondhu marked up, for the sidebar's photo folder.
  const [images, setImages] = useState<GalleryImage[]>([]);
  const refreshImages = useCallback(() => {
    listImages(phone)
      .then(setImages)
      .catch(() => {
        // The folder stays as it was; chat still works.
      });
  }, [phone]);
  useEffect(refreshImages, [refreshImages]);

  // Sessions booked with an officer, for the sidebar and the cards under replies.
  const [bookings, setBookings] = useState<Booking[]>([]);
  const refreshBookings = useCallback(() => {
    listBookings(phone)
      .then(setBookings)
      .catch(() => {
        // The list stays as it was; chat still works.
      });
  }, [phone]);
  useEffect(refreshBookings, [refreshBookings]);

  const onCancelBooking = useCallback(
    async (b: Booking) => {
      const updated = await cancelBooking(phone, b.id);
      setBookings((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      // A booking for a case is logged on the case too.
      if (b.case_id) refreshCases();
    },
    [phone, refreshCases],
  );

  const upsertCase = useCallback((c: CropCase) => {
    setCases((prev) => [c, ...prev.filter((x) => x.id !== c.id)]);
  }, []);

  const onThreadCreated = useCallback(
    (id: string) => {
      setThreadId(id);
      refreshThreads();
    },
    [refreshThreads],
  );
  const onFinished = useCallback(() => {
    refreshThreads();
    refreshCases();
    refreshImages();
    refreshBookings();
  }, [refreshThreads, refreshCases, refreshImages, refreshBookings]);
  const stream = useChat({ phone, threadId, onThreadCreated, onFinished });

  const onPinThread = async (t: Thread) => {
    await pinThread(phone, t.thread_id, !t.pinned);
    refreshThreads();
  };
  const [threadError, setThreadError] = useState<string | null>(null);
  const onDeleteThread = async (t: Thread) => {
    // Gone at once; a failure brings it back with a message.
    setThreadError(null);
    setThreads((prev) => prev.filter((x) => x.thread_id !== t.thread_id));
    if (t.thread_id === threadId) setThreadId(null);
    try {
      await deleteThread(phone, t.thread_id);
    } catch {
      setThreadError(`“${t.title ?? "নতুন কথোপকথন"}” মুছতে পারিনি। আবার চেষ্টা করুন।`);
    }
    refreshThreads();
  };

  const turns = useMemo(() => buildTurns(stream.messages, stream.isLoading), [stream.messages, stream.isLoading]);
  const lastTurn = turns.at(-1);
  const waiting =
    stream.isLoading && (lastTurn?.kind === "user" || (lastTurn?.kind === "assistant" && !lastTurn.reply && !lastTurn.steps.some((s) => s.status === "running")));

  // The newest case a tool returned opens the pane, once, if it came in during a run. Cases in
  // a thread's history may be out of date, so those come from /v1/cases instead.
  const latestCase = turns
    .flatMap((t) => (t.kind === "assistant" ? t.steps : []))
    .findLast((s) => s.status === "done" && CASE_TOOLS.has(s.name) && isCase(s.artifact));
  const [handledStep, setHandledStep] = useState<string | null>(null);
  if (latestCase && latestCase.id !== handledStep && isCase(latestCase.artifact)) {
    setHandledStep(latestCase.id);
    if (stream.isLoading) {
      upsertCase(latestCase.artifact);
      setOpenCaseId(latestCase.artifact.id);
    }
  }

  // A finished run must end with something to read; otherwise tell the farmer.
  const noReply =
    !stream.isLoading &&
    stream.error == null &&
    (lastTurn?.kind === "user" || (lastTurn?.kind === "assistant" && !lastTurn.reply));

  const send = useCallback(
    (text: string, images: string[] = []) => {
      // Photos go as image_url content blocks next to the text (Muse reads them directly).
      const content = images.length
        ? [...(text ? [{ type: "text" as const, text }] : []), ...images.map(imageBlock)]
        : text;
      // Name, place and the open case go into the system prompt (UserContext).
      void stream.submit(content, context, newThreadTitle(text, images.length > 0));
    },
    [stream, context],
  );

  const onAction = useCallback(
    (event: ActionEvent) => {
      if (event.type === "open_url" && typeof event.params.url === "string") {
        window.open(event.params.url, "_blank", "noopener,noreferrer");
      } else if (event.type === "continue_conversation") {
        const label = String(event.params.message ?? event.humanFriendlyMessage ?? "").trim();
        if (label) send(encodeFormMessage(label, flattenFormState(event.formState)));
      }
    },
    [send],
  );

  // Keep the newest content in view while streaming, unless the reader scrolled up.
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [stream.messages, waiting]);

  const showCases = () => setOpenCaseId(openCaseId ? null : (cases[0]?.id ?? null));
  const shellClass = ["shell", openCase && "with-pane", collapsed && "sidebar-collapsed", drawerOpen && "drawer-open"].filter(Boolean).join(" ");

  return (
    <div
      className={shellClass}
      style={openCase && paneWidth ? ({ "--pane-width": `${paneWidth}px` } as React.CSSProperties) : undefined}
    >
      {drawerOpen && <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden />}
      <aside className="sidebar" id="sidebar">
        <nav className="sidebar-rail" aria-label="সাইডবার">
          <button type="button" className="icon-btn" onClick={expandSidebar} aria-label="সাইডবার খুলুন" title="সাইডবার খুলুন">
            <PanelLeftOpen size={18} />
          </button>
          <span className="brand-mark" aria-hidden>
            <Sprout size={18} />
          </span>
          <button type="button" className="icon-btn" onClick={() => openThread(null)} aria-label="নতুন কথোপকথন" title="নতুন কথোপকথন">
            <Plus size={18} />
          </button>
          {cases.length > 0 && (
            <button type="button" className="icon-btn badge-btn" onClick={showCases} aria-label="পরিকল্পনা" title="পরিকল্পনা">
              <ClipboardList size={18} />
              <span className="badge">{bnDigits(cases.length)}</span>
            </button>
          )}
          <span className="rail-spacer" />
          <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label="থিম পরিবর্তন" title="থিম পরিবর্তন">
            {mode === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button type="button" className="icon-btn" onClick={onSignOut} aria-label="প্রোফাইল পরিবর্তন" title="প্রোফাইল পরিবর্তন">
            <LogOut size={16} />
          </button>
        </nav>
        <div className="sidebar-full">
          <div className="brand">
            <span className="brand-mark" aria-hidden>
              <Sprout size={18} />
            </span>
            <div className="brand-text">
              <div className="brand-name">KrishiBondhu.AI</div>
              <div className="brand-sub">কৃষকের ডিজিটাল বন্ধু</div>
            </div>
            <button type="button" className="icon-btn sidebar-collapse" onClick={toggleSidebar} aria-label="সাইডবার বন্ধ করুন" title="সাইডবার বন্ধ করুন">
              <PanelLeftClose size={18} />
            </button>
            <button type="button" className="icon-btn drawer-close" onClick={() => setDrawerOpen(false)} aria-label="বন্ধ করুন">
              <X size={18} />
            </button>
          </div>
          <button type="button" className="new-chat" onClick={() => openThread(null)}>
            <Plus size={16} /> নতুন কথোপকথন
          </button>
          <PlanFolder
            cases={cases}
            openId={openCaseId}
            onOpen={(id) => {
              setOpenCaseId(id);
              setDrawerOpen(false);
            }}
          />
          <BookingList bookings={bookings} onCancel={onCancelBooking} onOpenCase={setOpenCaseId} />
          <PhotoFolder images={images} onOpenThread={openThread} />
          <div className="sidebar-label">কথোপকথন</div>
          <nav className="thread-list" aria-label="কথোপকথন">
            {threadError && (
              <p className="thread-error" role="alert">
                {threadError}
              </p>
            )}
            {threads.length === 0 && <p className="thread-empty">আপনার কথোপকথনগুলো এখানে দেখা যাবে।</p>}
            {threads.map((t) => (
              <ThreadItem
                key={t.thread_id}
                thread={t}
                current={t.thread_id === threadId}
                onOpen={() => openThread(t.thread_id)}
                onPin={() => void onPinThread(t)}
                onDelete={() => void onDeleteThread(t)}
              />
            ))}
          </nav>
          <div className="sidebar-foot">
            <span className="phone-chip" title={placeLabel(profile)}>
              <span className="profile-name">{name}</span>
              {bnDigits(phone)}
            </span>
            <button type="button" className="icon-btn" onClick={onToggleTheme} aria-label="থিম পরিবর্তন">
              {mode === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button type="button" className="icon-btn" onClick={onSignOut} aria-label="প্রোফাইল পরিবর্তন">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      <main className="main">
        <header className="mobile-header">
          <button
            type="button"
            className="icon-btn"
            onClick={() => setDrawerOpen(true)}
            aria-label="মেনু"
            aria-controls="sidebar"
            aria-expanded={drawerOpen}
          >
            <Menu size={18} />
          </button>
          <span className="brand-mark" aria-hidden>
            <Sprout size={16} />
          </span>
          <span className="brand-name">KrishiBondhu.AI</span>
          {cases.length > 0 && (
            <button type="button" className="icon-btn badge-btn" onClick={showCases} aria-label="পরিকল্পনা">
              <ClipboardList size={18} />
              <span className="badge">{bnDigits(cases.length)}</span>
            </button>
          )}
          <button type="button" className="icon-btn" onClick={() => setThreadId(null)} aria-label="নতুন কথোপকথন">
            <Plus size={18} />
          </button>
        </header>

        <div
          className="scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          <div className="thread">
            {turns.length === 0 && !stream.isThreadLoading ? (
              <Welcome onPick={send} />
            ) : (
              turns.map((turn, i) =>
                turn.kind === "user" ? (
                  <UserMessage key={turn.id} text={turn.text} images={turn.images} />
                ) : (
                  <div key={turn.id} className="assistant-turn">
                    <ToolActivity steps={turn.steps} />
                    {turn.reply && (
                      <AssistantReply
                        text={turn.reply}
                        isStreaming={stream.isLoading && i === turns.length - 1}
                        onAction={onAction}
                      />
                    )}
                    <CaseCards steps={turn.steps} cases={cases} openId={openCaseId} onOpen={setOpenCaseId} />
                    <BookingCards steps={turn.steps} bookings={bookings} onCancel={onCancelBooking} onOpenCase={setOpenCaseId} />
                  </div>
                ),
              )
            )}
            {waiting && <Thinking />}
            {stream.error != null && !stream.isLoading && <ErrorNote error={stream.error} />}
            {noReply && turns.length > 0 && !stream.isThreadLoading && (
              <Note>কোনো উত্তর পাওয়া যায়নি। অনুগ্রহ করে আবার চেষ্টা করুন।</Note>
            )}
          </div>
        </div>

        <div className="composer-wrap">
          {openCase && (
            <div className="focus-chip">
              <IconTile icon={Target} tone="green" size="s" />
              <span className="focus-label">যে বিষয়ে কথা হচ্ছে</span>
              <button type="button" className="focus-name" onClick={() => setOpenCaseId(openCase.id)}>
                {openCase.problem}
              </button>
              <button type="button" className="icon-btn" onClick={() => setOpenCaseId(null)} aria-label="এই পরিকল্পনা নিয়ে কথা বন্ধ করুন">
                <X size={14} />
              </button>
            </div>
          )}
          <Composer ref={composerRef} phone={phone} onSend={send} onStop={() => void stream.stop()} isLoading={stream.isLoading} />
          <p className="disclaimer">পরামর্শটি BRRI / DAE নির্দেশিকা থেকে AI দিয়ে তৈরি। রাসায়নিক ব্যবহারের আগে স্থানীয় কৃষি অফিসারের সাথে কথা বলুন।</p>
        </div>
      </main>

      {openCase && (
        <>
          <PaneResizer onResize={setPaneWidth} />
          <CasePane
            crop={openCase}
            cases={cases}
            busy={stream.isLoading}
            onSelect={setOpenCaseId}
            onClose={() => setOpenCaseId(null)}
            onAsk={(text, details) => send(withDetails(text, details))}
            onPhoto={(_crop, step) => composerRef.current?.pickPhotos(`"${step.title}": নতুন ছবি পাঠালাম। গাছ এখন কেমন?`)}
            onUpdateStep={async (crop, step, patch) => upsertCase(await updateStep(phone, crop.id, step.id, patch))}
            onUpdateCase={async (crop, patch) => upsertCase(await updateCase(phone, crop.id, patch))}
            onDelete={async (crop) => {
              await deleteCase(phone, crop.id);
              setCases((prev) => prev.filter((c) => c.id !== crop.id));
              setOpenCaseId(null);
            }}
          />
        </>
      )}
    </div>
  );
}

/** A link to each case a turn started or changed, under the reply. */
function CaseCards({
  steps,
  cases,
  openId,
  onOpen,
}: {
  steps: Step[];
  cases: CropCase[];
  openId: string | null;
  onOpen: (id: string) => void;
}) {
  const ids = [
    ...new Set(
      steps
        .filter((s) => s.status === "done" && (s.name === "start_crop_case" || s.name === "start_cultivation_plan" || s.name === "update_crop_case"))
        .map((s) => (isCase(s.artifact) ? s.artifact.id : String(s.args.case_id ?? "")))
        .filter(Boolean),
    ),
  ];
  return ids.map((id) => {
    const c = cases.find((x) => x.id === id);
    if (!c) return null;
    const open = id === openId;
    return (
      <button key={id} type="button" className="case-card" aria-pressed={open} onClick={() => onOpen(id)}>
        <IconTile icon={ClipboardList} tone="green" />
        <span>
          <strong>{c.problem}</strong>
          <span className="sub">
            {bnDigits(c.progress.total)}টির মধ্যে {bnDigits(c.progress.done)}টি ধাপ সম্পন্ন ·{" "}
            {open ? "পাশের প্যানেলে খোলা" : "সময়রেখা দেখুন"}
          </span>
        </span>
      </button>
    );
  });
}

/** The booking a turn made or changed, under the reply: as it is now if the list has it. */
function BookingCards({
  steps,
  bookings,
  onCancel,
  onOpenCase,
}: {
  steps: Step[];
  bookings: Booking[];
  onCancel: (b: Booking) => Promise<void>;
  onOpenCase: (id: string) => void;
}) {
  const latest = new Map<string, Booking>();
  for (const s of steps) {
    if (s.status === "done" && BOOKING_TOOLS.has(s.name) && isBooking(s.artifact)) latest.set(s.artifact.id, s.artifact);
  }
  return [...latest.values()].map((b) => (
    <BookingCard key={b.id} booking={bookings.find((x) => x.id === b.id) ?? b} onCancel={onCancel} onOpenCase={onOpenCase} />
  ));
}

function Welcome({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <section className="welcome">
      <span className="brand-mark brand-mark-lg" aria-hidden>
        <Sprout size={26} />
      </span>
      <h1>আসসালামু আলাইকুম! আজ আপনার ফসলের জন্য কী করতে পারি?</h1>
      <p>মাঠে যা দেখছেন তা লিখুন বা ছবি দিন। আমি সমস্যা চিনে চিকিৎসা, বা নতুন কিছু চাষের পরিকল্পনা দিনে দিনে সাজিয়ে দেব, আর দরকার হলে কৃষি অফিসারের সাথে সময় ঠিক করে দেব।</p>
      <div className="starters">
        {STARTERS.map(({ icon, tone, title, prompt }) => (
          <button key={title} type="button" className="starter" onClick={() => onPick(prompt)}>
            <IconTile icon={icon} tone={tone} />
            <span className="starter-title">{title}</span>
            <span className="starter-prompt">{prompt}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function Thinking() {
  return (
    <div className="thinking" role="status">
      <span className="dot" />
      <span className="dot" />
      <span className="dot" />
      <span className="shimmer">ভাবছি…</span>
    </div>
  );
}

function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  const filtered = /content_policy|content management policy/i.test(message);
  const unreachable = /failed to fetch|networkerror|load failed|ECONNREFUSED/i.test(message);
  return (
    <Note>
      {filtered
        ? "এই বার্তাটি AI সেবাদাতার নিরাপত্তা ফিল্টারে আটকে গেছে। একটু অন্যভাবে লিখে আবার চেষ্টা করুন।"
        : unreachable
          ? `সার্ভারের (${API_URL}) সাথে যোগাযোগ করা যাচ্ছে না। সার্ভার চালু আছে তো? (uv run main.py)`
          : "উত্তর দিতে গিয়ে একটি সমস্যা হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।"}
    </Note>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="error-note" role="alert">
      <AlertTriangle size={16} />
      <span>{children}</span>
    </div>
  );
}

/** The sidebar's name for a conversation, from its first message. */
function newThreadTitle(text: string, hasPhotos: boolean): string | null {
  const label = decodeFormMessage(text).label;
  if (!label) return hasPhotos ? "ছবি পাঠানো হয়েছে" : null;
  return label.length > 48 ? `${label.slice(0, 47)}…` : label;
}

/** A conversation in the sidebar. Deleting takes a second click on the same button. */
function ThreadItem({
  thread,
  current,
  onOpen,
  onPin,
  onDelete,
}: {
  thread: Thread;
  current: boolean;
  onOpen: () => void;
  onPin: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const deleteLabel = confirming ? "মুছে ফেলতে আবার চাপুন" : "কথোপকথন মুছুন";
  return (
    <div className="thread-row" aria-current={current} data-confirming={confirming || undefined}>
      <button type="button" className="thread-item" onClick={onOpen}>
        {thread.pinned ? <Pin size={14} /> : <MessageSquare size={14} />}
        <span>{thread.title ?? "নতুন কথোপকথন"}</span>
      </button>
      {!confirming && (
        <button
          type="button"
          className="icon-btn thread-action"
          onClick={onPin}
          aria-label={thread.pinned ? "পিন সরান" : "পিন করুন"}
          title={thread.pinned ? "পিন সরান" : "পিন করুন"}
        >
          {thread.pinned ? <PinOff size={14} /> : <Pin size={14} />}
        </button>
      )}
      {confirming && (
        <button type="button" className="thread-cancel" onClick={() => setConfirming(false)}>
          না
        </button>
      )}
      <button
        type="button"
        className={confirming ? "thread-delete-armed" : "icon-btn thread-action"}
        onClick={() => (confirming ? onDelete() : setConfirming(true))}
        onBlur={(e) => {
          // Moving on to "না" is not leaving: that button has to stay to be pressed.
          if (!e.relatedTarget?.closest?.(".thread-row")) setConfirming(false);
        }}
        aria-label={deleteLabel}
        title={deleteLabel}
      >
        {confirming ? "মুছবেন?" : <Trash2 size={14} />}
      </button>
    </div>
  );
}
