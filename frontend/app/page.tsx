"use client";

import React, { FormEvent, useState, useEffect } from "react";

type Extraction = {
  function: string | null;
  inputs: unknown[] | null;
  expected: unknown;
  observed: unknown;
  version: string | null;
  confidence: number | null;
};

type Analysis = {
  status: "reproduced" | "not_reproducible" | "insufficient_info";
  extracted: Extraction | null;
  generated_test: string | null;
  run_output: string | null;
  explanation: string;
  duration_ms: number;
};

function getApiUrl(): string {
  let url = process.env.NEXT_PUBLIC_API_URL;
  if (!url || url.includes("localhost") || url.includes("127.0.0.1")) {
    if (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
      url = "https://repodoctor-production.up.railway.app";
    } else {
      url = "http://localhost:8000";
    }
  }
  url = url.trim().replace(/\/$/, "");
  if (!url.startsWith("http://") && !url.startsWith("https://")) {
    url = `https://${url}`;
  }
  return url;
}

// Pre-scripted reports for easy demo testing
const DEMO_PRESETS = [
  {
    id: "report_a",
    label: "🔴 Overflow (Report A)",
    title: "Loyalty points go negative for high-spend customers",
    body: "add_loyalty_points(2147483647, 1) returns a negative number. It should return 2147483648. Our top customers' balances flipped negative overnight.",
  },
  {
    id: "report_b",
    label: "🔴 Truncation (Report B)",
    title: "Splitting a bill loses money",
    body: "split_payment(100, 3) returns [33, 33, 33], which only adds up to 99. One cent disappears every time. Expected the shares to sum back to 100.",
  },
  {
    id: "report_c",
    label: "🔴 Double Coupon (Report C)",
    title: "20% coupon takes 40% off",
    body: "apply_coupon(100, 20) returns 60 but a 20% coupon should leave 80. We lost margin on every promo order.",
  },
  {
    id: "report_d",
    label: "🔴 Rate Limit (Report D)",
    title: "Rate limiter allows one request too many",
    body: "is_within_rate_limit(100, 100) returns True, so a client at the limit still gets through. At exactly the limit it should return False.",
  },
  {
    id: "report_e",
    label: "🔴 Timeout Hang (Report E)",
    title: "find_next_leap_year hangs the worker",
    body: "find_next_leap_year(2001) never returns and pins a CPU. It should return 2004.",
  },
  {
    id: "report_f",
    label: "🔴 Input Validation (Report F)",
    title: "Negative quantity produces a negative charge",
    body: "cart_total(50, -2) returns -100 — the store would refund an attacker. It should reject a negative quantity with a ValueError.",
  },
  {
    id: "report_g",
    label: "🟢 Correct Interest (Report G)",
    title: "Interest calculation is broken",
    body: "calculate_interest(1000, 5, 2) returns 100 but I expected 105.",
  },
  {
    id: "report_h",
    label: "🟡 Vague (Report H)",
    title: "it doesn't work",
    body: "billing is wrong please fix everything",
  },
];

export default function Home() {
  const [title, setTitle] = useState(DEMO_PRESETS[0].title);
  const [body, setBody] = useState(DEMO_PRESETS[0].body);
  const [result, setResult] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"extracted" | "test" | "output">("extracted");
  const [providers, setProviders] = useState<Record<string, boolean>>({
    gemini: false,
    openai: false,
    groq: false,
    grok: false,
    openrouter: false,
  });
  const [selectedProvider, setSelectedProvider] = useState<string>("gemini");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [copiedText, setCopiedText] = useState(false);

  // Load provider configurations
  useEffect(() => {
    async function fetchProviders() {
      try {
        const response = await fetch(`${getApiUrl()}/providers`);
        if (response.ok) {
          const data = await response.json();
          setProviders(data.providers);
          setSelectedProvider(data.default);
        }
      } catch (e) {
        console.error("Failed to load providers", e);
      }
    }
    fetchProviders();
  }, []);

  // Live health connectivity check
  useEffect(() => {
    async function checkHealth() {
      try {
        const res = await fetch(`${getApiUrl()}/health`);
        setApiOnline(res.ok);
      } catch (e) {
        setApiOnline(false);
      }
    }
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${getApiUrl()}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body, provider: selectedProvider }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? payload.error ?? "Analysis could not be completed.");
      }
      setResult(payload as Analysis);
      if (payload.status === "insufficient_info" || !payload.generated_test) {
        setActiveTab("extracted");
      } else {
        setActiveTab("test");
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reach RepoDoctor.");
    } finally {
      setLoading(false);
    }
  }

  function handlePresetSelect(preset: typeof DEMO_PRESETS[number]) {
    setTitle(preset.title);
    setBody(preset.body);
  }

  const handleCopyCode = (text: string | null) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedText(true);
    setTimeout(() => setCopiedText(false), 2000);
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-[#070913] text-slate-100 selection:bg-indigo-500/30 font-sans">
      {/* Dynamic Glowing Accents */}
      <div className="absolute left-[-10%] top-[-10%] -z-10 h-[600px] w-[600px] rounded-full bg-gradient-to-tr from-indigo-600/10 to-violet-600/10 blur-[140px] opacity-70" />
      <div className="absolute right-[-5%] bottom-[-5%] -z-10 h-[700px] w-[700px] rounded-full bg-gradient-to-br from-purple-600/5 to-pink-600/5 blur-[160px] opacity-55" />

      <main className="mx-auto max-w-7xl px-6 py-14 sm:px-8 lg:px-12">
        {/* Top Header Section */}
        <header className="mb-14 border-b border-slate-800/40 pb-8">
          <div className="flex flex-col items-center justify-between gap-6 lg:flex-row">
            <div className="flex flex-col items-center gap-5 lg:flex-row lg:items-start text-center lg:text-left">
              <img
                src="/logo.png"
                alt="RepoDoctor Logo"
                className="h-20 w-20 rounded-2xl border border-indigo-500/20 shadow-lg shadow-indigo-500/10 object-contain bg-[#0a0d17]"
              />
              <div>
                <div className="inline-flex items-center gap-2.5 rounded-full border border-indigo-500/20 bg-indigo-950/20 px-3.5 py-1.5 text-xs font-semibold uppercase tracking-wider text-indigo-400 backdrop-blur-md">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75"></span>
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500"></span>
                  </span>
                  RepoDoctor — AI Sandbox Triage
                </div>
                <h1 className="mt-4 bg-gradient-to-r from-slate-100 via-indigo-100 to-slate-400 bg-clip-text text-4xl font-black tracking-tight text-transparent sm:text-5xl lg:text-6xl">
                  Prove Bug Reports
                </h1>
                <p className="mt-4 max-w-3xl text-lg text-slate-400 leading-relaxed">
                  Extract natural language claims with LLMs, generate test suites, and execute code assertions automatically inside a secure Docker sandbox.
                </p>
              </div>
            </div>
            
            {/* Live API Health Check Badge */}
            <div className="flex items-center gap-3">
              <div className={`flex items-center gap-2.5 rounded-xl border px-4 py-2.5 text-sm font-semibold transition-all duration-300 backdrop-blur-md ${
                apiOnline === null
                  ? "border-amber-500/20 bg-amber-500/5 text-amber-400"
                  : apiOnline
                  ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400 shadow-lg shadow-emerald-500/5"
                  : "border-red-500/20 bg-red-500/5 text-red-400"
              }`}>
                <span className={`relative flex h-2 w-2 ${apiOnline ? "animate-pulse" : ""}`}>
                  <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    apiOnline === null ? "bg-amber-400 animate-ping" : apiOnline ? "bg-emerald-400 animate-ping" : "bg-red-400"
                  }`}></span>
                  <span className={`relative inline-flex h-2 w-2 rounded-full ${
                    apiOnline === null ? "bg-amber-500" : apiOnline ? "bg-emerald-500" : "bg-red-500"
                  }`}></span>
                </span>
                {apiOnline === null ? "Connecting API..." : apiOnline ? "Sandbox API Online" : "Sandbox API Offline"}
              </div>
            </div>
          </div>
        </header>

        {/* Quick presets row */}
        <section className="mb-10 rounded-2xl border border-slate-800/60 bg-slate-900/20 p-5 backdrop-blur-md">
          <div className="flex items-center gap-2 mb-3">
            <svg className="h-4 w-4 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Demo Presets (Quick Fill)</h2>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {DEMO_PRESETS.map((preset) => {
              const isSelected = title === preset.title && body === preset.body;
              return (
                <button
                  key={preset.id}
                  onClick={() => handlePresetSelect(preset)}
                  type="button"
                  className={`rounded-xl px-4 py-2.5 text-xs font-semibold border transition-all duration-200 active:scale-[0.98] ${
                    isSelected
                      ? "bg-indigo-600/10 border-indigo-500/80 text-indigo-300 shadow-lg shadow-indigo-500/5 ring-1 ring-indigo-500/30"
                      : "bg-slate-950/40 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200 hover:bg-slate-900/50"
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </section>

        {/* Master Dashboard Panel */}
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
          
          {/* LEFT: Bug Report Form Card */}
          <section className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/30 p-6 shadow-2xl backdrop-blur-xl hover:border-slate-800 transition duration-300">
              <h2 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
                Submit Bug Report
              </h2>
              <p className="mt-1.5 text-sm text-slate-400">Enter details to automatically reproduce and test</p>

              <form className="mt-7 space-y-6" onSubmit={submit}>
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400" htmlFor="title">
                    Issue Title
                  </label>
                  <input
                    className="mt-2.5 w-full rounded-xl border border-slate-800 bg-[#0b0e1a]/90 px-4 py-3 text-sm text-slate-100 placeholder-slate-600 outline-none ring-indigo-500/40 transition duration-200 focus:border-indigo-500/80 focus:ring-4"
                    id="title"
                    placeholder="e.g. get_discount returns wrong value"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400" htmlFor="body">
                    Issue Details (Body)
                  </label>
                  <textarea
                    className="mt-2.5 min-h-[180px] w-full rounded-xl border border-slate-800 bg-[#0b0e1a]/90 px-4 py-3 text-sm text-slate-100 placeholder-slate-600 outline-none ring-indigo-500/40 transition duration-200 focus:border-indigo-500/80 focus:ring-4 font-mono text-[13px] leading-relaxed"
                    id="body"
                    placeholder="Describe inputs and expected vs observed results..."
                    required
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400">
                    AI Service Provider
                  </label>
                  <div className="mt-2.5 grid grid-cols-5 gap-2">
                    {["gemini", "openai", "groq", "grok", "openrouter"].map((prov) => {
                      const isAvailable = providers[prov];
                      const isSelected = selectedProvider === prov;
                      return (
                        <button
                          key={prov}
                          type="button"
                          onClick={() => isAvailable && setSelectedProvider(prov)}
                          disabled={!isAvailable}
                          className={`rounded-xl py-3 text-xs font-bold border flex flex-col items-center justify-center transition-all duration-200 active:scale-[0.96] ${
                            isSelected
                              ? "bg-indigo-600/15 border-indigo-500/80 text-indigo-300 ring-2 ring-indigo-500/20"
                              : isAvailable
                              ? "bg-slate-950/50 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200 hover:bg-slate-900/80"
                              : "bg-slate-950/20 border-slate-900/60 text-slate-600 cursor-not-allowed opacity-40"
                          }`}
                        >
                          <span className="capitalize">{prov === "openrouter" ? "OpenRouter" : prov}</span>
                          <span className={`text-[9px] mt-1 font-semibold ${isAvailable ? "text-emerald-500/80" : "text-slate-600"}`}>
                            {isAvailable ? "Active" : "Locked"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <button
                  className="relative w-full overflow-hidden rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-700 to-violet-700 py-3.5 font-bold text-white transition-all duration-300 hover:shadow-lg hover:shadow-indigo-500/10 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={loading}
                  type="submit"
                >
                  <span className="relative flex items-center justify-center gap-2">
                    {loading ? (
                      <>
                        <svg className="h-4.5 w-4.5 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Triaging Bug Report...
                      </>
                    ) : (
                      <>
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        Analyze & Test Report
                      </>
                    )}
                  </span>
                </button>
              </form>
            </div>

            {error && (
              <div className="mt-4 rounded-xl border border-rose-500/20 bg-rose-500/5 p-4.5 text-sm text-rose-400 backdrop-blur-md">
                <div className="flex gap-2">
                  <svg className="h-5 w-5 shrink-0 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <span className="font-bold">Error encountered:</span>
                    <p className="mt-1 text-xs text-rose-500/80 font-mono leading-relaxed">{error}</p>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* RIGHT: Triaging Output Panel */}
          <section className="lg:col-span-7">
            {result ? (
              <div className="space-y-6">
                {/* Result Summary Card Banner */}
                <div
                  className={`rounded-2xl border p-6 shadow-2xl backdrop-blur-xl transition-all duration-300 relative overflow-hidden ${
                    result.status === "reproduced"
                      ? "border-rose-500/30 bg-rose-950/10 shadow-rose-950/10"
                      : result.status === "not_reproducible"
                      ? "border-emerald-500/30 bg-emerald-950/10 shadow-emerald-950/10"
                      : "border-amber-500/30 bg-amber-950/10 shadow-amber-950/10"
                  }`}
                >
                  <div className="absolute right-0 top-0 h-40 w-40 rounded-full blur-[70px] opacity-10 -z-10 bg-current" />
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      {result.status === "reproduced" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 px-4.5 py-1 text-xs font-bold uppercase tracking-wider text-rose-400">
                          🔴 Reproduced (Bug Real)
                        </span>
                      )}
                      {result.status === "not_reproducible" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-4.5 py-1 text-xs font-bold uppercase tracking-wider text-emerald-400">
                          🟢 Not Reproducible
                        </span>
                      )}
                      {result.status === "insufficient_info" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-4.5 py-1 text-xs font-bold uppercase tracking-wider text-amber-400">
                          🟡 Insufficient Info
                        </span>
                      )}
                    </div>
                    <span className="rounded-xl bg-slate-950/60 border border-slate-800/80 px-3.5 py-1.5 text-xs text-slate-400 font-mono">
                      ⏱️ {result.duration_ms} ms
                    </span>
                  </div>

                  <p className="mt-4.5 text-base leading-relaxed text-slate-200 font-semibold">{result.explanation}</p>
                </div>

                {/* IDE / Output Tabbed Inspector */}
                <div className="overflow-hidden rounded-2xl border border-slate-850 bg-slate-950/80 shadow-2xl">
                  {/* macOS IDE header styling */}
                  <div className="flex items-center justify-between border-b border-slate-900 bg-slate-900/40 px-4 py-3">
                    <div className="flex gap-1.5">
                      <span className="h-3 w-3 rounded-full bg-rose-500/80" />
                      <span className="h-3 w-3 rounded-full bg-amber-500/80" />
                      <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
                    </div>
                    
                    {/* tab group */}
                    <div className="flex gap-1 border border-slate-800 bg-[#0e111d] p-1 rounded-xl">
                      <button
                        onClick={() => setActiveTab("extracted")}
                        className={`rounded-lg px-3 py-1.5 text-xs font-bold transition duration-200 ${
                          activeTab === "extracted"
                            ? "bg-indigo-600/15 text-indigo-300 border border-indigo-500/20"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        Claims Contract
                      </button>
                      {result.generated_test && (
                        <button
                          onClick={() => setActiveTab("test")}
                          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition duration-200 ${
                            activeTab === "test"
                              ? "bg-indigo-600/15 text-indigo-300 border border-indigo-500/20"
                              : "text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          test_generated.py
                        </button>
                      )}
                      {result.run_output && (
                        <button
                          onClick={() => setActiveTab("output")}
                          className={`rounded-lg px-3 py-1.5 text-xs font-bold transition duration-200 ${
                            activeTab === "output"
                              ? "bg-indigo-600/15 text-indigo-300 border border-indigo-500/20"
                              : "text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          Sandbox Logs
                        </button>
                      )}
                    </div>
                    
                    <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold font-mono">INSPECTOR</span>
                  </div>

                  {/* Tab Panels */}
                  <div className="p-6 font-mono text-sm leading-6">
                    
                    {/* Tab 1: Extracted contract tables */}
                    {activeTab === "extracted" && (
                      <div className="space-y-4">
                        {result.extracted ? (
                          <div className="divide-y divide-slate-900 border border-slate-900 rounded-xl overflow-hidden bg-[#0a0d17]/40 text-slate-300">
                            <div className="flex justify-between px-4.5 py-3 hover:bg-slate-900/10">
                              <span className="text-slate-500 text-xs uppercase tracking-wider font-bold">Target Function</span>
                              <span className="font-semibold text-indigo-300">{result.extracted.function ?? "None"}</span>
                            </div>
                            <div className="flex justify-between px-4.5 py-3 hover:bg-slate-900/10">
                              <span className="text-slate-500 text-xs uppercase tracking-wider font-bold">Inputs</span>
                              <span className="text-slate-100 font-semibold">{JSON.stringify(result.extracted.inputs)}</span>
                            </div>
                            <div className="flex justify-between px-4.5 py-3 hover:bg-slate-900/10">
                              <span className="text-slate-500 text-xs uppercase tracking-wider font-bold">Expected Value</span>
                              <span className="text-emerald-400 font-semibold">{JSON.stringify(result.extracted.expected)}</span>
                            </div>
                            <div className="flex justify-between px-4.5 py-3 hover:bg-slate-900/10">
                              <span className="text-slate-500 text-xs uppercase tracking-wider font-bold">Observed Value</span>
                              <span className="text-rose-400 font-semibold">{JSON.stringify(result.extracted.observed)}</span>
                            </div>
                            <div className="flex justify-between px-4.5 py-3 hover:bg-slate-900/10">
                              <span className="text-slate-500 text-xs uppercase tracking-wider font-bold">Confidence</span>
                              <span className="text-amber-400 font-semibold">{(result.extracted.confidence ?? 0.0) * 100}%</span>
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-500 italic text-center py-4">No structured data was extracted.</p>
                        )}
                      </div>
                    )}

                    {/* Tab 2: test_generated.py syntax code block */}
                    {activeTab === "test" && (
                      <div className="relative">
                        <button
                          onClick={() => handleCopyCode(result.generated_test)}
                          className="absolute right-0 top-0 rounded-lg border border-slate-800 bg-[#0e111d] px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200 transition active:scale-95"
                        >
                          {copiedText ? "Copied!" : "Copy Code"}
                        </button>
                        <pre className="overflow-x-auto text-[#b4c6fc] text-xs pt-8 select-all font-mono leading-relaxed bg-[#0a0d17]/30 p-4 rounded-xl border border-slate-900">
                          <code>{result.generated_test}</code>
                        </pre>
                      </div>
                    )}

                    {/* Tab 3: Sandbox output logs */}
                    {activeTab === "output" && (
                      <pre className="overflow-x-auto text-slate-300 text-xs select-text font-mono leading-relaxed bg-[#0a0d17]/30 p-4 rounded-xl border border-slate-900 whitespace-pre-wrap">
                        <code>{result.run_output}</code>
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800/80 bg-slate-900/5 p-8 text-center text-slate-500 backdrop-blur-md">
                <div className="h-14 w-14 rounded-2xl bg-indigo-600/5 flex items-center justify-center border border-indigo-500/10 shadow-lg shadow-indigo-500/5">
                  <svg
                    className="h-7 w-7 text-indigo-400 animate-pulse"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"
                    />
                  </svg>
                </div>
                <h3 className="mt-4 font-extrabold text-slate-300 text-lg">Sandbox Idle</h3>
                <p className="mt-2.5 max-w-sm text-sm text-slate-500 leading-relaxed">
                  Select a quickpreset above or enter custom parameters on the left to activate secure verification.
                </p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
