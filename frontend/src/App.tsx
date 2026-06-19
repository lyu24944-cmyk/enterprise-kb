import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ChatMessage,
  Citation,
  Document,
  chatStream,
  deleteDocument,
  fetchDocuments,
  uploadDocument,
} from "./api";
import "./App.css";

const SUGGESTIONS = [
  "公司年假多少天？",
  "总结这份合同内容",
  "帮我提取所有风险条款",
  "根据制度生成请假申请",
];

export default function App() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadDocs = useCallback(async () => {
    try {
      const list = await fetchDocuments();
      setDocs(list);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    loadDocs();
  }, [loadDocs]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const toggleDoc = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      for (const f of Array.from(files)) {
        await uploadDocument(f);
      }
      await loadDocs();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  const onDelete = async (id: string) => {
    if (!confirm("确定删除该文档及其向量索引？")) return;
    await deleteDocument(id);
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    await loadDocs();
  };

  const send = async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setLoading(true);

    let assistant = "";
    let citations: Citation[] = [];
    let intent = "";

    setMessages((m) => [...m, { role: "assistant", content: "" }]);

    try {
      const sid = await chatStream(
        msg,
        sessionId,
        Array.from(selected),
        (token) => {
          assistant += token;
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", content: assistant, intent, citations };
            return copy;
          });
        },
        (meta) => {
          setSessionId(meta.session_id);
          intent = meta.intent;
        },
        (sources) => {
          citations = sources;
        },
      );
      setSessionId(sid);
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: assistant, intent, citations };
        return copy;
      });
    } catch (e: unknown) {
      const err = e instanceof Error ? e.message : "请求失败";
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: `错误：${err}` };
        return copy;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <header className="brand">
          <h1>企业知识库</h1>
          <p>AI Agent + RAG · DeepSeek</p>
        </header>

        <label className="upload-zone">
          <input
            type="file"
            multiple
            accept=".pdf,.docx,.pptx,.xlsx"
            hidden
            onChange={(e) => onUpload(e.target.files)}
          />
          {uploading ? "上传入库中..." : "上传 PDF / Word / PPT / Excel"}
        </label>

        <div className="doc-list">
          <h3>知识库文档 {docs.length ? `(${docs.length})` : ""}</h3>
          {docs.length === 0 && <p className="empty">暂无文档，请先上传或运行演示脚本</p>}
          {docs.map((d) => (
            <div key={d.id} className={`doc-item ${selected.has(d.id) ? "selected" : ""}`}>
              <label>
                <input type="checkbox" checked={selected.has(d.id)} onChange={() => toggleDoc(d.id)} />
                <span className="doc-name" title={d.filename}>{d.filename}</span>
              </label>
              <div className="doc-meta">
                <span className={`status ${d.status}`}>{d.status}</span>
                <span>{d.chunk_count} 块</span>
                <button className="link" onClick={() => onDelete(d.id)}>删除</button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <h2>欢迎使用企业知识库</h2>
              <p>上传制度、合同、培训材料后，可提问或执行 Agent 任务</p>
              <div className="chips">
                {SUGGESTIONS.map((s) => (
                  <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.intent && m.role === "assistant" && (
                <span className="intent-tag">{m.intent}</span>
              )}
              <div className="bubble-body">
                <ReactMarkdown>{m.content || (loading && i === messages.length - 1 ? "思考中..." : "")}</ReactMarkdown>
              </div>
              {m.citations && m.citations.length > 0 && (
                <div className="citations">
                  <strong>引用来源</strong>
                  {m.citations.map((c, j) => (
                    <details key={j}>
                      <summary>
                        {c.filename}
                        {c.page ? ` · 第${c.page}页` : ""}
                        {c.section ? ` · ${c.section}` : ""}
                      </summary>
                      <p>{c.text}</p>
                    </details>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <footer className="composer">
          <textarea
            rows={2}
            placeholder="输入问题，例如：公司年假多少天？"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button className="send" disabled={loading || !input.trim()} onClick={() => send()}>
            发送
          </button>
        </footer>
      </main>
    </div>
  );
}
