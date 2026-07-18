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

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
    grok: false,
  });
  const [selectedProvider, setSelectedProvider] = useState<string>("gemini");

  useEffect(() => {
    async function fetchProviders() {
      try {
        const response = await fetch(`${API_URL}/providers`);
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

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, body, provider: selectedProvider }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? payload.error ?? "Analysis could not be completed.");
      }
      setResult(payload as Analysis);
      // Auto switch tabs depending on result status
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

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-slate-950 text-slate-100 selection:bg-indigo-500/30">
      {/* Decorative background glow */}
      <div className="absolute left-1/4 top-0 -z-10 h-[500px] w-[500px] rounded-full bg-indigo-500/10 blur-[120px]" />
      <div className="absolute right-1/4 bottom-10 -z-10 h-[600px] w-[600px] rounded-full bg-purple-500/5 blur-[150px]" />

      <main className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        {/* Header */}
        <header className="mb-12 text-center lg:text-left">
          <div className="flex flex-col items-center justify-between gap-4 lg:flex-row">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/5 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-indigo-400">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500"></span>
                </span>
                RepoDoctor — AI Sandbox Triage
              </div>
              <h1 className="mt-4 bg-gradient-to-r from-indigo-200 via-indigo-100 to-slate-400 bg-clip-text text-4xl font-extrabold tracking-tight text-transparent sm:text-5xl">
                Prove Bug Reports in a Sandbox
              </h1>
              <p className="mt-3 max-w-2xl text-lg text-slate-400">
                RepoDoctor extracts natural language claims using Gemini, synthesizes a pytest, and runs it against your code in an isolated Docker sandbox.
              </p>
            </div>
            <div className="flex gap-2">
              <a
                href={`${API_URL}/health`}
                target="_blank"
                rel="noreferrer"
                className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2 text-sm font-medium text-slate-400 transition hover:border-slate-700 hover:text-slate-200"
              >
                API Health Check
              </a>
            </div>
          </div>
        </header>

        {/* Demo Quick-Presets */}
        <section className="mb-8 rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-md">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">Demo Presets (Quick Fill)</h2>
          <div className="flex flex-wrap gap-2.5">
            {DEMO_PRESETS.map((preset) => {
              const isSelected = title === preset.title && body === preset.body;
              return (
                <button
                  key={preset.id}
                  onClick={() => handlePresetSelect(preset)}
                  type="button"
                  className={`rounded-lg px-4 py-2 text-xs font-medium border transition-all duration-200 ${
                    isSelected
                      ? "bg-indigo-600/10 border-indigo-500/80 text-indigo-300 shadow-md shadow-indigo-500/5"
                      : "bg-slate-900 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
        </section>

        {/* Core Layout Grid */}
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Left Column: Form Input */}
          <section className="lg:col-span-5">
            <div className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-6 shadow-xl backdrop-blur-lg">
              <h2 className="text-xl font-bold text-slate-100">Submit Bug Report</h2>
              <p className="mt-1 text-sm text-slate-400">Describe the function call and expectation.</p>

              <form className="mt-6 space-y-5" onSubmit={submit}>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400" htmlFor="title">
                    Issue Title
                  </label>
                  <input
                    className="mt-2 w-full rounded-lg border border-slate-800 bg-slate-950/80 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none ring-indigo-500/50 transition focus:border-indigo-500/80 focus:ring-4"
                    id="title"
                    placeholder="e.g. get_discount returns wrong value"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400" htmlFor="body">
                    Issue Details (Body)
                  </label>
                  <textarea
                    className="mt-2 min-h-[160px] w-full rounded-lg border border-slate-800 bg-slate-950/80 px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none ring-indigo-500/50 transition focus:border-indigo-500/80 focus:ring-4"
                    id="body"
                    placeholder="e.g. Calling get_discount(100, 20) returns 120 but it should return 80."
                    required
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    AI Service Provider
                  </label>
                  <div className="mt-2 grid grid-cols-3 gap-2">
                    {["gemini", "openai", "grok"].map((prov) => {
                      const isAvailable = providers[prov];
                      const isSelected = selectedProvider === prov;
                      return (
                        <button
                          key={prov}
                          type="button"
                          onClick={() => isAvailable && setSelectedProvider(prov)}
                          disabled={!isAvailable}
                          className={`rounded-lg py-2.5 text-xs font-semibold border flex flex-col items-center justify-center transition-all ${
                            isSelected
                              ? "bg-indigo-600/20 border-indigo-500 text-indigo-300 ring-2 ring-indigo-500/20"
                              : isAvailable
                              ? "bg-slate-950/80 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                              : "bg-slate-950/40 border-slate-900 text-slate-600 cursor-not-allowed opacity-50"
                          }`}
                        >
                          <span className="capitalize">{prov}</span>
                          <span className="text-[9px] mt-0.5 text-slate-500">
                            {isAvailable ? "Active" : "Locked"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <button
                  className="relative w-full overflow-hidden rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-700 py-3 font-semibold text-white transition-all hover:from-indigo-500 hover:to-indigo-600 hover:shadow-lg hover:shadow-indigo-500/20 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={loading}
                  type="submit"
                >
                  <span className="relative flex items-center justify-center gap-2">
                    {loading ? (
                      <>
                        <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Triage In Progress...
                      </>
                    ) : (
                      <>Analyze & Test Report</>
                    )}
                  </span>
                </button>
              </form>
            </div>

            {error && (
              <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-400 backdrop-blur-sm">
                <div className="flex gap-2">
                  <span className="font-semibold">Error:</span>
                  <span>{error}</span>
                </div>
              </div>
            )}
          </section>

          {/* Right Column: Triaging Output Panel */}
          <section className="lg:col-span-7">
            {result ? (
              <div className="space-y-6">
                {/* Result Summary Banner */}
                <div
                  className={`rounded-2xl border p-6 shadow-xl backdrop-blur-lg transition-all duration-300 ${
                    result.status === "reproduced"
                      ? "border-rose-500/20 bg-rose-950/10"
                      : result.status === "not_reproducible"
                      ? "border-emerald-500/20 bg-emerald-950/10"
                      : "border-amber-500/20 bg-amber-950/10"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex items-center gap-3">
                      {result.status === "reproduced" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-rose-500/30 bg-rose-500/10 px-4 py-1 text-sm font-semibold text-rose-400">
                          🔴 Reproduced (Bug Real)
                        </span>
                      )}
                      {result.status === "not_reproducible" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-4 py-1 text-sm font-semibold text-emerald-400">
                          🟢 Not Reproducible
                        </span>
                      )}
                      {result.status === "insufficient_info" && (
                        <span className="inline-flex h-9 items-center justify-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-1 text-sm font-semibold text-amber-400">
                          🟡 Insufficient Info
                        </span>
                      )}
                    </div>
                    <span className="rounded-full bg-slate-900 border border-slate-800 px-3 py-1 text-xs text-slate-400">
                      ⏱️ {result.duration_ms} ms
                    </span>
                  </div>

                  <p className="mt-4 text-base leading-relaxed text-slate-200">{result.explanation}</p>
                </div>

                {/* IDE / Output Tabbed Inspector */}
                <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl">
                  {/* macOS IDE header */}
                  <div className="flex items-center justify-between border-b border-slate-900 bg-slate-900/60 px-4 py-3">
                    <div className="flex gap-1.5">
                      <span className="h-3 w-3 rounded-full bg-rose-500/80" />
                      <span className="h-3 w-3 rounded-full bg-amber-500/80" />
                      <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => setActiveTab("extracted")}
                        className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                          activeTab === "extracted"
                            ? "bg-indigo-600/20 text-indigo-400"
                            : "text-slate-500 hover:text-slate-300"
                        }`}
                      >
                        Extracted Contract
                      </button>
                      {result.generated_test && (
                        <button
                          onClick={() => setActiveTab("test")}
                          className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                            activeTab === "test"
                              ? "bg-indigo-600/20 text-indigo-400"
                              : "text-slate-500 hover:text-slate-300"
                          }`}
                        >
                          test_generated.py
                        </button>
                      )}
                      {result.run_output && (
                        <button
                          onClick={() => setActiveTab("output")}
                          className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                            activeTab === "output"
                              ? "bg-indigo-600/20 text-indigo-400"
                              : "text-slate-500 hover:text-slate-300"
                          }`}
                        >
                          Sandbox Output
                        </button>
                      )}
                    </div>
                    <span className="text-[10px] uppercase tracking-widest text-slate-600">INSPECTOR</span>
                  </div>

                  {/* Tab Panels */}
                  <div className="p-5 font-mono text-sm leading-6">
                    {activeTab === "extracted" && (
                      <div className="space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-900 pb-2">
                          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Property</span>
                          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Value</span>
                        </div>
                        {result.extracted ? (
                          <div className="space-y-2 text-slate-300">
                            <div className="flex justify-between">
                              <span className="text-slate-500">Target Function:</span>
                              <span className="font-semibold text-indigo-300">{result.extracted.function ?? "null"}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Inputs:</span>
                              <span className="text-slate-100">{JSON.stringify(result.extracted.inputs)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Expected Value:</span>
                              <span className="text-emerald-400 font-semibold">{JSON.stringify(result.extracted.expected)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Observed Value:</span>
                              <span className="text-rose-400 font-semibold">{JSON.stringify(result.extracted.observed)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-500">Confidence Score:</span>
                              <span className="text-amber-400 font-semibold">{result.extracted.confidence ?? "null"}</span>
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-600 italic">No structured data was extracted.</p>
                        )}
                      </div>
                    )}

                    {activeTab === "test" && (
                      <pre className="overflow-x-auto text-indigo-300">
                        <code>{result.generated_test}</code>
                      </pre>
                    )}

                    {activeTab === "output" && (
                      <pre className="overflow-x-auto text-slate-300 whitespace-pre-wrap">
                        <code>{result.run_output}</code>
                      </pre>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-full min-h-[300px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/20 p-8 text-center text-slate-500">
                <svg
                  className="h-10 w-10 text-slate-600 animate-pulse"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"
                  />
                </svg>
                <h3 className="mt-4 font-bold text-slate-400">Sandbox Idle</h3>
                <p className="mt-2 max-w-sm text-sm text-slate-500">
                  Select a preset above or submit a custom report to see the sandbox verification live.
                </p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
