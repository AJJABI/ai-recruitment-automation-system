import { useState, useEffect, useCallback } from "react";
import { useSearch } from "wouter";
import { format, startOfMonth, endOfMonth, eachDayOfInterval, getDay, isToday, parseISO } from "date-fns";
import { ChevronLeft, ChevronRight, Clock, CheckCircle2, Mail, X, AlertCircle } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

type ToastData = { id: number; title: string; variant?: "default" | "destructive" };
let _toastSetter: React.Dispatch<React.SetStateAction<ToastData[]>> | null = null;
let _toastId = 0;

function useToast() {
  const toast = useCallback(({ title, variant }: { title: string; variant?: "default" | "destructive" }) => {
    if (!_toastSetter) return;
    const id = ++_toastId;
    _toastSetter((prev) => [...prev, { id, title, variant }]);
    setTimeout(() => _toastSetter?.((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);
  return { toast };
}

function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([]);
  useEffect(() => { _toastSetter = setToasts; return () => { _toastSetter = null; }; }, []);
  return (
    <>
      {children}
      <div style={{ position: "fixed", bottom: 24, right: 24, zIndex: 9999, display: "flex", flexDirection: "column", gap: 8 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "12px 16px", borderRadius: 8, minWidth: 260, maxWidth: 360,
            background: t.variant === "destructive" ? "#fef2f2" : "#f0fdf4",
            border: `1px solid ${t.variant === "destructive" ? "#fca5a5" : "#86efac"}`,
            color: t.variant === "destructive" ? "#dc2626" : "#16a34a",
            fontSize: 13, fontWeight: 600, boxShadow: "0 4px 16px rgba(0,0,0,0.1)",
          }}>
            <span style={{ flex: 1 }}>{t.title}</span>
            <button onClick={() => _toastSetter?.((p) => p.filter((x) => x.id !== t.id))}
              style={{ background: "none", border: "none", cursor: "pointer", padding: 2, color: "inherit", opacity: 0.7 }}>
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const N8N_BASE = import.meta.env.VITE_N8N_BASE_URL ?? "http://localhost:5678";
const DAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

type Job = { id: number; title: string; location?: string; };
type Slot = { id: number; date: string; startTime: string; endTime: string; status: "available" | "booked"; };

function mapSlot(raw: any): Slot {
  return { id: raw.id, date: raw.date, startTime: raw.start_time, endTime: raw.end_time, status: raw.status };
}

async function fetchJob(jobId: number): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error("job_not_found");
  const data = await res.json();
  return { id: data.id, title: data.title, location: data.location };
}

async function fetchAvailableSlots(month: string, jobId: number): Promise<Slot[]> {
  const res = await fetch(`${API_BASE}/interviews/public/slots?month=${month}&job_id=${jobId}`);
  if (!res.ok) throw new Error("fetch_failed");
  const data: any[] = await res.json();

  // ── FIX : exclure les slots dont la date est dans le passé ──────────────────
  const todayStr = format(new Date(), "yyyy-MM-dd");
  return data
    .map(mapSlot)
    .filter((s) => s.date >= todayStr && s.status === "available");
}

async function bookSlotAPI(slotId: number, candidateName: string, candidateEmail: string): Promise<any> {
  const search = new URLSearchParams(window.location.search);
  const token = search.get("token") ?? "";
  const res = await fetch(`${API_BASE}/interviews/book`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, slot_id: slotId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? "book_failed");
  }
  return res.json();
}

function CandidateBookingInner() {
  const { toast } = useToast();
  const search = useSearch();
  const params = new URLSearchParams(search);
  const rawJobId = params.get("job_id");
  const jobId = rawJobId ? parseInt(rawJobId, 10) : null;

  const [job, setJob]           = useState<Job | null>(null);
  const [jobError, setJobError] = useState(false);
  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [confirmOpen, setConfirmOpen]   = useState(false);
  const [booked, setBooked]             = useState(false);
  const [bookedSlot, setBookedSlot]     = useState<Slot | null>(null);
  const [candidate, setCandidate]       = useState({ name: "", email: "" });
  const [slots, setSlots]       = useState<Slot[]>([]);
  const [isLoading, setLoading] = useState(false);
  const [isPending, setPending] = useState(false);
  const [tokenStatus, setTokenStatus] = useState<"checking" | "valid" | "expired" | "used" | "invalid">("checking");

  const monthKey = format(currentMonth, "yyyy-MM");

  useEffect(() => {
    if (!jobId || isNaN(jobId)) { setJobError(true); return; }
    fetchJob(jobId).then(setJob).catch(() => setJobError(true));
  }, [jobId]);

  useEffect(() => {
    if (!jobId || isNaN(jobId)) return;
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) { setTokenStatus("invalid"); return; }
    fetch(`${API_BASE}/interviews/slots/available/${jobId}?token=${token}`)
      .then(async (res) => {
        if (res.ok) { setTokenStatus("valid"); return; }
        const err = await res.json().catch(() => ({}));
        if (err?.detail === "Lien déjà utilisé") setTokenStatus("used");
        else if (err?.detail === "Lien expiré")  setTokenStatus("expired");
        else                                      setTokenStatus("invalid");
      })
      .catch(() => setTokenStatus("invalid"));
  }, [jobId]);

  useEffect(() => {
    if (!jobId || isNaN(jobId)) return;
    let cancelled = false;
    setLoading(true);
    fetchAvailableSlots(monthKey, jobId)
      .then((data) => { if (!cancelled) setSlots(data); })
      .catch(() => { if (!cancelled) setSlots([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [monthKey, jobId]);

  function refetchSlots() {
    if (!jobId || isNaN(jobId)) return;
    fetchAvailableSlots(monthKey, jobId).then(setSlots).catch(() => setSlots([]));
  }

  async function handleBook() {
    if (!selectedSlot || !candidate.name || !candidate.email) {
      toast({ title: "Please fill in your name and email", variant: "destructive" });
      return;
    }
    setPending(true);
    try {
      const bookingData = await bookSlotAPI(selectedSlot.id, candidate.name, candidate.email);
      const meetLink = bookingData?.meet_link ?? "";
      fetch(`${N8N_BASE}/webhook/confirmer-reservation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          slot_id: selectedSlot.id, candidate_name: candidate.name,
          candidate_email: candidate.email, slot_date: selectedSlot.date,
          slot_time: selectedSlot.startTime, job_id: jobId,
          job_title: job?.title ?? import.meta.env.VITE_JOB_TITLE ?? "Poste",
          meet_link: meetLink,
        }),
      }).catch(() => {});
      refetchSlots();
      setBookedSlot(selectedSlot);
      setConfirmOpen(false);
      setBooked(true);
    } catch {
      toast({ title: "Slot already booked or unavailable", variant: "destructive" });
    } finally {
      setPending(false);
    }
  }

  const start    = startOfMonth(currentMonth);
  const end      = endOfMonth(currentMonth);
  const days     = eachDayOfInterval({ start, end });
  const startPad = getDay(start);

  const availableDates = new Set(slots.map((s) => s.date));
  const slotsForDate = selectedDate ? slots.filter((s) => s.date === selectedDate) : [];

  if (tokenStatus === "checking") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-card p-8 text-center">
          <div className="w-10 h-10 rounded-full border-2 border-teal-400 border-t-transparent animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground text-sm">Verifying your link...</p>
        </div>
      </div>
    );
  }

  if (tokenStatus === "expired") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-card p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-amber-50 flex items-center justify-center mx-auto mb-4">
            <AlertCircle size={32} className="text-amber-400" />
          </div>
          <h1 className="text-xl font-bold mb-2">Link Expired</h1>
          <p className="text-muted-foreground text-sm">Your interview booking link has expired. Please contact the recruiter to request a new one.</p>
        </div>
      </div>
    );
  }

  if (tokenStatus === "used") {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-card p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-teal-50 flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 size={32} className="text-teal-500" />
          </div>
          <h1 className="text-xl font-bold mb-2">Already Booked</h1>
          <p className="text-muted-foreground text-sm">You have already used this link to book an interview. Check your email for the confirmation details.</p>
        </div>
      </div>
    );
  }

  if (!jobId || isNaN(jobId) || jobError) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-card p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
            <AlertCircle size={32} className="text-red-400" />
          </div>
          <h1 className="text-xl font-bold mb-2">Invalid Link</h1>
          <p className="text-muted-foreground text-sm">This booking link is invalid or has expired. Please contact the recruiter to get a valid link.</p>
        </div>
      </div>
    );
  }

  if (booked && bookedSlot) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-6">
        <div className="max-w-md w-full rounded-xl border border-border bg-card p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-teal-50 flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 size={32} className="text-teal-500" />
          </div>
          <h1 className="text-xl font-bold mb-2">Booking Confirmed!</h1>
          <p className="text-muted-foreground text-sm mb-6">Your interview has been scheduled. You'll receive a reminder email 15 minutes before it starts.</p>
          <div className="rounded-lg bg-muted/50 p-4 text-sm text-left space-y-2">
            {job && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Position</span>
                <span className="font-medium">{job.title}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Date</span>
              <span className="font-medium">{format(parseISO(bookedSlot.date), "EEEE, MMMM d")}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Time</span>
              <span className="font-medium">{bookedSlot.startTime} — {bookedSlot.endTime}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Email</span>
              <span className="font-medium">{candidate.email}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="max-w-2xl mx-auto">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-bold">Book Your Interview</h1>
          {job ? (
            <p className="text-muted-foreground text-sm mt-1">
              Position: <span className="font-semibold text-foreground">{job.title}</span>
              {job.location && <span> · {job.location}</span>}
            </p>
          ) : (
            <Skeleton className="h-4 w-56 mx-auto mt-2" />
          )}
          <p className="text-muted-foreground text-xs mt-2">Select a date, pick a time that works for you, and you'll receive a confirmation by email.</p>
        </div>

        <div className="rounded-xl border border-border bg-card p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold">{format(currentMonth, "MMMM yyyy")}</h2>
            <div className="flex gap-1">
              <button onClick={() => setCurrentMonth((d) => new Date(d.getFullYear(), d.getMonth() - 1, 1))}
                className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent transition-colors">
                <ChevronLeft size={16} />
              </button>
              <button onClick={() => setCurrentMonth((d) => new Date(d.getFullYear(), d.getMonth() + 1, 1))}
                className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:bg-accent transition-colors">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-7 gap-0.5 mb-2">
            {DAY_LABELS.map((d) => (
              <div key={d} className="text-center text-xs text-muted-foreground py-1">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-0.5">
            {Array.from({ length: startPad }).map((_, i) => <div key={`pad-${i}`} />)}
            {days.map((day) => {
              const dateStr  = format(day, "yyyy-MM-dd");
              const hasSlots = availableDates.has(dateStr);
              const selected = selectedDate === dateStr;
              const today    = isToday(day);
              return (
                <button key={dateStr} onClick={() => hasSlots && setSelectedDate(dateStr)}
                  disabled={!hasSlots}
                  className={cn(
                    "relative aspect-square rounded-lg flex flex-col items-center justify-center text-sm transition-colors",
                    selected              ? "bg-primary text-primary-foreground" : "",
                    hasSlots && !selected ? "hover:bg-primary/20 cursor-pointer text-foreground" : "",
                    !hasSlots             ? "text-muted-foreground/40 cursor-not-allowed" : "",
                    today && !selected    ? "ring-1 ring-primary" : "",
                  )}>
                  <span className={cn("font-medium", today && !selected && "text-primary")}>{format(day, "d")}</span>
                  {hasSlots && !selected && (
                    <span className="absolute bottom-1 left-1/2 -translate-x-1/2">
                      <span className="w-1 h-1 rounded-full bg-teal-400 block" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-4 mt-4 pt-4 border-t border-border">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-2 h-2 rounded-full bg-teal-400 inline-block" /> Available slot
            </div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="w-2 h-2 rounded-full bg-primary inline-block" /> Selected date
            </div>
          </div>
        </div>

        {selectedDate && (
          <div className="rounded-xl border border-border bg-card p-5">
            <h2 className="font-semibold mb-3">Available Times — {format(parseISO(selectedDate), "EEEE, MMMM d")}</h2>
            {isLoading ? (
              <div className="space-y-2">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
            ) : slotsForDate.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {slotsForDate.map((slot) => (
                  <button key={slot.id} onClick={() => { setSelectedSlot(slot); setConfirmOpen(true); }}
                    className="flex items-center gap-2 rounded-lg border border-border bg-background hover:border-primary/50 hover:bg-primary/5 p-3 transition-colors text-sm font-medium">
                    <Clock size={14} className="text-teal-400 shrink-0" />
                    {slot.startTime} — {slot.endTime}
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No available slots for this date.</p>
            )}
          </div>
        )}

        {!selectedDate && !isLoading && (
          <div className="text-center py-8 text-muted-foreground text-sm">
            {availableDates.size > 0 ? "Select a highlighted date above to view available times." : "No slots available this month. Try navigating to a different month."}
          </div>
        )}
      </div>

      {confirmOpen && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.55)" }}
          onClick={(e) => e.target === e.currentTarget && setConfirmOpen(false)}>
          <div style={{ background: "#ffffff", borderRadius: 16, padding: "28px 28px 24px", width: "100%", maxWidth: 400, boxShadow: "0 24px 64px rgba(0,0,0,0.18)", border: "1px solid #e2e8f0" }}>
            <div style={{ marginBottom: 20 }}>
              <h2 style={{ fontSize: 17, fontWeight: 700, color: "#1e293b", margin: "0 0 6px" }}>Confirm Your Booking</h2>
              {selectedSlot && (
                <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
                  {format(parseISO(selectedSlot.date), "EEEE, MMMM d")} · {selectedSlot.startTime} — {selectedSlot.endTime}
                </p>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 16 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Your Name</label>
                <input placeholder="Jane Smith" value={candidate.name} onChange={(e) => setCandidate((c) => ({ ...c, name: e.target.value }))}
                  style={{ padding: "9px 12px", borderRadius: 8, fontSize: 13, border: "1px solid #d1d5db", background: "#f9fafb", color: "#1e293b", outline: "none", width: "100%", boxSizing: "border-box" as const }}
                  onFocus={e => (e.currentTarget.style.borderColor = "#0d9488")} onBlur={e => (e.currentTarget.style.borderColor = "#d1d5db")} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>Your Email</label>
                <input type="email" placeholder="jane@example.com" value={candidate.email} onChange={(e) => setCandidate((c) => ({ ...c, email: e.target.value }))}
                  style={{ padding: "9px 12px", borderRadius: 8, fontSize: 13, border: "1px solid #d1d5db", background: "#f9fafb", color: "#1e293b", outline: "none", width: "100%", boxSizing: "border-box" as const }}
                  onFocus={e => (e.currentTarget.style.borderColor = "#0d9488")} onBlur={e => (e.currentTarget.style.borderColor = "#d1d5db")} />
              </div>
              <p style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#94a3b8", margin: 0 }}>
                <Mail size={12} /> A confirmation email will be sent to this address.
              </p>
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmOpen(false)}
                style={{ padding: "9px 18px", borderRadius: 8, fontSize: 13, fontWeight: 600, border: "1px solid #e2e8f0", background: "#f8fafc", color: "#475569", cursor: "pointer" }}>
                Cancel
              </button>
              <button onClick={handleBook} disabled={isPending}
                style={{ padding: "9px 20px", borderRadius: 8, fontSize: 13, fontWeight: 700, border: "none", background: isPending ? "#5eead4" : "#0d9488", color: "#fff", cursor: isPending ? "not-allowed" : "pointer", opacity: isPending ? 0.8 : 1, transition: "opacity 0.15s" }}>
                {isPending ? "Booking..." : "Confirm Booking"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function CandidateBooking() {
  return (
    <ToastProvider>
      <CandidateBookingInner />
    </ToastProvider>
  );
}