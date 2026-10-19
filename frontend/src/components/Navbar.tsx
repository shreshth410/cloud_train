import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import {
  BrainCircuit,
  Database,
  Layers,
  Sparkles,
  Info,
  LogOut,
  User,
  Zap,
} from "lucide-react";

export const Navbar: React.FC = () => {
  const { user, logout, bypassLogin, isAuthenticated } = useAuth();
  const location = useLocation();

  const navLinks = [
    { to: "/", label: "Dashboard", icon: Layers },
    { to: "/datasets", label: "Datasets", icon: Database },
    { to: "/train", label: "New Training", icon: Sparkles, highlight: true },
    { to: "/jobs", label: "Jobs", icon: BrainCircuit },
    { to: "/about", label: "Architecture", icon: Info },
  ];

  return (
    <header className="sticky top-0 z-50 backdrop-blur-md bg-[#080d1a]/85 border-b border-slate-800/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20 group-hover:scale-105 transition-transform duration-200">
            <Zap className="w-5 h-5 text-white fill-white/20" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                CloudTrain
              </span>
              <span className="text-[10px] font-semibold tracking-wider uppercase px-1.5 py-0.5 rounded bg-cyan-950/70 border border-cyan-800/60 text-cyan-400">
                AWS Zero-Cost
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono hidden sm:block">
              Serverless ML Platform
            </p>
          </div>
        </Link>

        {/* Navigation items */}
        {isAuthenticated && (
          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-150 ${
                    item.highlight
                      ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-md shadow-cyan-500/25 hover:brightness-110"
                      : isActive
                      ? "bg-slate-800 text-cyan-400 border border-slate-700 shadow-sm"
                      : "text-slate-300 hover:text-white hover:bg-slate-800/60"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-cyan-400" : ""}`} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        )}

        {/* User / Auth Section */}
        <div className="flex items-center gap-3">
          {isAuthenticated ? (
            <div className="flex items-center gap-3">
              <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-xs">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <User className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-slate-300 max-w-[150px] truncate" title={user?.email}>
                  {user?.email}
                </span>
              </div>
              <button
                onClick={logout}
                title="Sign out"
                className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-rose-400 hover:border-rose-900/50 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={bypassLogin}
                className="text-xs px-3 py-1.5 rounded-lg bg-cyan-950/60 border border-cyan-800/60 text-cyan-300 hover:bg-cyan-900/60 transition-colors"
              >
                Local Dev Guest
              </button>
              <Link
                to="/login"
                className="text-xs px-3.5 py-1.5 rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition-colors"
              >
                Sign In
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
