import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LlmComparisonEntry, RagIngestResponse, RagQueryResponse } from "../types";

const EXAMPLES = [
  "What is the current landslide risk?",
  "Explain the risk factors",
  "Show recent landslide activity",
  "How does TerraGuard predict risk?",
  "What should a field officer do during high risk?",
  "What is the rainfall in Dima Hasao?",
  "How many landslides happened in Assam?",
  "What evacuation actions are recommended?",
];

interface ChatEntry {
  role: "user" | "assistant";
  text: string;
  sources?: RagQueryResponse["sources"];
  llmUsed?: boolean;
  answerType?: RagQueryResponse["answer_type"];
  queryDescription?: string | null;
  chartData?: RagQueryResponse["chart_data"];
  llmComparison?: RagQueryResponse["llm_comparison"];
}

// Shown only when LLM_PROVIDER='multi': a compact readout of what happened
// on THIS question for the chatbot's Groq-primary / OpenRouter-fallback
// chain — Groq is always tried first; OpenRouter is only ever actually
// called if Groq errored or was rejected by the groundedness check, and
// shows as "Not called" here when Groq already succeeded. Gemini never
// appears — it is permanently excluded from the chat runtime. Real
// per-call results only, never invented — see
// llm_providers._evaluate_all_providers on the backend.
function LlmComparisonPanel({ entries }: { entries: LlmComparisonEntry[] }) {
  const STATUS_LABEL: Record<string, string> = {
    ok: "Answered",
    request_failed: "Failed",
    failed_groundedness_check: "Rejected (ungrounded)",
    not_called: "Not called",
    no_result: "No result",
  };
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", marginBottom: 6 }}>
        LLM chain — {entries.filter((e) => e.status === "ok").length} of {entries.length} providers answered
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {entries.map((e) => (
          <div
            key={e.provider}
            title={e.reason || e.error || (e.status === "not_called" ? "Skipped — an earlier provider already succeeded" : undefined)}
            style={{
              fontSize: 11,
              border: e.selected_as_optimal ? "1px solid #10b981" : "1px solid var(--border)",
              background: e.selected_as_optimal ? "rgba(16,185,129,0.08)" : "var(--surface-2)",
              borderRadius: 6,
              padding: "4px 8px",
              minWidth: 120,
              opacity: e.status === "not_called" ? 0.6 : 1,
            }}
          >
            <div style={{ fontWeight: 700, display: "flex", justifyContent: "space-between", gap: 6 }}>
              <span style={{ textTransform: "capitalize" }}>{e.provider}</span>
              {e.selected_as_optimal && <span style={{ color: "#10b981" }}>★ Used</span>}
            </div>
            <div style={{ color: "var(--text-dim)" }}>
              {STATUS_LABEL[e.status] ?? e.status}
              {typeof e.score === "number" ? ` · score ${e.score}` : ""}
              {typeof e.latency_ms === "number" ? ` · ${e.latency_ms}ms` : ""}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Simple, dependency-free heatmap: a colored grid, no charting library
// needed. Color scale is relative to this grid's own real min/max (never a
// fixed/invented scale) — light for low values, deep green for high.
function Heatmap({ chart }: { chart: NonNullable<RagQueryResponse["chart_data"]> }) {
  const flat = chart.values.flat().filter((v): v is number => v !== null);
  const min = flat.length ? Math.min(...flat) : 0;
  const max = flat.length ? Math.max(...flat) : 1;
  const colorFor = (v: number | null) => {
    if (v === null) return "var(--surface-2)";
    const t = max > min ? (v - min) / (max - min) : 0.5;
    // Light (low) -> deep green (high), consistent with the app's accent color.
    const lightness = 88 - t * 55; // 88% (near-white) down to 33% (deep)
    return `hsl(140, 45%, ${lightness}%)`;
  };
  const textColorFor = (v: number | null) => {
    if (v === null) return "var(--text-dim)";
    const t = max > min ? (v - min) / (max - min) : 0.5;
    return t > 0.55 ? "#fff" : "var(--text)";
  };
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)" }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", marginBottom: 6 }}>
        {chart.title}
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: 11 }}>
          <thead>
            <tr>
              <th style={{ padding: "3px 6px" }} />
              {chart.x_labels.map((x) => (
                <th key={x} style={{ padding: "3px 6px", color: "var(--text-dim)", fontWeight: 500 }}>{x}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {chart.y_labels.map((y, yi) => (
              <tr key={y}>
                <td style={{ padding: "3px 6px", color: "var(--text-dim)", fontWeight: 600 }}>{y}</td>
                {chart.values[yi].map((v, xi) => (
                  <td
                    key={xi}
                    title={v === null ? "no data" : `${v} ${chart.unit}`}
                    style={{
                      padding: "3px 6px",
                      textAlign: "center",
                      background: colorFor(v),
                      color: textColorFor(v),
                      borderRadius: 3,
                      minWidth: 30,
                    }}
                  >
                    {v === null ? "–" : v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Distinguishes retrieved/structured evidence (real DB rows or cited
// document chunks — "isEvidence: true") from a purely generated
// explanation, so the chat UI never blurs the two together.
const ANSWER_TYPE_LABEL: Record<string, { label: string; bg: string; fg: string; isEvidence: boolean }> = {
  general_chat: { label: "Chat", bg: "var(--surface-3)", fg: "var(--text-dim)", isEvidence: false },
  about_app: { label: "About TerraGuard", bg: "var(--teal-soft)", fg: "var(--teal)", isEvidence: false },
  structured: { label: "Verified data — from records", bg: "var(--low-soft)", fg: "var(--low)", isEvidence: true },
  document: { label: "Document / knowledge base — cited", bg: "var(--low-soft)", fg: "var(--low)", isEvidence: true },
  combined: { label: "Verified data + document — verified", bg: "var(--low-soft)", fg: "var(--low)", isEvidence: true },
  insufficient_data: { label: "No sufficient data found", bg: "var(--critical-soft)", fg: "var(--critical)", isEvidence: false },
  // General knowledge from the configured multi-provider LLM chain, used
  // only when TerraGuard's own data records and knowledge base have nothing on
  // the question (see rag_pipeline._general_knowledge_answer). Kept visibly
  // distinct in amber — this is explicitly NOT a verified TerraGuard record.
  general_knowledge: { label: "General AI knowledge — not a verified TerraGuard record", bg: "var(--moderate-soft)", fg: "var(--moderate)", isEvidence: false },
};

// Local LLM generation (Ollama/Qwen3 on the user's own machine) can
// genuinely take a while, especially the very first question after the
// backend boots (the embedding model may still be downloading/loading in
// the background — see main.py's startup preload) or on modest hardware.
// A visible, ticking "thinking" bubble makes that wait look like progress
// instead of a frozen app, which was the actual complaint: replies
// sometimes seemed to never show up.
const THINKING_MESSAGES = [
  "TerraGuard AI is thinking...",
  "Checking TerraGuard's data records and knowledge base...",
  "Still working — this is taking a little longer than usual...",
  "Almost there...",
];

export default function RagAssistantPage() {
  const [question, setQuestion] = useState("");
  const [log, setLog] = useState<ChatEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [ingesting, setIngesting] = useState(false);
  const [ingestStatus, setIngestStatus] = useState<{ ok: boolean; message: string } | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);
  // Guards against a double-click starting two overlapping recognition
  // sessions before React's isRecording state has actually committed —
  // recognition.onstart fires asynchronously, so isRecording alone isn't
  // enough to prevent a race on a fast double-click/tap.
  const startingRef = useRef(false);
  // The user's own "stop" click calls recognition.stop(), which some
  // browsers report via onerror with code "aborted" even though nothing
  // actually went wrong — that used to surface as a confusing "voice
  // recognition failed" message every time someone deliberately stopped
  // recording. Tracked so onerror can tell a real failure from a
  // user-initiated stop.
  const userStoppedRef = useRef(false);
  const questionRef = useRef(question);
  questionRef.current = question;

  // Web Speech API (SpeechRecognition) — browser-native, free, no paid
  // speech-to-text service. Support varies: Chrome/Edge ship it as
  // `webkitSpeechRecognition`, some browsers don't ship it at all.
  const SpeechRecognitionCtor =
    typeof window !== "undefined" ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition : null;
  const speechSupported = Boolean(SpeechRecognitionCtor);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop?.();
    };
  }, []);

  useEffect(() => {
    if (!loading) return;
    setElapsedSec(0);
    const interval = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [loading]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log, loading]);

  const ask = async (q: string) => {
    if (!q.trim()) return;
    setLog((prev) => [...prev, { role: "user", text: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const resp = await api.post<RagQueryResponse>("/rag/query", { question: q });
      setLog((prev) => [
        ...prev,
        {
          role: "assistant",
          text: resp.data.answer,
          sources: resp.data.sources,
          llmUsed: resp.data.llm_used,
          answerType: resp.data.answer_type,
          queryDescription: resp.data.query_description,
          chartData: resp.data.chart_data,
          llmComparison: resp.data.llm_comparison,
        },
      ]);
    } catch (e) {
      setLog((prev) => [...prev, { role: "assistant", text: `Error: ${e instanceof Error ? e.message : "request failed"}` }]);
    } finally {
      setLoading(false);
    }
  };

  // Was previously fire-and-forget with zero UI feedback — clicking it did
  // something on the backend but looked exactly like a dead button. Now
  // shows a real loading state and a real success/error result, and can't
  // be double-clicked into two concurrent ingests.
  const ingest = async () => {
    if (ingesting) return;
    setIngesting(true);
    setIngestStatus(null);
    try {
      const resp = await api.post<RagIngestResponse>("/rag/ingest");
      const { documents_ingested, chunks_created, skipped } = resp.data;
      const detail = ` (${documents_ingested} document(s), ${chunks_created} chunk(s) re-indexed)`;
      const skippedNote = skipped && skipped.length > 0 ? ` Skipped: ${skipped.join("; ")}` : "";
      setIngestStatus({ ok: true, message: `Knowledge base reloaded${detail}.${skippedNote}` });
    } catch (e) {
      setIngestStatus({
        ok: false,
        message: `Reload failed: ${e instanceof Error ? e.message : "request failed"}. The previously loaded knowledge base is still in use.`,
      });
    } finally {
      setIngesting(false);
    }
  };

  const clearChat = () => {
    setLog([]);
    setVoiceError(null);
  };

  const stopRecording = () => {
    userStoppedRef.current = true;
    recognitionRef.current?.stop?.();
  };

  const startRecording = () => {
    if (!speechSupported || loading || isRecording || startingRef.current) return;
    startingRef.current = true;
    userStoppedRef.current = false;
    setVoiceError(null);

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      startingRef.current = false;
      setIsRecording(true);
    };

    recognition.onresult = (event: any) => {
      const transcript = event?.results?.[0]?.[0]?.transcript?.trim();
      if (!transcript) {
        setVoiceError("Didn't catch that — please try again.");
        return;
      }
      // Text goes into the input box for the user to review/edit; it is
      // never sent automatically — they still have to press Send/Ask.
      setQuestion((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };

    recognition.onerror = (event: any) => {
      const code = event?.error;
      if (userStoppedRef.current && (code === "aborted" || code === "no-speech")) {
        // The user deliberately pressed stop — some browsers report that as
        // an "aborted"/"no-speech" error even though nothing went wrong.
        return;
      }
      if (code === "not-allowed" || code === "service-not-allowed") {
        setVoiceError("Microphone permission denied. Please allow microphone access to use voice input.");
      } else if (code === "no-speech") {
        setVoiceError("No speech detected. Please try again.");
      } else if (code === "aborted") {
        // Genuinely unexpected abort (not user-initiated) — still worth
        // surfacing, but with wording that doesn't imply a broken mic.
        setVoiceError("Voice recording was interrupted. Please try again.");
      } else {
        setVoiceError("Voice recognition failed. Please try again or type your question.");
      }
    };

    recognition.onend = () => {
      startingRef.current = false;
      setIsRecording(false);
      recognitionRef.current = null;
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      startingRef.current = false;
      setIsRecording(false);
      setVoiceError("Could not start voice recognition. Please try again.");
    }
  };

  const toggleRecording = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div>
      <h2 className="page-title">TerraGuard AI Assistant</h2>
      <p className="page-subtitle">
        Answers come from two places only: TerraGuard's own data records (risk zones, rainfall, landslide history — exact
        numbers) and its knowledge base (SOPs, guidance — retrieved and cited). The assistant never invents numbers,
        locations, or predictions — it only explains what TerraGuard's own data and documents say.
      </p>

      <div className="card">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {EXAMPLES.map((ex) => (
            <button key={ex} className="btn btn-ghost" onClick={() => ask(ex)} disabled={loading} style={{ fontWeight: 500, fontSize: 12.5 }}>
              {ex}
            </button>
          ))}
          <button
            className="btn btn-ghost"
            onClick={clearChat}
            disabled={loading || log.length === 0}
            style={{ marginLeft: "auto", fontWeight: 500, fontSize: 12.5 }}
            title="Clear the conversation"
          >
            Clear Chat
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => ingest()}
            disabled={loading || ingesting}
            style={{ fontWeight: 500, fontSize: 12.5 }}
            title="Re-scans knowledge_base/ and re-indexes it for this assistant"
          >
            {ingesting ? (
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span className="thinking-dots" aria-hidden="true"><span /><span /><span /></span>
                Reloading knowledge base…
              </span>
            ) : (
              "Reload knowledge base"
            )}
          </button>
        </div>

        {ingestStatus && (
          <div
            style={{
              fontSize: 12.5,
              marginBottom: 10,
              padding: "8px 10px",
              borderRadius: 6,
              background: ingestStatus.ok ? "var(--low-soft, rgba(16,185,129,0.1))" : "var(--critical-soft, rgba(220,38,38,0.1))",
              color: ingestStatus.ok ? "var(--low, #10b981)" : "var(--critical, #dc2626)",
            }}
          >
            {ingestStatus.message}
          </div>
        )}

        <div className="chat-log">
          {log.map((entry, i) => (
            <div key={i} className={`chat-msg ${entry.role} chat-msg-enter`}>
              <div className="chat-msg-role-label">{entry.role === "user" ? "You" : "TerraGuard AI"}</div>
              {entry.role === "assistant" && entry.answerType && (
                <div
                  className="evidence-tag"
                  style={{
                    color: ANSWER_TYPE_LABEL[entry.answerType]?.fg ?? "var(--text-dim)",
                    background: ANSWER_TYPE_LABEL[entry.answerType]?.bg ?? "var(--surface-3)",
                  }}
                >
                  {ANSWER_TYPE_LABEL[entry.answerType]?.isEvidence ? "✓ " : ""}
                  {ANSWER_TYPE_LABEL[entry.answerType]?.label ?? entry.answerType}
                </div>
              )}
              <div style={{ whiteSpace: "pre-wrap" }}>{entry.text}</div>
              {/* Source excerpts, match %, and query-description metadata are
                  intentionally not shown here — just the direct answer, plus
                  a heatmap when the answer has real multi-year/month data
                  behind it (see Heatmap above). */}
              {entry.chartData && <Heatmap chart={entry.chartData} />}
              {entry.llmComparison && entry.llmComparison.length > 0 && (
                <LlmComparisonPanel entries={entry.llmComparison} />
              )}
            </div>
          ))}
          {loading && (
            <div className="chat-msg assistant">
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-dim)" }}>
                <span className="thinking-dots" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </span>
                <span>
                  {THINKING_MESSAGES[Math.min(Math.floor(elapsedSec / 5), THINKING_MESSAGES.length - 1)]}
                  {elapsedSec > 0 ? ` (${elapsedSec}s)` : ""}
                </span>
              </div>
            </div>
          )}
          <div ref={logEndRef} />
        </div>

        {voiceError && (
          <div style={{ fontSize: 12, color: "var(--critical, #dc2626)", marginBottom: 8 }}>{voiceError}</div>
        )}

        {isRecording && (
          <div className="voice-listening-banner" role="status">
            <span className="voice-listening-dot" aria-hidden="true" />
            Listening… speak your question, then press the mic again to stop.
          </div>
        )}

        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !loading && ask(questionRef.current)}
            placeholder={speechSupported ? "Ask about risk, rainfall, landslide history, or disaster-response guidance… (or use the mic)" : "Ask about risk, rainfall, landslide history, or disaster-response guidance..."}
            disabled={loading}
          />
          <button
            type="button"
            className={`btn btn-ghost${isRecording ? " recording" : ""}`}
            onClick={toggleRecording}
            disabled={loading || !speechSupported}
            title={
              !speechSupported
                ? "Voice input isn't supported in this browser — try Chrome or Edge"
                : isRecording
                  ? "Stop recording"
                  : "Ask by voice"
            }
            aria-pressed={isRecording}
            style={{
              minWidth: 44,
              color: isRecording ? "#fff" : undefined,
              background: isRecording ? "#dc2626" : undefined,
              borderColor: isRecording ? "#dc2626" : undefined,
            }}
          >
            {isRecording ? "● " : "🎤"}
            {isRecording && <span className="thinking-dots" aria-hidden="true" style={{ marginLeft: 4 }}><span /><span /><span /></span>}
          </button>
          <button className="primary blue-action-button" onClick={() => ask(question)} disabled={loading}>
            {loading ? `Thinking (${elapsedSec}s)` : "Ask"}
          </button>
        </div>
        {!speechSupported && (
          <p style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6 }}>
            Voice input isn't available in this browser — it works in Chrome and Edge. Typing works everywhere.
          </p>
        )}
      </div>
    </div>
  );
}
