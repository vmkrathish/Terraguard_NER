import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { RagQueryResponse } from "../types";

interface FloatingMessage {
  role: "user" | "assistant";
  text: string;
}

export default function FloatingAssistant() {
  const navigate = useNavigate();
  const assistantRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<FloatingMessage[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (!assistantRef.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  async function ask() {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) return;

    setQuestion("");
    setMessages((current) => [...current, { role: "user", text: trimmedQuestion }]);
    setLoading(true);
    try {
      const response = await api.post<RagQueryResponse>("/rag/query", { question: trimmedQuestion });
      setMessages((current) => [...current, { role: "assistant", text: response.data.answer }]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", text: `Unable to reach TerraGuard AI: ${error instanceof Error ? error.message : "request failed"}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div ref={assistantRef} className={`floating-assistant ${open ? "open" : ""}`}>
      {open && (
        <section className="floating-assistant-panel" aria-label="AI Assistance chatbot">
          <header className="floating-assistant-header">
            <div>
              <strong>AI Assistance</strong>
              <span>TerraGuard response intelligence</span>
            </div>
            <button className="floating-assistant-close" onClick={() => setOpen(false)} aria-label="Close AI Assistance">×</button>
          </header>

          <div className="floating-assistant-messages" aria-live="polite">
            {messages.length === 0 && (
              <div className="floating-assistant-welcome">
                Ask about risk zones, rainfall, landslides, or response guidance.
              </div>
            )}
            {messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`floating-assistant-message ${message.role}`}>
                {message.text}
              </div>
            ))}
            {loading && <div className="floating-assistant-message assistant">Checking TerraGuard data...</div>}
          </div>

          <form className="floating-assistant-form" onSubmit={(event) => { event.preventDefault(); void ask(); }}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Ask TerraGuard AI..."
              aria-label="Ask TerraGuard AI"
              disabled={loading}
            />
            <button type="submit" aria-label="Send question" disabled={loading || !question.trim()}>↑</button>
          </form>
          <button className="floating-assistant-full-link" onClick={() => navigate("/assistant")}>Open full assistant</button>
        </section>
      )}

      <button
        className="floating-assistant-trigger"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-label={open ? "Close AI Assistance" : "Open AI Assistance"}
      >
        <span className="floating-assistant-icon" aria-hidden="true">✦</span>
        <span>AI Assistance</span>
      </button>
    </div>
  );
}
