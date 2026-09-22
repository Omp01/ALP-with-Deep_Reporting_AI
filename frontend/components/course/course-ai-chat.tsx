"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Sparkles,
  Send,
  X,
  Compass,
  BookOpen,
  CheckCircle2,
  Clock,
  ArrowRight,
  RotateCcw,
  Bot,
  User as UserIcon,
  HelpCircle,
  Lightbulb,
} from "lucide-react";
import { Button, Badge, Spinner } from "@/components/ui";
import { apiClient } from "@/lib/api-client";

export interface LearningPathStep {
  module_id: string;
  module_title: string;
  status: "completed" | "in_progress" | "recommended_next" | "up_next" | string;
  rationale: string;
  recommended_item_id?: string | null;
  recommended_item_title?: string | null;
}

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant";
  content: string;
  action?: string;
  model?: string;
  provider?: string;
  learning_path?: LearningPathStep[] | null;
  timestamp: string;
}

interface CourseAIChatProps {
  courseId: string;
  courseTitle?: string;
  currentItemId?: string | null;
  isOpen: boolean;
  onClose: () => void;
  onSelectLesson?: (itemId: string) => void;
}

export function CourseAIChat({
  courseId,
  courseTitle = "Course",
  currentItemId,
  isOpen,
  onClose,
  onSelectLesson,
}: CourseAIChatProps) {
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Focus input when drawer opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  const sendMessage = useCallback(
    async (text: string, action: string = "chat") => {
      if ((!text.trim() && action === "chat") || loading) return;

      const userMsgText = text.trim() || (action === "summarize" ? "Summarize this course" : action === "learning_path" ? "Recommend my learning path" : text);
      const userMsg: ChatMessageItem = {
        id: `user-${Date.now()}`,
        role: "user",
        content: userMsgText,
        action,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setLoading(true);
      setActiveAction(action);

      try {
        const historyPayload = messages.slice(-6).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const response = await apiClient.post<{
          reply: string;
          action: string;
          provider: string;
          model: string;
          learning_path?: LearningPathStep[] | null;
        }>(
          `/api/v1/courses/${courseId}/chat`,
          {
            message: text.trim(),
            action,
            current_item_id: currentItemId || null,
            history: historyPayload,
          },
          { timeoutMs: 60_000 }
        );

        const assistantMsg: ChatMessageItem = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: response.reply,
          action: response.action,
          provider: response.provider,
          model: response.model,
          learning_path: response.learning_path,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err: unknown) {
        const errMsg: ChatMessageItem = {
          id: `assistant-err-${Date.now()}`,
          role: "assistant",
          content:
            err instanceof Error
              ? `I encountered an issue processing your request: ${err.message}. Please try asking again.`
              : "Unable to connect to AI Mentor service. Please check your network and try again.",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setLoading(false);
        setActiveAction(null);
      }
    },
    [courseId, currentItemId, loading, messages]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input, "chat");
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="AI Course Mentor"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col border-l border-border bg-surface shadow-2xl transition-transform duration-300 animate-in slide-in-from-right sm:w-[480px]"
    >
      {/* 1. Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-border bg-surface-elevated/90 px-4 py-3.5 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-primary to-primary-hover text-white shadow-sm ring-1 ring-primary/20">
            <Sparkles className="h-5 w-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-fg">AI Course Mentor</h2>
              <span className="flex h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-emerald-500/20" />
            </div>
            <p className="text-xs text-fg-muted truncate max-w-[220px]">
              {courseTitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={clearChat}
              title="Reset conversation"
              className="text-fg-muted hover:text-fg"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Close AI Mentor"
            className="text-fg-muted hover:text-fg"
          >
            <X className="h-5 w-5" />
          </Button>
        </div>
      </div>

      {/* 2. Messages / Body */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-4 text-sm"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary mb-3 shadow-inner">
              <Bot className="h-6 w-6" />
            </div>
            <h3 className="font-semibold text-fg text-base">
              Hi, I&apos;m your Course Mentor!
            </h3>
            <p className="text-xs text-fg-muted max-w-xs mt-1.5 leading-relaxed">
              I can summarize the course curriculum, analyze your skill gaps, and guide your personalized study path powered by Gemini & Groq.
            </p>

            {/* Quick Action Chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-6 w-full max-w-sm">
              <button
                type="button"
                onClick={() => sendMessage("", "summarize")}
                className="flex items-center gap-2.5 p-3 rounded-xl border border-border bg-surface-elevated hover:border-primary/40 hover:bg-surface-elevated/80 transition-all text-left group"
              >
                <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-500 group-hover:scale-105 transition-transform">
                  <BookOpen className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-fg">Summarize Course</p>
                  <p className="text-[11px] text-fg-muted">Overview & key skills</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() => sendMessage("", "learning_path")}
                className="flex items-center gap-2.5 p-3 rounded-xl border border-border bg-surface-elevated hover:border-primary/40 hover:bg-surface-elevated/80 transition-all text-left group"
              >
                <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-500 group-hover:scale-105 transition-transform">
                  <Compass className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-fg">My Learning Path</p>
                  <p className="text-[11px] text-fg-muted">Tailored next steps</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() =>
                  sendMessage("What are the most challenging topics in this course and how can I master them?", "chat")
                }
                className="flex items-center gap-2.5 p-3 rounded-xl border border-border bg-surface-elevated hover:border-primary/40 hover:bg-surface-elevated/80 transition-all text-left group"
              >
                <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500 group-hover:scale-105 transition-transform">
                  <Lightbulb className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-fg">Tricky Concepts</p>
                  <p className="text-[11px] text-fg-muted">Tips to conquer them</p>
                </div>
              </button>

              <button
                type="button"
                onClick={() =>
                  sendMessage("Give me a quick 3-question practice pop quiz based on this course.", "chat")
                }
                className="flex items-center gap-2.5 p-3 rounded-xl border border-border bg-surface-elevated hover:border-primary/40 hover:bg-surface-elevated/80 transition-all text-left group"
              >
                <div className="p-1.5 rounded-lg bg-purple-500/10 text-purple-500 group-hover:scale-105 transition-transform">
                  <HelpCircle className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs font-semibold text-fg">Pop Quiz Prep</p>
                  <p className="text-[11px] text-fg-muted">Test my readiness</p>
                </div>
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col ${
                msg.role === "user" ? "items-end" : "items-start"
              }`}
            >
              <div className="flex items-center gap-1.5 mb-1 text-[11px] text-fg-muted">
                {msg.role === "assistant" ? (
                  <>
                    <Sparkles className="h-3 w-3 text-primary" />
                    <span className="font-medium text-fg">AI Mentor</span>
                    {msg.model && (
                      <span className="text-[10px] text-fg-muted/70">
                        ({msg.model})
                      </span>
                    )}
                  </>
                ) : (
                  <>
                    <UserIcon className="h-3 w-3 text-fg-muted" />
                    <span>You</span>
                  </>
                )}
                <span>·</span>
                <span>{msg.timestamp}</span>
              </div>

              <div
                className={`max-w-[92%] rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed shadow-sm ${
                  msg.role === "user"
                    ? "bg-primary text-white rounded-br-none"
                    : "bg-surface-elevated border border-border text-fg rounded-bl-none"
                }`}
              >
                {/* Formatted Markdown-like Content */}
                <div className="whitespace-pre-wrap space-y-1.5">
                  {msg.content}
                </div>

                {/* Structured Learning Path Cards */}
                {msg.learning_path && msg.learning_path.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-border/70 space-y-2.5">
                    <p className="text-xs font-semibold tracking-wide uppercase text-fg-muted flex items-center gap-1.5">
                      <Compass className="h-3.5 w-3.5 text-primary" /> Recommended Study Milestones:
                    </p>
                    <div className="space-y-2">
                      {msg.learning_path.map((step, idx) => {
                        const isCompleted = step.status === "completed";
                        const isNext = step.status === "recommended_next" || step.status === "in_progress";

                        return (
                          <div
                            key={idx}
                            className={`p-2.5 rounded-xl border transition-colors ${
                              isNext
                                ? "border-primary/40 bg-primary/5 ring-1 ring-primary/20"
                                : isCompleted
                                ? "border-emerald-500/30 bg-emerald-500/5"
                                : "border-border bg-surface"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-semibold text-fg flex items-center gap-1.5 truncate">
                                {isCompleted ? (
                                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                                ) : isNext ? (
                                  <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
                                ) : (
                                  <Clock className="h-3.5 w-3.5 text-fg-muted shrink-0" />
                                )}
                                <span className="truncate">{step.module_title}</span>
                              </span>
                              <Badge
                                variant={
                                  isCompleted
                                    ? "success"
                                    : isNext
                                    ? "primary"
                                    : "neutral"
                                }
                                size="sm"
                              >
                                {step.status === "recommended_next"
                                  ? "Recommended"
                                  : step.status === "completed"
                                  ? "Done"
                                  : "Up Next"}
                              </Badge>
                            </div>

                            <p className="text-[11px] text-fg-muted mt-1 leading-snug">
                              {step.rationale}
                            </p>

                            {step.recommended_item_id && onSelectLesson && (
                              <button
                                type="button"
                                onClick={() => {
                                  if (step.recommended_item_id) {
                                    onSelectLesson(step.recommended_item_id);
                                    onClose();
                                  }
                                }}
                                className="mt-2 flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
                              >
                                <span>Go to lesson: {step.recommended_item_title || "Start Topic"}</span>
                                <ArrowRight className="h-3 w-3 ml-0.5" />
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {/* Loading Indicator */}
        {loading && (
          <div className="flex flex-col items-start">
            <div className="flex items-center gap-1.5 mb-1 text-[11px] text-fg-muted">
              <Sparkles className="h-3 w-3 text-primary animate-spin" />
              <span className="font-medium text-fg">AI Mentor is thinking...</span>
            </div>
            <div className="rounded-2xl rounded-bl-none border border-border bg-surface-elevated p-3.5 text-xs text-fg-muted flex items-center gap-2.5">
              <Spinner size="sm" />
              <span>
                {activeAction === "summarize"
                  ? "Synthesizing full course curriculum & key skills..."
                  : activeAction === "learning_path"
                  ? "Analyzing your competency telemetry to build path..."
                  : "Generating grounded pedagogical response..."}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 3. Action Toolbar & Prompt Input */}
      <div className="shrink-0 border-t border-border bg-surface-elevated/70 p-3 space-y-2">
        {/* Quick Suggestion Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs no-scrollbar">
          <button
            type="button"
            disabled={loading}
            onClick={() => sendMessage("", "summarize")}
            className="shrink-0 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-fg-muted hover:border-primary/40 hover:text-fg transition-colors disabled:opacity-50"
          >
            ⚡ Summarize
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => sendMessage("", "learning_path")}
            className="shrink-0 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-fg-muted hover:border-primary/40 hover:text-fg transition-colors disabled:opacity-50"
          >
            🎯 Learning Path
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() =>
              sendMessage("Explain the main concept of the current lesson in simple terms.", "explain")
            }
            className="shrink-0 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-fg-muted hover:border-primary/40 hover:text-fg transition-colors disabled:opacity-50"
          >
            💡 Explain Lesson
          </button>
        </div>

        {/* Input Box */}
        <div className="relative flex items-center">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            disabled={loading}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask AI Mentor anything about this course..."
            className="w-full resize-none rounded-xl border border-border bg-surface px-3.5 py-2.5 pr-10 text-xs sm:text-sm text-fg placeholder:text-fg-muted focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50 max-h-32 min-h-[42px]"
          />
          <button
            type="button"
            disabled={loading || !input.trim()}
            onClick={() => sendMessage(input, "chat")}
            aria-label="Send message"
            className="absolute right-2 flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-white hover:bg-primary-hover disabled:opacity-40 transition-opacity"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
        <p className="text-[10px] text-center text-fg-muted/60">
          Powered by Gemini & Groq AI · Grounded in course curriculum
        </p>
      </div>
    </div>
  );
}
