/** The farmer's conversations and the streaming turn (src/meta_hackathon/api/threads.py). */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_HEADERS, API_URL, PHONE_HEADER } from "./config";
import type { ChatMessage } from "./turns";

export type Thread = {
  thread_id: string;
  title: string | null;
  pinned: boolean;
  created_at: string;
  updated_at: string;
};

export type TurnContent = string | ({ type: "text"; text: string } | { type: "image_url"; image_url: { url: string } })[];
export type TurnContext = Record<string, string | undefined>;

type StreamEvent =
  | { type: "message"; message: ChatMessage }
  | { type: "token"; text: string }
  | { type: "error"; message: string }
  | { type: "end" };

async function request<T>(phone: string, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}/v1/threads${path}`, {
    ...init,
    headers: { ...API_HEADERS, [PHONE_HEADER]: phone, "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const listThreads = (phone: string) => request<{ threads: Thread[] }>(phone, "").then((r) => r.threads);

export const createThread = (phone: string, title: string | null) =>
  request<Thread>(phone, "", { method: "POST", body: JSON.stringify({ title }) });

export const pinThread = (phone: string, id: string, pinned: boolean) =>
  request<Thread>(phone, `/${id}`, { method: "PATCH", body: JSON.stringify({ pinned }) });

export const deleteThread = (phone: string, id: string) => request<void>(phone, `/${id}`, { method: "DELETE" });

async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      // Lines starting with ":" are keep-alives.
      if (frame.startsWith("data: ")) yield JSON.parse(frame.slice(6)) as StreamEvent;
    }
  }
}

type UseChatOptions = {
  phone: string;
  threadId: string | null;
  /** A thread was created for the first message. */
  onThreadCreated: (id: string) => void;
  /** A turn ended, however it ended. */
  onFinished: () => void;
};

export function useChat({ phone, threadId, onThreadCreated, onFinished }: UseChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Reply text so far, shown as the last message until the finished one replaces it.
  const [draft, setDraft] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const running = useRef<AbortController | null>(null);
  // The thread just created for a send: its messages are already on screen.
  const [created, setCreated] = useState<string | null>(null);
  // The thread whose history has arrived.
  const [loaded, setLoaded] = useState<string | null>(null);

  const [shownThread, setShownThread] = useState(threadId);
  if (threadId !== shownThread) {
    setShownThread(threadId);
    if (!threadId || threadId !== created) {
      setCreated(null);
      setLoaded(null);
      setMessages([]);
      setDraft("");
      setError(null);
    }
  }

  const stop = useCallback(() => running.current?.abort(), []);

  useEffect(() => {
    if (threadId && threadId === created) return;
    running.current?.abort();
    if (!threadId) return;
    let current = true;
    request<{ messages: ChatMessage[] }>(phone, `/${threadId}/messages`)
      .then((r) => current && setMessages(r.messages))
      .catch((e) => current && setError(e))
      .finally(() => current && setLoaded(threadId));
    return () => {
      current = false;
    };
  }, [phone, threadId, created]);

  const submit = useCallback(
    async (content: TurnContent, context: TurnContext, title: string | null) => {
      if (running.current) return;
      const controller = new AbortController();
      running.current = controller;
      const pendingId = `pending-${Date.now()}`;
      setMessages((prev) => [...prev, { id: pendingId, type: "human", content }]);
      setDraft("");
      setError(null);
      setIsLoading(true);
      try {
        let id = threadId;
        if (!id) {
          id = (await createThread(phone, title)).thread_id;
          setCreated(id);
          onThreadCreated(id);
        }
        const res = await fetch(`${API_URL}/v1/threads/${id}/stream`, {
          method: "POST",
          headers: { ...API_HEADERS, [PHONE_HEADER]: phone, "Content-Type": "application/json" },
          body: JSON.stringify({ content, context }),
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);
        for await (const event of readEvents(res.body)) {
          if (event.type === "token") {
            setDraft((d) => d + event.text);
          } else if (event.type === "error") {
            setError(new Error(event.message));
          } else if (event.type === "message") {
            const { message } = event;
            // The server's copy of the farmer's message replaces the one shown on sending.
            setMessages((prev) => (message.type === "human" ? prev.map((m) => (m.id === pendingId ? message : m)) : [...prev, message]));
            if (message.type === "ai") setDraft("");
          }
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(e);
      } finally {
        running.current = null;
        setDraft("");
        setIsLoading(false);
        onFinished();
      }
    },
    [phone, threadId, onThreadCreated, onFinished],
  );

  const shown = useMemo<ChatMessage[]>(() => (draft ? [...messages, { id: "draft", type: "ai", content: draft }] : messages), [messages, draft]);

  const isThreadLoading = threadId !== null && threadId !== created && threadId !== loaded;

  return { messages: shown, isLoading, isThreadLoading, error, submit, stop };
}
