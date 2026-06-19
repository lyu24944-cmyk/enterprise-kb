export interface Document {
  id: string;
  filename: string;
  doc_type: string;
  category: string;
  chunk_count: number;
  status: string;
  created_at: string;
}

export interface Citation {
  doc_id: string;
  filename: string;
  page?: number;
  section?: string;
  text: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  intent?: string;
  status?: string;
  citations?: Citation[];
}

const API = "/api/v1";
const CHAT_TIMEOUT_MS = 120_000;

export async function fetchDocuments(): Promise<Document[]> {
  const res = await fetch(`${API}/documents`);
  if (!res.ok) throw new Error("加载文档失败");
  return res.json();
}

export async function uploadDocument(file: File): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/documents/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "上传失败");
  }
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API}/documents/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("删除失败");
}

export async function chatStream(
  message: string,
  sessionId: string | null,
  docIds: string[],
  onToken: (t: string) => void,
  onMeta: (data: { session_id: string; intent: string }) => void,
  onCitation: (sources: Citation[]) => void,
  onStatus: (message: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, doc_ids: docIds, stream: true }),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "对话失败");
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let session = sessionId || "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) data = line.slice(5).trim();
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (event === "meta") {
        session = parsed.session_id || session;
        if (parsed.intent) onMeta(parsed);
      } else if (event === "status") {
        onStatus(parsed.message);
      } else if (event === "token") {
        onToken(parsed.content);
      } else if (event === "citation") {
        onCitation(parsed.sources);
      } else if (event === "error") {
        throw new Error(parsed.message || "对话失败");
      }
    }
  }
  return session;
}

export function createChatAbortSignal(): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);
  return {
    signal: controller.signal,
    cancel: () => clearTimeout(timer),
  };
}
