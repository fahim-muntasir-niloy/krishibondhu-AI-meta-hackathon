/**
 * Groups the flat LangGraph message list into chat turns: a user message, then
 * one assistant turn holding its tool steps and the final openui-lang reply.
 */
import { contentImages } from "./images";
import type { StepStatus } from "./narration";

/** A message as the API sends it: LangChain's own dump (api/threads.py). */
export type ChatMessage = {
  id?: string | null;
  type: string;
  content: string | ({ type?: string; text?: unknown } | string)[] | unknown[];
  tool_calls?: unknown[];
  tool_call_id?: string;
  status?: string;
  artifact?: unknown;
};

export type Step = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: StepStatus;
  result: unknown;
  /** What the tool returned for the UI only (the ToolMessage artifact), e.g. a crop case. */
  artifact?: unknown;
};

export type Turn =
  | { kind: "user"; id: string; text: string; images: string[] }
  | { kind: "assistant"; id: string; steps: Step[]; reply: string | null; replyId: string | null };

type ToolCall = { id?: string; name: string; args: Record<string, unknown> };

export function messageText(m: ChatMessage): string {
  if (typeof m.content === "string") return m.content;
  return (m.content as ({ type?: string; text?: unknown } | string)[])
    .map((block) => (typeof block === "string" ? block : block.type === "text" ? String(block.text ?? "") : ""))
    .join("");
}

function parseResult(content: string): unknown {
  try {
    return JSON.parse(content);
  } catch {
    return content;
  }
}

export function buildTurns(messages: ChatMessage[], isLoading: boolean): Turn[] {
  const results = new Map<string, { content: unknown; error: boolean; artifact?: unknown }>();
  for (const m of messages) {
    if (m.type === "tool") {
      const tm = m as ChatMessage & { tool_call_id: string };
      results.set(tm.tool_call_id, { content: parseResult(messageText(m)), error: tm.status === "error", artifact: tm.artifact });
    }
  }

  const turns: Turn[] = [];
  let current: Extract<Turn, { kind: "assistant" }> | null = null;

  messages.forEach((m, i) => {
    const id = m.id ?? `msg-${i}`;
    if (m.type === "human") {
      current = null;
      turns.push({ kind: "user", id, text: messageText(m), images: contentImages(m.content) });
      return;
    }
    if (m.type !== "ai") return;
    if (!current) {
      current = { kind: "assistant", id, steps: [], reply: null, replyId: null };
      turns.push(current);
    }
    const toolCalls = ((m.tool_calls ?? []) as ToolCall[]).filter((tc) => tc.name);
    if (toolCalls.length) {
      // Text alongside tool calls is the model thinking aloud; the narrated steps replace it.
      for (const tc of toolCalls) {
        const res = tc.id ? results.get(tc.id) : undefined;
        current.steps.push({
          id: tc.id ?? `${id}-${tc.name}`,
          name: tc.name,
          args: tc.args ?? {},
          status: res ? (res.error ? "error" : "done") : isLoading ? "running" : "stopped",
          result: res?.content,
          artifact: res?.artifact,
        });
      }
    } else if (messageText(m).trim()) {
      current.reply = messageText(m);
      current.replyId = id;
    }
  });
  return turns;
}
