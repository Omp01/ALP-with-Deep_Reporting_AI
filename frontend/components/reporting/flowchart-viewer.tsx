"use client";

import React, { useEffect, useRef, useState } from "react";
import { Download, Code, Sparkles, RefreshCw, ZoomIn, AlertTriangle } from "lucide-react";
import { Button, Badge } from "@/components/ui";

interface FlowchartViewerProps {
  mermaidCode: string;
  id?: string;
}

export function FlowchartViewer({ mermaidCode, id = "mermaid-svg" }: FlowchartViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [showRawCode, setShowRawCode] = useState<boolean>(false);

  useEffect(() => {
    let isMounted = true;
    const renderDiagram = async () => {
      if (!mermaidCode) return;
      try {
        setRenderError(null);
        const mermaidModule = await import("mermaid");
        const mermaid = mermaidModule.default || mermaidModule;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "loose",
          flowchart: {
            useMaxWidth: true,
            htmlLabels: true,
            curve: "basis",
          },
        });

        const uniqueId = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(uniqueId, mermaidCode);
        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err: any) {
        console.error("Mermaid render error:", err);
        if (isMounted) {
          setRenderError("Could not render visual diagram. Showing raw flowchart syntax below.");
        }
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [mermaidCode]);

  const downloadSvg = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `flowchart_report_${Date.now()}.svg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-3">
      {/* Action Toolbar */}
      <div className="flex items-center justify-between bg-slate-900 text-slate-200 px-4 py-2.5 rounded-t-xl border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-slate-100">Interactive Visual Diagram</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowRawCode(!showRawCode)}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition-colors flex items-center gap-1.5"
          >
            <Code className="w-3.5 h-3.5 text-indigo-400" />
            {showRawCode ? "Hide Mermaid Syntax" : "View Syntax"}
          </button>
          <button
            onClick={downloadSvg}
            disabled={!svgContent}
            className="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            Export SVG
          </button>
        </div>
      </div>

      {/* Raw Code View Toggle */}
      {showRawCode && (
        <div className="p-4 bg-slate-950 rounded-lg border border-slate-800">
          <div className="text-[11px] font-mono text-slate-400 mb-2">Mermaid.js Definition Syntax:</div>
          <pre className="text-xs font-mono text-indigo-300 overflow-x-auto leading-relaxed">{mermaidCode}</pre>
        </div>
      )}

      {/* Diagram Canvas Box */}
      <div className="bg-white border border-slate-200 rounded-b-xl p-6 min-h-[300px] flex items-center justify-center overflow-x-auto shadow-inner">
        {renderError ? (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto" />
            <p className="text-xs font-medium text-slate-700">{renderError}</p>
            <pre className="p-3 bg-slate-100 rounded text-xs font-mono text-slate-800 max-w-xl overflow-x-auto text-left mx-auto">
              {mermaidCode}
            </pre>
          </div>
        ) : svgContent ? (
          <div
            ref={containerRef}
            className="w-full flex justify-center [&>svg]:max-w-full [&>svg]:h-auto font-sans"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <div className="flex items-center gap-2 text-slate-400 text-xs">
            <RefreshCw className="w-4 h-4 animate-spin text-indigo-600" />
            Rendering visual flowchart...
          </div>
        )}
      </div>
    </div>
  );
}
