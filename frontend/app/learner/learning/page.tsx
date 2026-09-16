"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Sidebar } from "@/components/Sidebar";
import {
  Compass,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Sparkles,
  RefreshCw,
  Award,
  AlertCircle,
  HelpCircle,
} from "lucide-react";

export default function AdaptiveLearningPage() {
  const [user, setUser] = useState<any>(null);
  const [course, setCourse] = useState<any>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
  const [adaptiveFeedback, setAdaptiveFeedback] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [startTime, setStartTime] = useState<number>(Date.now());

  useEffect(() => {
    async function loadSession() {
      if (typeof window === "undefined") return;
      const stored = localStorage.getItem("user");
      const token = localStorage.getItem("access_token");
      if (!stored || !token) {
        window.location.href = "/login";
        return;
      }
      const u = JSON.parse(stored);
      setUser(u);
      const headers = { Authorization: `Bearer ${token}` };

      try {
        const coursesRes = await fetch("http://localhost:8000/api/v1/courses", { headers });
        if (coursesRes.ok) {
          const courses = await coursesRes.json();
          if (courses.length > 0) {
            setCourse(courses[0]);

            // Seeded interactive demo assessment questions
            setQuestions([
              {
                id: "q-1",
                text: "Which hook should be used to manage complex local state transitions with predictable actions in React?",
                options: [
                  { id: 0, text: "useReducer", is_correct: true },
                  { id: 1, text: "useState", is_correct: false, error: "suboptimal for complex reducer state" },
                  { id: 2, text: "useEffect", is_correct: false, error: "side-effect hook, not state holder" },
                  { id: 3, text: "useRef", is_correct: false, error: "mutable ref, does not trigger re-render" },
                ],
                explanation: "useReducer is preferred for complex state logic involving multiple sub-values or when the next state depends on the previous one.",
                difficulty: "intermediate",
                competency_name: "React State Management",
              },
              {
                id: "q-2",
                text: "When should you provide a dependency array to useEffect to avoid unintended infinite re-renders?",
                options: [
                  { id: 0, text: "Only when importing third-party libraries", is_correct: false, error: "misconception" },
                  { id: 1, text: "Always specify every reactive value referenced inside the effect callback", is_correct: true },
                  { id: 2, text: "Leave it empty in all cases to optimize performance", is_correct: false, error: "causes stale closures" },
                  { id: 3, text: "Dependency arrays are deprecated in modern React", is_correct: false, error: "factually incorrect" },
                ],
                explanation: "The exhaustive deps rule ensures all variables from the component scope used in the effect are tracked to prevent stale closures.",
                difficulty: "intermediate",
                competency_name: "React Component Lifecycle",
              },
            ]);
            setStartTime(Date.now());
          }
        }
      } catch (e) {
        console.error("Error loading session", e);
      } finally {
        setLoading(false);
      }
    }
    loadSession();
  }, []);

  const handleSubmitAnswer = async () => {
    if (selectedOption === null) return;
    const q = questions[currentIdx];
    const opt = q.options[selectedOption];
    const correct = opt.is_correct;
    const duration = Date.now() - startTime;
    setIsCorrect(correct);
    setSubmitted(true);

    const token = localStorage.getItem("access_token");
    const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

    try {
      // 1. Ingest Learning Telemetry Event
      await fetch("http://localhost:8000/api/v1/events", {
        method: "POST",
        headers,
        body: JSON.stringify({
          event_type: "question_answered",
          course_id: course?.id,
          payload: {
            question_id: q.id,
            correct: correct,
            duration_ms: duration,
            attempt_number: 1,
            difficulty: q.difficulty,
            error_type: opt.error,
          },
        }),
      });

      // 2. Call Adaptive Next Endpoint for live decision
      const adaptiveRes = await fetch("http://localhost:8000/api/v1/adaptive/next", {
        method: "POST",
        headers,
        body: JSON.stringify({
          session_id: "00000000-0000-0000-0000-000000000001",
          course_id: course?.id,
        }),
      });

      if (adaptiveRes.ok) {
        const feedback = await adaptiveRes.json();
        setAdaptiveFeedback(feedback);
      }
    } catch (err) {
      console.error("Error submitting answer", err);
    }
  };

  const handleNextQuestion = () => {
    if (currentIdx + 1 < questions.length) {
      setCurrentIdx(currentIdx + 1);
      setSelectedOption(null);
      setSubmitted(false);
      setIsCorrect(null);
      setAdaptiveFeedback(null);
      setStartTime(Date.now());
    } else {
      // Completed sample set, loop or reset
      setCurrentIdx(0);
      setSelectedOption(null);
      setSubmitted(false);
      setIsCorrect(null);
      setAdaptiveFeedback(null);
      setStartTime(Date.now());
    }
  };

  const currentQ = questions[currentIdx];

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8 max-w-4xl">
          {/* Header */}
          <div className="mb-6 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-indigo-600 uppercase tracking-wider mb-1">
                <Compass className="w-4 h-4" /> Live Adaptive Session
              </div>
              <h1 className="text-2xl font-bold text-slate-900">{course?.title || "Full-Stack React & Node"}</h1>
            </div>
            <span className="text-xs font-semibold px-3 py-1 bg-white border border-slate-200 rounded-full text-slate-700">
              Item {currentIdx + 1} of {questions.length}
            </span>
          </div>

          {loading ? (
            <div className="bg-white p-12 text-center rounded-2xl border border-slate-200">
              <div className="animate-spin w-8 h-8 border-4 border-indigo-600 border-t-transparent rounded-full mx-auto" />
              <p className="mt-3 text-sm text-slate-500">Loading adaptive curriculum item...</p>
            </div>
          ) : currentQ ? (
            <div className="space-y-6">
              {/* Question Card */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Testing Competency: <strong className="text-slate-700">{currentQ.competency_name}</strong>
                  </span>
                  <span className="text-xs font-bold uppercase px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                    Difficulty: {currentQ.difficulty}
                  </span>
                </div>

                <h2 className="text-lg font-semibold text-slate-900 leading-relaxed mb-6">
                  {currentQ.text}
                </h2>

                {/* Option choices */}
                <div className="space-y-3">
                  {currentQ.options.map((opt: any) => {
                    const isSelected = selectedOption === opt.id;
                    let optionStyle = "border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700";
                    if (isSelected) {
                      optionStyle = "border-indigo-600 bg-indigo-50/40 text-indigo-900 font-medium";
                    }
                    if (submitted) {
                      if (opt.is_correct) {
                        optionStyle = "border-emerald-500 bg-emerald-50 text-emerald-900 font-medium";
                      } else if (isSelected && !opt.is_correct) {
                        optionStyle = "border-rose-500 bg-rose-50 text-rose-900 font-medium";
                      }
                    }

                    return (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={submitted}
                        onClick={() => setSelectedOption(opt.id)}
                        className={`w-full text-left p-4 rounded-xl border text-sm transition-all flex items-center justify-between ${optionStyle}`}
                      >
                        <span>{opt.text}</span>
                        {submitted && opt.is_correct && (
                          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                        )}
                        {submitted && isSelected && !opt.is_correct && (
                          <XCircle className="w-5 h-5 text-rose-600 flex-shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Action button */}
                <div className="mt-6 flex justify-end">
                  {!submitted ? (
                    <button
                      type="button"
                      disabled={selectedOption === null}
                      onClick={handleSubmitAnswer}
                      className="px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm disabled:opacity-50"
                    >
                      Submit Response
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleNextQuestion}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors shadow-sm"
                    >
                      Continue Next Step <ArrowRight className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>

              {/* Real-time Feedback & Adaptive Reasoning */}
              {submitted && (
                <div className="p-6 bg-white border border-slate-200 rounded-2xl shadow-sm space-y-4">
                  <div className="flex items-center gap-3">
                    {isCorrect ? (
                      <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold">
                        ✓
                      </div>
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center font-bold">
                        ✕
                      </div>
                    )}
                    <div>
                      <h3 className="font-bold text-slate-900 text-base">
                        {isCorrect ? "Correct answer!" : "Incorrect — Misconception Identified"}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">{currentQ.explanation}</p>
                    </div>
                  </div>

                  {adaptiveFeedback && (
                    <div className="p-4 bg-indigo-50/50 border border-indigo-200 rounded-xl space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-indigo-700 flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5" /> Adaptive Engine Decision
                        </span>
                        <span className="text-xs font-bold uppercase px-2 py-0.5 rounded-full bg-indigo-600 text-white">
                          {adaptiveFeedback.decision}
                        </span>
                      </div>
                      <p className="text-xs text-slate-700 leading-relaxed font-medium">
                        {adaptiveFeedback.reason}
                      </p>
                      <div className="text-[11px] text-slate-500 pt-1 border-t border-indigo-100 flex items-center justify-between">
                        <span>Target Modality: <strong>{adaptiveFeedback.recommended_difficulty || "Standard"}</strong></span>
                        <span>Logged to immutable decision store</span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </main>
      </div>
    </div>
  );
}
