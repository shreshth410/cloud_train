import React from "react";
import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar";
import { ShieldCheck, Cloud, Cpu } from "lucide-react";

export const Layout: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#080d1a] text-slate-100 relative overflow-x-hidden selection:bg-cyan-500/20 selection:text-cyan-300">
      {/* Subtle ambient lighting gradients */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-cyan-600/10 rounded-full blur-[140px] pointer-events-none -z-10" />
      <div className="absolute top-1/3 right-10 w-[600px] h-[600px] bg-indigo-600/10 rounded-full blur-[160px] pointer-events-none -z-10" />

      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-800/80 bg-[#060913]/90 py-6 mt-16 text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-slate-200">CloudTrain</span>
            <span>•</span>
            <span>Zero-Cost Serverless Machine Learning</span>
          </div>

          <div className="flex items-center gap-6 text-slate-400">
            <div className="flex items-center gap-1.5 text-emerald-400/90">
              <ShieldCheck className="w-4 h-4" />
              <span>Cost Guardrails Active ($10 Budget)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Auto-Terminating EC2</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Cloud className="w-4 h-4 text-indigo-400" />
              <span>AWS Serverless</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};
