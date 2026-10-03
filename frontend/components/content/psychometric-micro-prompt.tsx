"use client";

import React, { useState, useEffect } from "react";
import { CheckCircle2, Sparkles, X, HelpCircle, Loader2 } from "lucide-react";
import { reportsService } from "@/services/reports";
import { PsychometricQuestion } from "@/types/learning";

interface PsychometricMicroPromptProps {
  stage: string;
  courseId?: string | null;
  moduleId?: string | null;
  contentItemId?: string | null;
  topic?: string | null;
  onResponseSubmitted?: () => void;
  className?: string;
}

const CONSTRUCT_LABELS: Record<string, { title: string; color: string }> = {
  confidence: { title: "Confidence Check", color: "bg-indigo-500/10 text-indigo-400 border-indigo-500/20" },
  perceived_understanding: { title: "Understanding Check", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
  cognitive_effort: { title: "Mental Effort", color: "bg-amber-500/10 text-amber-400 border-amber-500/20" },
  learning_difficulty: { title: "Pacing & Difficulty", color: "bg-orange-500/10 text-orange-400 border-orange-500/20" },
  application_readiness: { title: "Application Readiness", color: "bg-blue-500/10 text-blue-400 border-blue-500/20" },
  retention_confidence: { title: "Recall Confidence", color: "bg-purple-500/10 text-purple-400 border-purple-500/20" },
  engagement: { title: "Engagement", color: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20" },
  self_assessed_mastery: { title: "Self-Mastery", color: "bg-teal-500/10 text-teal-400 border-teal-500/20" },
  reflection: { title: "Growth Reflection", color: "bg-pink-500/10 text-pink-400 border-pink-500/20" },
  motivation: { title: "Learning Motivation", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" },
};

export function PsychometricMicroPrompt({
  stage,
  courseId,
  moduleId,
  contentItemId,
  topic,
  onResponseSubmitted,
  className = "",
}: PsychometricMicroPromptProps) {
  const [question, setQuestion] = useState<PsychometricQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submittedValue, setSubmittedValue] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [thankYouMessage, setThankYouMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const controller = new AbortController();

    async function fetchPrompt() {
      try {
        setLoading(true);
        const res = await reportsService.getPsychometricPrompt(
          stage,
          {
            course_id: courseId || undefined,
            module_id: moduleId || undefined,
            content_item_id: contentItemId || undefined,
            topic: topic || undefined,
          },
          controller.signal
        );
        if (isMounted) {
          setQuestion(res.prompt);
        }
      } catch (err) {
        // Cooldown or error, gracefully stay silent
        if (isMounted) setQuestion(null);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchPrompt();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [stage, courseId, moduleId, contentItemId, topic]);

  if (loading || dismissed || !question) {
    return null;
  }

  const constructMeta = CONSTRUCT_LABELS[question.construct] || {
    title: "Learning Check-In",
    color: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  };

  const minScale = question.scale_min ?? 1;
  const maxScale = question.scale_max ?? 5;
  const scaleRange = Array.from({ length: maxScale - minScale + 1 }, (_, i) => minScale + i);
  const labels = question.scale_labels || {};

  const handleSelectOption = async (val: number) => {
    if (submitting || submittedValue !== null) return;
    setSubmitting(true);
    setSubmittedValue(val);

    try {
      const receipt = await reportsService.submitPsychometricResponse({
        question_id: question.id,
        raw_response: { value: val },
        course_id: courseId,
        module_id: moduleId,
        content_item_id: contentItemId,
        topic: topic,
      });

      setThankYouMessage(
        receipt.acknowledgment_message ||
          "Thank you for sharing your learning signal! Calibration updated."
      );
      if (onResponseSubmitted) {
        onResponseSubmitted();
      }

      // Auto dismiss after 3 seconds
      setTimeout(() => {
        setDismissed(true);
      }, 3500);
    } catch (err) {
      console.error("Failed to submit psychometric response:", err);
      setSubmitting(false);
      setSubmittedValue(null);
    }
  };

  if (thankYouMessage) {
    return (
      <div
        className={`relative overflow-hidden rounded-xl border border-emerald-500/30 bg-gradient-to-r from-emerald-950/40 via-slate-900/80 to-slate-900/90 p-4 shadow-lg backdrop-blur-md transition-all duration-500 animate-in fade-in slide-in-from-bottom-2 ${className}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-emerald-200">Signal Recorded</p>
              <p className="text-xs text-slate-300">{thankYouMessage}</p>
            </div>
          </div>
          <button
            onClick={() => setDismissed(true)}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow-xl backdrop-blur-md transition-all hover:border-slate-700/80 animate-in fade-in slide-in-from-bottom-3 ${className}`}
    >
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${constructMeta.color}`}
          >
            <Sparkles className="h-3 w-3" />
            {constructMeta.title}
          </span>
          <span className="text-[11px] text-slate-500 font-mono tracking-wide uppercase">
            Quick 1-Click Reflection
          </span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-slate-500 hover:text-slate-300 p-1 rounded-md transition-colors"
          title="Dismiss check-in"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <p className="text-sm font-medium text-slate-200 mb-3 leading-relaxed">
        {question.question_text}
      </p>

      {/* Likert Scale Buttons */}
      <div className="grid grid-cols-5 gap-2">
        {scaleRange.map((val) => {
          const isSelected = submittedValue === val;
          const labelText = labels[String(val)] || "";
          return (
            <button
              key={val}
              type="button"
              disabled={submitting}
              onClick={() => handleSelectOption(val)}
              className={`group flex flex-col items-center justify-center p-2.5 rounded-lg border text-center transition-all ${
                isSelected
                  ? "border-emerald-500 bg-emerald-500/20 text-emerald-300 scale-95"
                  : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-indigo-500/60 hover:bg-indigo-950/30 hover:text-white"
              } disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              <span className="text-base font-bold transition-transform group-hover:scale-110">
                {val}
              </span>
              {labelText && (
                <span className="text-[10px] text-slate-400 mt-1 line-clamp-1 group-hover:text-slate-200">
                  {labelText}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {submitting && (
        <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center gap-2 rounded-xl">
          <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
          <span className="text-xs text-indigo-200 font-medium">Recording learning signal...</span>
        </div>
      )}
    </div>
  );
}
