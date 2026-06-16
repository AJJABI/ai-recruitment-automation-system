/**
 * TestPage.tsx — Page test technique candidat
 *
 * Autonome — aucune dépendance externe au projet de base.
 * Compatible : wouter + lucide-react + tailwind (déjà installés).
 *
 * URL : /test?application_id=XXX&test_id=YYY
 *
 * Flow :
 *   1. Charge les questions depuis GET /tests/{test_id}
 *   2. Intro → candidat entre son nom → plein écran
 *   3. Test avec anti-triche (tab switch, copy, fullscreen, idle)
 *   4. Soumission → POST /applications/{id}/evaluate-test
 *   5. Page "Test soumis" (pas de score — résultats dans dashboard Manager)
 */

import {
    useState,
    useEffect,
    useReducer,
    useRef,
    useCallback,
    ReactNode,
} from "react";
import {
    ShieldAlert,
    ShieldCheck,
    Clock,
    Flag,
    Lock,
    ChevronLeft,
    ChevronRight,
    Send,
    AlertTriangle,
    FileText,
    Loader2,
    AlertCircle,
    CheckCircle2,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

interface Question {
    id: number;
    type: "MCQ" | "Open";
    text: string;
    options?: string[];
    timeLimit: number;
    skill?: string;
}

interface Violation {
    type: "tab_switch" | "copy_paste" | "print_screen" | "fullscreen_exit" | "idle";
    timestamp: number;
}

interface TestState {
    status: "loading" | "error" | "intro" | "in_progress" | "submitting" | "done" | "already_submitted";
    questions: Question[];
    currentIndex: number;
    answers: Record<number, string>;
    locked: Record<number, boolean>;
    flagged: Set<number>;
    violations: Violation[];
    candidateName: string;
    globalTime: number;
    perQuestionTime: number;
    timeSpent: Record<number, number>;
    startTimes: Record<number, number>;
    errorMsg: string;
    testId: string;
    applicationId: string;
    candidateEmail: string;
    jobTitle: string;
}

type Action =
    | { type: "SET_LOADING" }
    | { type: "SET_ERROR"; msg: string }
    | { type: "SET_QUESTIONS"; questions: Question[]; testId: string; applicationId: string }
    | { type: "START"; candidateName: string }
    | { type: "SET_ANSWER"; id: number; value: string }
    | { type: "NEXT" }
    | { type: "PREV" }
    | { type: "GO_TO"; index: number }
    | { type: "TOGGLE_FLAG"; id: number }
    | { type: "LOCK"; id: number }
    | { type: "LOG_VIOLATION"; violationType: Violation["type"] }
    | { type: "TICK_GLOBAL" }
    | { type: "TICK_QUESTION" }
    | { type: "SUBMIT" }
    | { type: "SET_DONE" }
    | { type: "SET_ALREADY_SUBMITTED" }
    | { type: "SET_META"; candidateEmail: string; jobTitle: string };

function pad(n: number) {
    return String(n).padStart(2, "0");
}
function fmt(s: number) {
    return `${pad(Math.floor(s / 60))}:${pad(s % 60)}`;
}

const GLOBAL_TIME = 3600; // 60 min

function getInitialState(): TestState {
    return {
        status: "loading",
        questions: [],
        currentIndex: 0,
        answers: {},
        locked: {},
        flagged: new Set(),
        violations: [],
        candidateName: "",
        globalTime: GLOBAL_TIME,
        perQuestionTime: 0,
        timeSpent: {},
        startTimes: {},
        errorMsg: "",
        testId: "",
        applicationId: "",
        candidateEmail: "",
        jobTitle: "",
    };
}

function reducer(state: TestState, action: Action): TestState {
    const qs = state.questions;
    const cur = qs[state.currentIndex];

    switch (action.type) {
        case "SET_LOADING": return { ...state, status: "loading" };
        case "SET_ERROR": return { ...state, status: "error", errorMsg: action.msg };

        case "SET_QUESTIONS":
            return {
                ...state,
                status: "intro",
                questions: action.questions,
                testId: action.testId,
                applicationId: action.applicationId,
                globalTime: GLOBAL_TIME,
                perQuestionTime: action.questions[0]?.timeLimit ?? 120,
            };

        case "START":
            return {
                ...state,
                status: "in_progress",
                candidateName: action.candidateName,
                startTimes: qs[0] ? { [qs[0].id]: Date.now() } : {},
                perQuestionTime: qs[0]?.timeLimit ?? 120,
            };

        case "SET_ANSWER":
            return { ...state, answers: { ...state.answers, [action.id]: action.value } };

        case "NEXT": {
            if (state.currentIndex >= qs.length - 1) return state;
            const ni = state.currentIndex + 1;
            const spent = cur ? Date.now() - (state.startTimes[cur.id] ?? Date.now()) : 0;
            return {
                ...state,
                currentIndex: ni,
                timeSpent: cur ? { ...state.timeSpent, [cur.id]: (state.timeSpent[cur.id] ?? 0) + spent } : state.timeSpent,
                startTimes: { ...state.startTimes, [qs[ni].id]: Date.now() },
                perQuestionTime: state.locked[qs[ni].id] ? 0 : qs[ni].timeLimit,
            };
        }

        case "PREV": {
            if (state.currentIndex <= 0) return state;
            const pi = state.currentIndex - 1;
            const spent = cur ? Date.now() - (state.startTimes[cur.id] ?? Date.now()) : 0;
            return {
                ...state,
                currentIndex: pi,
                timeSpent: cur ? { ...state.timeSpent, [cur.id]: (state.timeSpent[cur.id] ?? 0) + spent } : state.timeSpent,
                startTimes: { ...state.startTimes, [qs[pi].id]: Date.now() },
                perQuestionTime: state.locked[qs[pi].id] ? 0 : qs[pi].timeLimit,
            };
        }

        case "GO_TO": {
            if (action.index === state.currentIndex || action.index < 0 || action.index >= qs.length) return state;
            const spent = cur ? Date.now() - (state.startTimes[cur.id] ?? Date.now()) : 0;
            return {
                ...state,
                currentIndex: action.index,
                timeSpent: cur ? { ...state.timeSpent, [cur.id]: (state.timeSpent[cur.id] ?? 0) + spent } : state.timeSpent,
                startTimes: { ...state.startTimes, [qs[action.index].id]: Date.now() },
                perQuestionTime: state.locked[qs[action.index].id] ? 0 : qs[action.index].timeLimit,
            };
        }

        case "TOGGLE_FLAG": {
            const f = new Set(state.flagged);
            f.has(action.id) ? f.delete(action.id) : f.add(action.id);
            return { ...state, flagged: f };
        }

        case "LOCK":
            return { ...state, locked: { ...state.locked, [action.id]: true } };

        case "LOG_VIOLATION":
            return { ...state, violations: [...state.violations, { type: action.violationType, timestamp: Date.now() }] };

        case "TICK_GLOBAL":
            return state.globalTime <= 0 ? state : { ...state, globalTime: state.globalTime - 1 };

        case "TICK_QUESTION":
            return state.perQuestionTime <= 0 ? state : { ...state, perQuestionTime: state.perQuestionTime - 1 };

        case "SUBMIT":
            return { ...state, status: "submitting" };

        case "SET_DONE":
            return { ...state, status: "done" };

        case "SET_ALREADY_SUBMITTED":
            return { ...state, status: "already_submitted" };

        case "SET_META":
            return { ...state, candidateEmail: action.candidateEmail, jobTitle: action.jobTitle };

        default:
            return state;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const N8N_BASE = "http://127.0.0.1:5678";

export default function TestPage() {
    const [state, dispatch] = useReducer(reducer, getInitialState());
    const [showSubmitModal, setShowSubmitModal] = useState(false);
    const [showViolationModal, setShowViolationModal] = useState(false);
    const [violationMsg, setViolationMsg] = useState("");
    const [blurred, setBlurred] = useState(false);
    const [n8nError, setN8nError] = useState(false);
    const [nameInput, setNameInput] = useState("");
    const lastActivity = useRef(Date.now());

    // ── Reset lastActivity quand le test démarre vraiment ──────────────────────
    useEffect(() => {
        if (state.status === "in_progress") {
            lastActivity.current = Date.now();
        }
    }, [state.status]);

    const params = new URLSearchParams(window.location.search);
    const applicationId = params.get("application_id") ?? "";
    const testId = params.get("test_id") ?? "";

    // ── Charger questions ───────────────────────────────────────────────────────
    useEffect(() => {
        if (!applicationId || !testId) {
            dispatch({ type: "SET_ERROR", msg: "Invalid link — missing parameters application_id and test_id." });
            return;
        }
        fetch(`${BASE}/tests/${testId}`)
            .then(async (r) => {
                if (!r.ok) throw new Error("Test not found or link expired.");
                return r.json();
            })
            .then((data) => {
                const qs: Question[] = (data.questions ?? []).map((q: any, idx: number) => {
                    // Normalise le type — MCQ si options présentes OU type mcq/multiple_choice/qcm
                    const rawType = (q.type ?? "open").toLowerCase();
                    const isMCQ = rawType === "mcq" || rawType === "multiple_choice" || rawType === "qcm"
                        || (rawType !== "open" && rawType !== "problem" && rawType !== "scenario" && rawType !== "open_ended" && q.options && q.options.length > 0);
                    const type: "MCQ" | "Open" = isMCQ ? "MCQ" : "Open";

                    // Normalise les options
                    let options: string[] | undefined;
                    if (isMCQ && q.options) {
                        options = q.options.map((o: any) => {
                            if (typeof o === "string") return o;
                            return o.text ?? o.label ?? o.value ?? String(o);
                        });
                    }

                    // Normalise le texte de la question
                    const text = q.question ?? q.text ?? q.prompt ?? q.statement ?? `Question ${idx + 1}`;

                    return {
                        id: q.id ?? idx + 1,
                        type,
                        text,
                        options,
                        timeLimit: type === "MCQ" ? 180 : 480,  // MCQ 3min, Open 8min
                        skill: q.skill ?? "",
                        difficulty: q.difficulty ?? "",
                    };
                });
                dispatch({ type: "SET_QUESTIONS", questions: qs, testId, applicationId });

                // Récupérer email candidat + job title pour les emails n8n
                fetch(`${BASE}/applications/${applicationId}`)
                    .then(r => r.ok ? r.json() : null)
                    .then(data => {
                        if (data) {
                            dispatch({
                                type: "SET_META",
                                candidateEmail: data.candidate_email ?? data.email ?? "",
                                jobTitle: data.job_title ?? data.job?.title ?? "",
                            });
                        }
                    })
                    .catch(() => {}); // non-bloquant
            })
            .catch((e) => dispatch({ type: "SET_ERROR", msg: e.message }));
    }, [applicationId, testId]);

    // ── Timers ──────────────────────────────────────────────────────────────────
    useEffect(() => {
        if (state.status !== "in_progress") return;
        const g = setInterval(() => dispatch({ type: "TICK_GLOBAL" }), 1000);
        const q = setInterval(() => dispatch({ type: "TICK_QUESTION" }), 1000);
        return () => { clearInterval(g); clearInterval(q); };
    }, [state.status]);

    // Timer global → submit
    useEffect(() => {
        if (state.status === "in_progress" && state.globalTime <= 0) submitTest();
    }, [state.globalTime, state.status]);

    // Timer question → lock + passage auto immédiat
    useEffect(() => {
        if (state.status !== "in_progress" || state.perQuestionTime !== 0) return;
        const cur = state.questions[state.currentIndex];
        if (!cur || state.locked[cur.id]) return;
        // Verrouiller la question (score 0 implicite car pas de réponse)
        dispatch({ type: "LOCK", id: cur.id });
        // Passage auto à la question suivante immédiatement
        const nextIndex = state.currentIndex + 1;
        if (nextIndex < state.questions.length) {
            dispatch({ type: "NEXT" });
        } else {
            // Dernière question → soumettre automatiquement
            submitTest();
        }
    }, [state.perQuestionTime, state.status]);

    // ── Anti-triche ─────────────────────────────────────────────────────────────
    const logViolation = useCallback((type: Violation["type"], msg: string) => {
        dispatch({ type: "LOG_VIOLATION", violationType: type });
        const totalViolations = state.violations.length + 1; // +1 car dispatch pas encore appliqué

        // 3 violations → soumission automatique avec flag
        if (totalViolations >= 3) {
            setViolationMsg("3 violations detected. The test will be submitted automatically.");
            setShowViolationModal(true);
            setTimeout(() => submitTest(), 3000);
            return;
        }

        // Score 0 sur la question actuelle + passage auto à la suivante
        const cur = state.questions[state.currentIndex];
        if (cur && !state.locked[cur.id]) {
            dispatch({ type: "LOCK", id: cur.id });
            // Fermer le modal après 2s et passer à la suivante
            setViolationMsg(msg);
            setShowViolationModal(true);
            setTimeout(() => {
                setShowViolationModal(false);
                const nextIndex = state.currentIndex + 1;
                if (nextIndex < state.questions.length) {
                    dispatch({ type: "NEXT" });
                }
            }, 2000);
            return;
        }

        if (type !== "copy_paste") {
            setViolationMsg(msg);
            setShowViolationModal(true);
        }
    }, [state.violations, state.questions, state.currentIndex, state.locked]);

    useEffect(() => {
        if (state.status !== "in_progress") return;
        const blur = () => logViolation("tab_switch", "Focus loss detected. This incident has been recorded.");
        const fs = () => { if (!document.fullscreenElement) logViolation("fullscreen_exit", "Fullscreen exited."); };
        const cp = (e: ClipboardEvent) => { e.preventDefault(); logViolation("copy_paste", "Copy-paste disabled."); };
        const ctx = (e: MouseEvent) => e.preventDefault();
        const key = (e: KeyboardEvent) => {
            // Bloquer Escape — empêche de quitter le plein écran via clavier
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); return; }
            // Bloquer touche Windows / Meta
            if (e.key === "Meta" || e.key === "OS") { e.preventDefault(); return; }
            // Bloquer Alt+F4, Alt+Tab
            if (e.altKey && (e.key === "F4" || e.key === "Tab")) { e.preventDefault(); return; }
            // Bloquer F11 (toggle fullscreen)
            if (e.key === "F11") { e.preventDefault(); return; }
            if (e.key === "PrintScreen") { setBlurred(true); setTimeout(() => setBlurred(false), 2000); logViolation("print_screen", "Screenshot detected."); }
            if ((e.ctrlKey && e.shiftKey && ["I", "J", "C"].includes(e.key.toUpperCase())) || e.key === "F12") e.preventDefault();
        };
        const move = () => { lastActivity.current = Date.now(); };

        window.addEventListener("blur", blur);
        document.addEventListener("fullscreenchange", fs);
        document.addEventListener("copy", cp as any);
        document.addEventListener("cut", cp as any);
        document.addEventListener("paste", cp as any);
        document.addEventListener("contextmenu", ctx);
        window.addEventListener("keydown", key);
        window.addEventListener("mousemove", move);
        window.addEventListener("click", move);

        return () => {
            window.removeEventListener("blur", blur);
            document.removeEventListener("fullscreenchange", fs);
            document.removeEventListener("copy", cp as any);
            document.removeEventListener("cut", cp as any);
            document.removeEventListener("paste", cp as any);
            document.removeEventListener("contextmenu", ctx);
            window.removeEventListener("keydown", key);
            window.removeEventListener("mousemove", move);
            window.removeEventListener("click", move);
        };
    }, [state.status, logViolation]);

    // ── Submit ──────────────────────────────────────────────────────────────────
    const submitTest = useCallback(() => {
        if (state.status === "submitting" || state.status === "done") return;
        dispatch({ type: "SUBMIT" });
        const forcedByViolation = state.violations.length >= 3;

        // ✅ Fire-and-forget — on n'attend PAS que n8n termine
        // Le frontend passe immédiatement à l'écran "Test soumis"
        fetch(`${N8N_BASE}/webhook/corriger-test`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                test_id:        testId,
                answers:        state.questions.map(q => ({
                    question_id: q.id,
                    answer: q.type === "MCQ" && state.answers[q.id] !== undefined
                        ? (q.options?.[parseInt(state.answers[q.id])] ?? "")
                        : (state.answers[q.id] ?? ""),
                })),
                application_id:  Number(applicationId),
                violations:      state.violations,
                violation_flag:  forcedByViolation ? "VIOLATION_3" : null,
                forced_submit:   forcedByViolation,
                candidate_email: state.candidateEmail,
                candidate_name:  state.candidateName,
                job_title:       state.jobTitle,
            }),
        }).catch(() => {
            setN8nError(true);
        });

        // Passage immédiat à l'écran de confirmation, sans attendre n8n
        dispatch({ type: "SET_DONE" });
    }, [state, applicationId, testId]);

    const handleStart = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!nameInput.trim()) return;

        // ── Appel open-test ici — démarre le timer côté backend ──────────────
        try {
            const res = await fetch(`${BASE}/applications/${applicationId}/open-test`, { method: "POST" });
            if (res.status === 403 || res.status === 400) {
                const data = await res.json().catch(() => ({}));
                if (
                    data?.detail?.error === "TEST_ALREADY_SUBMITTED" ||
                    res.status === 400 && !data?.already_opened
                ) {
                    dispatch({ type: "SET_ALREADY_SUBMITTED" });
                    return;
                }
            }
            // already_opened=true → ok, test ouvert mais pas terminé → on continue
        } catch { }

        try { await document.documentElement.requestFullscreen(); } catch { }
        dispatch({ type: "START", candidateName: nameInput.trim() });
    };

    // ─── RENDER ────────────────────────────────────────────────────────────────

    const qs = state.questions;
    const cur = qs[state.currentIndex];
    const answered = Object.keys(state.answers).length;

    if (state.status === "already_submitted") return (
        <Centered>
            <div className="w-16 h-16 rounded-full bg-amber-50 border-2 border-amber-100 flex items-center justify-center mb-4">
                <Lock className="w-8 h-8 text-amber-500" />
            </div>
            <h2 className="text-xl font-bold text-slate-800 mb-2">Test Already Submitted</h2>
            <p className="text-slate-500 text-sm text-center leading-relaxed">
                You have already submitted this test. Your answers have been recorded and are being evaluated.
            </p>
            <p className="text-xs text-slate-400 mt-4">You may close this window.</p>
        </Centered>
    );

    if (state.status === "loading") return <Centered><Loader2 className="w-8 h-8 animate-spin text-purple-600" /><p className="text-slate-500 text-sm mt-3">Loading…</p></Centered>;

    if (state.status === "error") return (
        <Centered>
            <div className="w-16 h-16 rounded-full bg-red-50 border-2 border-red-100 flex items-center justify-center mb-4">
                <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-bold text-slate-800 mb-2">Invalid Link</h2>
            <p className="text-slate-500 text-sm text-center">{state.errorMsg}</p>
        </Centered>
    );

    if (state.status === "intro") return (
        <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4 font-sans">
            <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl border overflow-hidden">
                <div className="h-1 bg-gradient-to-r from-purple-600 via-purple-400 to-purple-200" />
                <div className="p-8 md:p-12">
                    <div className="flex items-start justify-between mb-8">
                        <div>
                            <h1 className="text-3xl font-bold text-slate-900 mb-1">Technical Assessment</h1>
                            <p className="text-slate-500 text-sm flex items-center gap-1.5">
                                <ShieldCheck className="w-4 h-4 text-purple-600" /> Secure examination environment
                            </p>
                        </div>
                        <div className="w-12 h-12 bg-purple-50 rounded-xl border border-purple-100 flex items-center justify-center">
                            <span className="font-mono font-bold text-purple-600 text-sm">TX</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mb-8">
                        {[
                            { icon: Clock, label: "Duration", value: "60 min" },
                            { icon: FileText, label: "Questions", value: `${qs.length}` },
                        ].map(({ icon: Icon, label, value }) => (
                            <div key={label} className="bg-slate-50 rounded-xl p-4 border">
                                <div className="flex items-center gap-2 text-slate-500 mb-1">
                                    <Icon className="w-4 h-4" />
                                    <span className="text-xs font-semibold uppercase tracking-wider">{label}</span>
                                </div>
                                <div className="text-xl font-bold font-mono text-slate-900">{value}</div>
                            </div>
                        ))}
                    </div>

                    <div className="mb-8 space-y-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
                            <ShieldAlert className="w-4 h-4 text-red-500" /> Evaluation rules
                        </h3>
                        <ul className="space-y-2.5 text-sm">
                            {[
                                ["red", "Tab switches and loss of focus are detected and recorded."],
                                ["red", "Full screen mode is mandatory. Any exit generates a violation."],
                                ["red", "3 violations trigger automatic test submission."],
                                ["purple", "Copy-paste is disabled during the test."],
                                ["purple", "Each question has its own timer — MCQ : 3 min, Open Question : 8 min."],
                                ["purple", "Questions lock automatically upon expiration. No backward navigation possible."],
                                ["purple", "The test auto-submits when the global timer ends (60 min)."],
                            ].map(([color, text], i) => (
                                <li key={i} className="flex items-start gap-3">
                                    <div className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${color === "red" ? "bg-red-500" : "bg-purple-500"}`} />
                                    <span className="text-slate-700">{text}</span>
                                </li>
                            ))}
                        </ul>
                    </div>

                    <form onSubmit={handleStart} className="space-y-4">
                        <div>
                            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                                Full name
                            </label>
                            <input
                                value={nameInput}
                                onChange={e => setNameInput(e.target.value)}
                                className="w-full h-11 px-4 border rounded-xl bg-white text-slate-900 font-medium focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                                autoComplete="off"
                                required
                            />
                        </div>
                        <button
                            type="submit"
                            className="w-full h-12 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-xl transition-colors"
                        >
                            Enter the secure environment
                        </button>
                    </form>
                </div>
            </div>
        </div>
    );

    if (state.status === "submitting") return (
        <Centered>
            <Loader2 className="w-8 h-8 animate-spin text-purple-600" />
            <p className="text-slate-500 text-sm mt-3">Submitting…</p>
        </Centered>
    );

    if (state.status === "done") return (
        <Centered>
            <div className="w-20 h-20 rounded-full bg-green-50 border-2 border-green-100 flex items-center justify-center mb-5">
                <CheckCircle2 className="w-10 h-10 text-green-500" />
            </div>
            <h2 className="text-2xl font-bold text-slate-900 mb-2">Test soumis !</h2>
            <p className="text-slate-500 text-sm text-center leading-relaxed max-w-xs">
                Your answers have been sent to our team. You will receive an email with the next steps in the recruitment process.
            </p>
            {n8nError && (
                <div className="mt-5 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-700 max-w-xs">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>A network error occurred while sending your answers. Please contact the recruiter to confirm your submission.</span>
                </div>
            )}
            <p className="text-xs text-slate-400 mt-6">You may close this window.</p>
        </Centered>
    );

    // ── TEST ──────────────────────────────────────────────────────────────────
    if (!cur) return null;
    const isLocked = !!state.locked[cur.id];
    const isFlagged = state.flagged.has(cur.id);
    const globalCritical = state.globalTime < 300;
    const questionCritical = state.perQuestionTime < 15;

    return (
        <div className={`min-h-screen bg-slate-50 flex flex-col font-sans transition-all ${blurred ? "blur-xl" : ""}`}>

            {/* ── Header ── */}
            <header className="h-16 border-b bg-white shadow-sm flex items-center justify-between px-6 shrink-0 z-10">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-purple-50 rounded-lg border border-purple-100 flex items-center justify-center">
                        <span className="font-mono font-bold text-purple-600 text-xs">TX</span>
                    </div>
                    <span className="text-sm font-medium text-slate-700">{state.candidateName}</span>
                </div>

                <div className="flex-1 max-w-md mx-8 hidden md:block">
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                        <span>Progress</span>
                        <span>{answered}/{qs.length} answered</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full bg-purple-500 rounded-full transition-all" style={{ width: `${(answered / qs.length) * 100}%` }} />
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <div className={`flex items-center gap-2 font-mono text-lg font-bold px-3 py-1 rounded-lg border ${globalCritical ? "text-red-600 border-red-200 bg-red-50" : "text-slate-800 border-slate-200"}`}>
                        <Clock className="w-4 h-4 opacity-70" />
                        {fmt(state.globalTime)}
                    </div>
                    <button onClick={() => setShowSubmitModal(true)} className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold rounded-lg transition-colors">
                        Submit
                    </button>
                </div>
            </header>

            <div className="flex flex-1 overflow-hidden">
                {/* ── Sidebar ── */}
                <aside className="w-64 border-r bg-white flex-col shrink-0 overflow-y-auto hidden md:flex">
                    <div className="p-4 border-b">
                        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">Navigation</p>
                        <div className="grid grid-cols-5 gap-2">
                            {qs.map((q, i) => {
                                const isCur = i === state.currentIndex;
                                const isAns = !!state.answers[q.id];
                                const isLk = !!state.locked[q.id];
                                const isFlg = state.flagged.has(q.id);
                                return (
                                    <div
                                        key={q.id}
                                        className={`relative w-10 h-10 rounded-lg flex items-center justify-center text-sm font-medium border
                      ${isCur ? "bg-purple-100 text-purple-700 border-purple-400" : ""}
                      ${isAns && !isCur ? "bg-green-50 text-green-700 border-green-300" : ""}
                      ${!isAns && !isCur ? "bg-white text-slate-500 border-slate-200" : ""}
                      ${isLk ? "opacity-40" : ""}
                      cursor-default select-none
                    `}
                                    >
                                        {isLk ? <Lock className="w-3 h-3" /> : i + 1}
                                        {isFlg && <div className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-amber-400 rounded-full" />}
                                        {isAns && !isCur && !isLk && <div className="absolute -bottom-1 -right-1 w-2.5 h-2.5 bg-green-500 rounded-full" />}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                    <div className="p-4 space-y-2 text-xs text-slate-400">
                        {[["bg-purple-100 border border-purple-400", "Current question"], ["bg-green-50 border border-green-300", "Answered"], ["bg-amber-400", "Flagged"], ["bg-slate-200", "Locked"]].map(([cls, label]) => (
                            <div key={label} className="flex items-center gap-2">
                                <div className={`w-3 h-3 rounded ${cls}`} />
                                {label}
                            </div>
                        ))}
                    </div>
                    <div className="mt-auto p-4 border-t text-xs text-slate-400">
                        <p>{qs.length - answered} question(s) remaining</p>
                        <p>{state.flagged.size} flagged</p>
                    </div>
                </aside>

                {/* ── Main ── */}
                <main className="flex-1 flex flex-col overflow-hidden bg-slate-50">
                    <div className="flex-1 overflow-y-auto p-6 md:p-10">
                        <div className="max-w-3xl mx-auto">

                            {/* Question header */}
                            <div className="flex items-center gap-3 mb-6 flex-wrap">
                                <span className="text-3xl font-bold text-slate-900 font-mono">{state.currentIndex + 1}.</span>
                                <span className="px-2.5 py-1 rounded-lg bg-slate-100 border text-xs font-semibold uppercase tracking-wider text-slate-500">
                                    {cur.type === "MCQ" ? "Multiple Choice" : "Open Question"}
                                </span>

                                {isLocked && <span className="px-2.5 py-1 rounded-lg bg-red-50 border border-red-100 text-xs font-semibold text-red-600 flex items-center gap-1"><Lock className="w-3 h-3" /> Locked</span>}
                                <div className={`ml-auto flex items-center gap-2 font-mono text-base font-bold px-3 py-1.5 rounded-lg border ${questionCritical ? "text-red-600 border-red-200 bg-red-50" : "text-purple-600 border-purple-100 bg-purple-50"}`}>
                                    <Clock className="w-4 h-4 opacity-70" />{fmt(state.perQuestionTime)}
                                </div>
                            </div>

                            {/* Question text */}
                            <p className="text-lg md:text-xl text-slate-800 font-medium leading-relaxed mb-8">{cur.text}</p>

                            {/* MCQ */}
                            {cur.type === "MCQ" && cur.options && (
                                <div className="space-y-3">
                                    {cur.options.map((opt, i) => {
                                        const sel = state.answers[cur.id] === i.toString();
                                        return (
                                            <button
                                                key={i}
                                                disabled={isLocked}
                                                onClick={() => dispatch({ type: "SET_ANSWER", id: cur.id, value: i.toString() })}
                                                className={`w-full text-left p-4 rounded-xl border transition-all flex items-center gap-4
                          ${sel ? "bg-purple-50 border-purple-400 ring-1 ring-purple-300" : "bg-white border-slate-200 hover:border-purple-300"}
                          ${isLocked ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}
                        `}
                                            >
                                                <div className={`w-8 h-8 rounded-full border flex items-center justify-center font-mono text-sm font-bold shrink-0 transition-colors ${sel ? "bg-purple-600 border-purple-600 text-white" : "border-slate-300 text-slate-500"}`}>
                                                    {String.fromCharCode(65 + i)}
                                                </div>
                                                <span className="text-slate-800">{opt}</span>
                                            </button>
                                        );
                                    })}
                                </div>
                            )}

                            {/* Open */}
                            {cur.type === "Open" && (
                                <div className="space-y-2">
                                    <textarea
                                        disabled={isLocked}
                                        value={state.answers[cur.id] ?? ""}
                                        onChange={e => dispatch({ type: "SET_ANSWER", id: cur.id, value: e.target.value })}
                                        placeholder="Write your answer here..."
                                        rows={10}
                                        className="w-full p-4 border border-slate-200 rounded-xl bg-white text-slate-800 leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                                    />
                                    <div className="flex justify-between text-xs text-slate-400 px-1">
                                        <span>Auto-saved</span>
                                        <span>{(state.answers[cur.id] ?? "").length} characters</span>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Nav bottom ── */}
                    <div className="h-20 border-t bg-white shadow-sm flex items-center justify-end px-6 shrink-0">

                        {state.currentIndex < qs.length - 1 ? (
                            <button
                                onClick={() => dispatch({ type: "NEXT" })}
                                disabled={isLocked}
                                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Next <ChevronRight className="w-4 h-4" />
                            </button>
                        ) : (
                            <button
                                onClick={() => setShowSubmitModal(true)}
                                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded-xl transition-colors"
                            >
                                Finish <Send className="w-4 h-4" />
                            </button>
                        )}
                    </div>
                </main>
            </div>

            {/* ── Modal soumission ── */}
            {showSubmitModal && (
                <Modal onClose={() => setShowSubmitModal(false)}>
                    <h2 className="text-xl font-bold text-slate-900 mb-2">Submit l'évaluation ?</h2>
                    <div className="space-y-3 text-sm text-slate-600 mb-6">
                        <p>You answered <strong>{answered}</strong> question(s) out of <strong>{qs.length}</strong>.</p>
                        {qs.length - answered > 0 && <p className="text-amber-600 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />{qs.length - answered} unanswered question(s).</p>}
                        {state.flagged.size > 0 && <p className="text-amber-600 flex items-center gap-2"><Flag className="w-4 h-4" />{state.flagged.size} question(s) flagged.</p>}
                        <p className="text-xs text-slate-400">Once submitted, you cannot modify your answers.</p>
                    </div>
                    <div className="flex gap-3">
                        <button onClick={() => setShowSubmitModal(false)} className="flex-1 px-4 py-2.5 border border-slate-200 rounded-xl text-sm font-medium text-slate-600 hover:bg-slate-50">
                            Back to Test
                        </button>
                        <button onClick={() => { setShowSubmitModal(false); submitTest(); }} className="flex-1 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 text-white text-sm font-semibold rounded-xl transition-colors">
                            Confirm
                        </button>
                    </div>
                </Modal>
            )}

            {/* ── Modal violation ── */}
            {showViolationModal && (
                <Modal onClose={() => { }}>
                    <div className="flex items-center gap-3 mb-4">
                        <ShieldAlert className="w-6 h-6 text-red-500 shrink-0" />
                        <h2 className="text-xl font-bold text-red-600">Violation Detected</h2>
                    </div>
                    <p className="text-slate-700 text-sm mb-3">{violationMsg}</p>
                    <div className="bg-slate-50 border rounded-lg p-3 text-sm mb-3">
                        Violations enregistrées : <strong className="text-red-600">{state.violations.length}</strong> / 3
                    </div>
                    {state.violations.length < 3 && (
                        <p className="text-xs text-amber-600 mb-4 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            This question has been locked (score 0). Moving to next in 2s.
                        </p>
                    )}
                    {state.violations.length >= 3 && (
                        <p className="text-xs text-red-600 mb-4 font-semibold">
                            ⚠️ 3 violations reached — auto-submitting in 3 seconds.
                        </p>
                    )}
                </Modal>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function Centered({ children }: { children: ReactNode }) {
    return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center p-4 font-sans">
            <div className="bg-white rounded-2xl shadow-xl border p-10 flex flex-col items-center max-w-sm w-full">
                {children}
            </div>
        </div>
    );
}

function Modal({ children, onClose }: { children: ReactNode; onClose: () => void }) {
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl border p-8 w-full max-w-md">
                {children}
            </div>
        </div>
    );
}