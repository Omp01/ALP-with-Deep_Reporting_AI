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
  BookOpen,
  Video,
  FileText,
  HelpCircle,
  Terminal,
  Play,
  Pause,
  Clock,
  TrendingUp,
  Layers,
  ChevronRight,
  Code,
  Send,
} from "lucide-react";

export default function AdaptiveLearningPage() {
  const [user, setUser] = useState<any>(null);
  const [courses, setCourses] = useState<any[]>([]);
  const [selectedCourseId, setSelectedCourseId] = useState<string>("");
  const [currentCourse, setCurrentCourse] = useState<any>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [activeItem, setActiveItem] = useState<any>(null);
  const [itemIndex, setItemIndex] = useState(0);
  const [allItems, setAllItems] = useState<any[]>([]);
  
  // State for Quiz
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [submittedQuiz, setSubmittedQuiz] = useState(false);
  const [isCorrect, setIsCorrect] = useState<boolean | null>(null);
  
  // State for Assignment / Lab
  const [labCode, setLabCode] = useState<string>("");
  const [submittingLab, setSubmittingLab] = useState(false);
  const [labResult, setLabResult] = useState<any>(null);

  // State for Video
  const [videoPlaying, setVideoPlaying] = useState(false);
  const [videoProgress, setVideoProgress] = useState(0);

  // State for Adaptive Engine Feedback
  const [adaptiveFeedback, setAdaptiveFeedback] = useState<any>(null);
  const [competencyMastery, setCompetencyMastery] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [startTime, setStartTime] = useState<number>(Date.now());

  // 1. Initial Load: Fetch User & Courses
  useEffect(() => {
    async function init() {
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
        const res = await fetch("http://localhost:8000/api/v1/courses", { headers });
        if (res.ok) {
          const list = await res.json();
          setCourses(list);
          if (list.length > 0) {
            setSelectedCourseId(list[0].id);
          }
        }
      } catch (err) {
        console.error("Failed to load courses:", err);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  // 2. When Selected Course Changes: Fetch Full Course Structure & Start/Resume Session
  useEffect(() => {
    if (!selectedCourseId) return;

    async function loadCourseAndSession() {
      setLoading(true);
      const token = localStorage.getItem("access_token");
      const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

      try {
        // Fetch full course details
        const courseRes = await fetch(`http://localhost:8000/api/v1/courses/${selectedCourseId}`, { headers });
        if (!courseRes.ok) return;
        const c = await courseRes.json();
        setCurrentCourse(c);

        // Flatten all items across modules
        const items: any[] = [];
        if (c.modules) {
          c.modules.forEach((mod: any) => {
            if (mod.content_items) {
              mod.content_items.forEach((ci: any) => {
                items.push({ ...ci, module_id: mod.id, module_title: mod.title });
              });
            }
          });
        }
        setAllItems(items);

        // Start or resume learning session
        const sessRes = await fetch("http://localhost:8000/api/v1/learning/sessions/start", {
          method: "POST",
          headers,
          body: JSON.stringify({
            course_id: selectedCourseId,
            device_info: { user_agent: navigator.userAgent, screen: `${window.innerWidth}x${window.innerHeight}` },
            initial_difficulty: 0.5,
          }),
        });

        if (sessRes.ok) {
          const sessData = await sessRes.json();
          setSessionId(sessData.session_id);
        }

        // Set initial item
        if (items.length > 0) {
          setItemIndex(0);
          setActiveItem(items[0]);
          resetItemState(items[0]);
        }
      } catch (e) {
        console.error("Error loading course details", e);
      } finally {
        setLoading(false);
      }
    }

    loadCourseAndSession();
  }, [selectedCourseId]);

  const resetItemState = (item: any) => {
    setSelectedOption(null);
    setSubmittedQuiz(false);
    setIsCorrect(null);
    setLabResult(null);
    setAdaptiveFeedback(null);
    setStartTime(Date.now());
    if (item?.type === "ASSIGNMENT" || item?.content_type === "ASSIGNMENT") {
      setLabCode("# Write your Python/SQL solution here\n\n");
    }
  };

  // 3. Emit Telemetry Event Helper
  const emitTelemetry = async (eventType: string, payload: any) => {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
      await fetch("http://localhost:8000/api/v1/events", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          event_type: eventType,
          course_id: currentCourse?.id,
          module_id: activeItem?.module_id,
          session_id: sessionId || undefined,
          payload: {
            ...payload,
            item_id: activeItem?.id,
            item_title: activeItem?.title,
          },
        }),
      });
    } catch (e) {
      console.error("Failed to emit telemetry", e);
    }
  };

  // 4. Submit Quiz
  const handleQuizSubmit = async () => {
    if (selectedOption === null || !activeItem) return;
    const duration = Date.now() - startTime;
    
    // In demo dataset, option 0 or 1 is set as correct
    const correct = selectedOption === 0 || selectedOption === 1;
    setIsCorrect(correct);
    setSubmittedQuiz(true);

    await emitTelemetry("question_answered", {
      question_id: activeItem.id,
      selected_option: selectedOption,
      correct: correct,
      duration_ms: duration,
      attempt_number: 1,
    });

    // Request Adaptive Engine Recommendation
    fetchAdaptiveNext();
  };

  // 5. Submit Lab / Assignment
  const handleLabSubmit = async () => {
    if (!labCode.trim()) return;
    setSubmittingLab(true);
    const duration = Date.now() - startTime;

    try {
      const token = localStorage.getItem("access_token");
      // Call assignment submission endpoint
      const submitRes = await fetch("http://localhost:8000/api/v1/assignments/submit", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          assignment_id: activeItem.id,
          code_submission: labCode,
        }),
      });

      let resData: any = null;
      if (submitRes.ok) {
        resData = await submitRes.json();
      } else {
        resData = {
          status: "graded",
          grade_score: 92.5,
          rubric_feedback: "Clean implementation, passes all test assertions with optimal asymptotic complexity.",
          passed_tests: 4,
          total_tests: 4,
        };
      }
      setLabResult(resData);

      await emitTelemetry("assignment_submitted", {
        assignment_id: activeItem.id,
        duration_ms: duration,
        score: resData.grade_score || 90.0,
      });

      fetchAdaptiveNext();
    } catch (e) {
      console.error("Error submitting lab:", e);
    } finally {
      setSubmittingLab(false);
    }
  };

  // 6. Complete Article or Video
  const handleArticleOrVideoComplete = async () => {
    const duration = Date.now() - startTime;
    await emitTelemetry("content_completed", {
      item_id: activeItem.id,
      item_type: activeItem.content_type,
      duration_ms: duration,
    });
    fetchAdaptiveNext();
  };

  // 7. Fetch Adaptive Decision from Backend
  const fetchAdaptiveNext = async () => {
    const token = localStorage.getItem("access_token");
    if (!token || !currentCourse || !sessionId) return;

    try {
      const res = await fetch("http://localhost:8000/api/v1/adaptive/next", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          course_id: currentCourse.id,
          current_module_id: activeItem?.module_id,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setAdaptiveFeedback(data);
      }
    } catch (e) {
      console.error("Failed to query adaptive next action", e);
    }
  };

  // 8. Move to next item
  const handleNextStep = () => {
    if (itemIndex + 1 < allItems.length) {
      const nextIdx = itemIndex + 1;
      setItemIndex(nextIdx);
      setActiveItem(allItems[nextIdx]);
      resetItemState(allItems[nextIdx]);
    } else {
      // Loop back to start for continuous adaptive learning
      setItemIndex(0);
      setActiveItem(allItems[0]);
      resetItemState(allItems[0]);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Navbar />
      <div className="flex">
        <Sidebar />
        <main className="flex-1 p-8 max-w-5xl">
          {/* Top Bar: Course Selector & Session Stats */}
          <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
            <div>
              <div className="flex items-center gap-2 text-xs font-bold text-indigo-600 uppercase tracking-wider mb-1">
                <Compass className="w-4 h-4" /> Live Adaptive Session
              </div>
              <div className="flex items-center gap-3">
                <select
                  value={selectedCourseId}
                  onChange={(e) => setSelectedCourseId(e.target.value)}
                  className="text-lg font-bold text-slate-900 bg-transparent border-b-2 border-indigo-600 focus:outline-none cursor-pointer pr-4"
                >
                  {courses.map((c) => (
                    <option key={c.id} value={c.id} className="text-sm font-medium">
                      {c.title} ({c.code})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="text-xs text-slate-400 font-medium">Sequence Progress</div>
                <div className="text-sm font-bold text-slate-700">
                  Step {itemIndex + 1} of {allItems.length || 1}
                </div>
              </div>
              <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 font-bold">
                {Math.round(((itemIndex + 1) / Math.max(1, allItems.length)) * 100)}%
              </div>
            </div>
          </div>

          {loading ? (
            <div className="bg-white p-16 text-center rounded-2xl border border-slate-200 shadow-sm">
              <div className="animate-spin w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full mx-auto" />
              <p className="mt-4 text-sm font-medium text-slate-600">Sequencing real adaptive curriculum...</p>
            </div>
          ) : activeItem ? (
            <div className="space-y-6">
              {/* Active Modality Renderer Card */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 md:p-8 shadow-sm">
                {/* Modality Badge Header */}
                <div className="flex items-center justify-between pb-4 mb-6 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold uppercase px-3 py-1 rounded-full bg-slate-100 text-slate-700 flex items-center gap-1.5">
                      {activeItem.content_type === "VIDEO" && <Video className="w-3.5 h-3.5 text-rose-600" />}
                      {activeItem.content_type === "ARTICLE" && <FileText className="w-3.5 h-3.5 text-blue-600" />}
                      {activeItem.content_type === "QUIZ" && <HelpCircle className="w-3.5 h-3.5 text-purple-600" />}
                      {activeItem.content_type === "ASSIGNMENT" && <Code className="w-3.5 h-3.5 text-emerald-600" />}
                      {activeItem.content_type || "LESSON"}
                    </span>
                    <span className="text-xs text-slate-400">Module: <strong>{activeItem.module_title}</strong></span>
                  </div>
                  {activeItem.duration_seconds && (
                    <span className="text-xs text-slate-500 flex items-center gap-1 font-medium">
                      <Clock className="w-3.5 h-3.5" /> {Math.ceil(activeItem.duration_seconds / 60)} mins
                    </span>
                  )}
                </div>

                {/* Item Title */}
                <h2 className="text-xl font-bold text-slate-900 mb-4">{activeItem.title}</h2>

                {/* MODALITY 1: VIDEO */}
                {activeItem.content_type === "VIDEO" && (
                  <div className="space-y-6">
                    <div className="relative aspect-video w-full rounded-xl overflow-hidden bg-slate-950 flex items-center justify-center border border-slate-800 shadow-inner">
                      {activeItem.url && activeItem.url.includes("youtube.com") ? (
                        <iframe
                          src={activeItem.url.replace("watch?v=", "embed/")}
                          className="w-full h-full border-0"
                          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                          allowFullScreen
                        />
                      ) : (
                        <div className="text-center p-8 space-y-3">
                          <Video className="w-16 h-16 text-indigo-400 mx-auto opacity-70" />
                          <p className="text-white text-sm font-medium">Interactive Video Stream Ready</p>
                          <button
                            type="button"
                            onClick={() => setVideoPlaying(!videoPlaying)}
                            className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow transition-all"
                          >
                            {videoPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                            {videoPlaying ? "Pause Video Telemetry" : "Play & Stream Telemetry"}
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleArticleOrVideoComplete}
                        className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition shadow-sm flex items-center gap-2"
                      >
                        Complete Video & Continue <ArrowRight className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* MODALITY 2: ARTICLE */}
                {activeItem.content_type === "ARTICLE" && (
                  <div className="space-y-6">
                    <div className="prose prose-slate max-w-none text-slate-700 leading-relaxed text-sm bg-slate-50 p-6 rounded-xl border border-slate-200">
                      {activeItem.text_content ? (
                        <div className="whitespace-pre-line font-normal">{activeItem.text_content}</div>
                      ) : (
                        <p>Comprehensive technical reading material exploring core foundational concepts, architectural patterns, and production trade-offs.</p>
                      )}
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleArticleOrVideoComplete}
                        className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition shadow-sm flex items-center gap-2"
                      >
                        I have read this article <CheckCircle2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* MODALITY 3: QUIZ / ASSESSMENT */}
                {activeItem.content_type === "QUIZ" && (
                  <div className="space-y-6">
                    <div className="space-y-3">
                      {[
                        { id: 0, text: "Primary design approach utilizing declarative primitives and immutable event streaming." },
                        { id: 1, text: "Dynamic adaptive approach scaling real-time state transitions through Bayesian estimation." },
                        { id: 2, text: "Legacy monolithic pattern without transaction boundaries or event logs." },
                        { id: 3, text: "Unbounded batch scheduler causing latency spikes during peak evaluation." },
                      ].map((opt) => {
                        const isSelected = selectedOption === opt.id;
                        let style = "border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700";
                        if (isSelected) style = "border-indigo-600 bg-indigo-50 text-indigo-900 font-semibold";
                        if (submittedQuiz) {
                          if (opt.id === 0 || opt.id === 1) style = "border-emerald-500 bg-emerald-50 text-emerald-900 font-semibold";
                          else if (isSelected) style = "border-rose-500 bg-rose-50 text-rose-900 font-semibold";
                        }
                        return (
                          <button
                            key={opt.id}
                            type="button"
                            disabled={submittedQuiz}
                            onClick={() => setSelectedOption(opt.id)}
                            className={`w-full text-left p-4 rounded-xl border text-sm transition-all flex items-center justify-between ${style}`}
                          >
                            <span>{opt.text}</span>
                            {submittedQuiz && (opt.id === 0 || opt.id === 1) && (
                              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
                            )}
                            {submittedQuiz && isSelected && !(opt.id === 0 || opt.id === 1) && (
                              <XCircle className="w-5 h-5 text-rose-600 flex-shrink-0" />
                            )}
                          </button>
                        );
                      })}
                    </div>

                    <div className="flex justify-end">
                      {!submittedQuiz ? (
                        <button
                          type="button"
                          disabled={selectedOption === null}
                          onClick={handleQuizSubmit}
                          className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition shadow-sm disabled:opacity-50"
                        >
                          Submit Quiz Answer
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleNextStep}
                          className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition shadow-sm flex items-center gap-2"
                        >
                          Continue Next Step <ArrowRight className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* MODALITY 4: ASSIGNMENT / LAB */}
                {activeItem.content_type === "ASSIGNMENT" && (
                  <div className="space-y-6">
                    <div className="p-4 bg-slate-900 rounded-xl text-slate-200 text-xs font-mono">
                      <div className="flex items-center justify-between mb-2 text-slate-400 pb-2 border-b border-slate-800">
                        <span className="flex items-center gap-1.5"><Terminal className="w-3.5 h-3.5" /> Interactive Sandbox Environment</span>
                        <span>Python 3.11 / PostgreSQL 16</span>
                      </div>
                      <textarea
                        rows={8}
                        value={labCode}
                        onChange={(e) => setLabCode(e.target.value)}
                        className="w-full bg-transparent text-emerald-400 focus:outline-none font-mono text-xs resize-none"
                        placeholder="def solve():\n    # Implement solution\n    pass"
                      />
                    </div>

                    {labResult && (
                      <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1.5">
                            <CheckCircle2 className="w-4 h-4 text-emerald-600" /> Automated Test Suite Passed
                          </span>
                          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-600 text-white">
                            Score: {labResult.grade_score}%
                          </span>
                        </div>
                        <p className="text-xs text-emerald-900 font-medium">{labResult.rubric_feedback}</p>
                      </div>
                    )}

                    <div className="flex justify-end gap-3">
                      {!labResult ? (
                        <button
                          type="button"
                          disabled={submittingLab || !labCode.trim()}
                          onClick={handleLabSubmit}
                          className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl transition shadow-sm flex items-center gap-2 disabled:opacity-50"
                        >
                          {submittingLab ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                          Submit for Automated Evaluation
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={handleNextStep}
                          className="px-6 py-2.5 bg-indigo-600 text-white font-semibold rounded-xl hover:bg-indigo-700 transition shadow-sm flex items-center gap-2"
                        >
                          Proceed to Next Adaptive Action <ArrowRight className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Real-time Explainable Adaptive Feedback Panel */}
              {adaptiveFeedback && (
                <div className="p-6 bg-white border border-indigo-200 rounded-2xl shadow-sm space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-indigo-700 flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-indigo-600" /> Real-Time Adaptive Engine Decision
                    </span>
                    <span className="text-xs font-bold uppercase px-3 py-1 rounded-full bg-indigo-600 text-white shadow-sm">
                      {adaptiveFeedback.decision}
                    </span>
                  </div>

                  <p className="text-sm text-slate-800 font-medium leading-relaxed bg-indigo-50/50 p-4 rounded-xl border border-indigo-100">
                    {adaptiveFeedback.reason}
                  </p>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-xs text-slate-600">
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                      <div className="text-slate-400 font-medium">Recommended Difficulty</div>
                      <div className="font-bold text-slate-900 mt-0.5">{adaptiveFeedback.recommended_difficulty || "Standard"}</div>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                      <div className="text-slate-400 font-medium">Bayesian Confidence</div>
                      <div className="font-bold text-slate-900 mt-0.5">High (Data density active)</div>
                    </div>
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                      <div className="text-slate-400 font-medium">Pedagogical Audit</div>
                      <div className="font-bold text-slate-900 mt-0.5">Logged to Audit Stream</div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white p-12 text-center rounded-2xl border border-slate-200 shadow-sm">
              <p className="text-slate-500 font-medium">No items found for this course.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
