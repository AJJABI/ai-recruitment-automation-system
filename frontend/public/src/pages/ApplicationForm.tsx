import { useState, useRef, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  User, Mail, Phone, MapPin, Linkedin, Briefcase,
  FileText, Upload, CheckCircle2, ArrowRight, ArrowLeft,
  X, File, Sparkles, ChevronRight, Loader2,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const MAX_FILE_SIZE = 5 * 1024 * 1024;
const ACCEPTED_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

const schema = z.object({
  nom: z.string().min(2, "Le nom doit contenir au moins 2 caractères"),
  prenom: z.string().min(2, "Le prénom doit contenir au moins 2 caractères"),
  email: z.string().email("Adresse email invalide"),
  telephone: z
    .string()
    .min(8, "Numéro de téléphone invalide")
    .regex(/^[+\d\s\-()]+$/, "Format invalide"),
  adresse: z.string().min(5, "L'adresse doit contenir au moins 5 caractères"),
  linkedin: z.string().url("URL invalide").optional().or(z.literal("")),
  job_id: z.number({ message: "Veuillez sélectionner un poste" }),
  cv: z.any().optional(),
  lettre: z.any().optional(),
});

type FormData = z.infer<typeof schema>;

interface Job {
  id: number;
  title: string;
  company?: string;
  description?: string;
}

const STEPS = [
  { id: 1, label: "Identité", icon: User },
  { id: 2, label: "Contact", icon: Phone },
  { id: 3, label: "Candidature", icon: Briefcase },
  { id: 4, label: "Documents", icon: FileText },
];

const stepFields: Record<number, (keyof FormData)[]> = {
  1: ["nom", "prenom"],
  2: ["email", "telephone", "adresse"],
  3: ["job_id"],
  4: [],
};

// --- FileUpload ---
interface FileUploadProps {
  label: string;
  description: string;
  icon: React.ReactNode;
  file: File | null;
  onFile: (f: File | null) => void;
  color: string;
}

function FileUpload({ label, description, icon, file, onFile, color }: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (f: File) => {
    if (!ACCEPTED_TYPES.includes(f.type)) { setError("Format accepté : PDF, DOC, DOCX"); return; }
    if (f.size > MAX_FILE_SIZE) { setError("Fichier trop volumineux (max 5 MB)"); return; }
    setError(null);
    onFile(f);
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-semibold text-foreground">{label}</label>
      {file ? (
        <div className={`flex items-center gap-3 p-4 rounded-xl border-2 ${color} bg-accent/30`}>
          <div className={`p-2 rounded-lg ${color} bg-white`}><File className="w-5 h-5 text-primary" /></div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{file.name}</p>
            <p className="text-xs text-muted-foreground">{formatSize(file.size)}</p>
          </div>
          <button type="button" onClick={() => onFile(null)}
            className="p-1.5 rounded-lg hover:bg-destructive/10 hover:text-destructive transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <div
          className={`upload-zone rounded-xl p-6 text-center cursor-pointer ${dragging ? "drag-over" : ""}`}
          onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".pdf,.doc,.docx" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
          <div className="flex flex-col items-center gap-3">
            <div className="p-3 rounded-full bg-accent">{icon}</div>
            <div>
              <p className="text-sm font-semibold">Glissez votre fichier ici</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                ou <span className="text-primary font-medium">parcourir</span> depuis votre ordinateur
              </p>
              <p className="text-xs text-muted-foreground mt-1">{description}</p>
            </div>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-destructive flex items-center gap-1"><X className="w-3 h-3" />{error}</p>}
    </div>
  );
}

// --- InputField ---
interface InputFieldProps {
  label: string;
  icon: React.ReactNode;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}

function InputField({ label, icon, error, required, children }: InputFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
        {label}{required && <span className="text-primary text-xs">*</span>}
      </label>
      <div className="relative">
        <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">{icon}</div>
        {children}
      </div>
      {error && <p className="text-xs text-destructive flex items-center gap-1"><X className="w-3 h-3" />{error}</p>}
    </div>
  );
}

// --- Composant principal ---
export default function ApplicationForm() {
  const [step, setStep] = useState(1);
  const [submitted, setSubmitted] = useState(false);
  const [cv, setCv] = useState<File | null>(null);
  const [lettre, setLettre] = useState<File | null>(null);
  const [jobOpen, setJobOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [alreadyApplied, setAlreadyApplied] = useState<{ application_id: number; status_v2: string; applied_at: string } | null>(null);

  const { register, handleSubmit, formState: { errors }, trigger, setValue, watch } = useForm<FormData>({
    resolver: zodResolver(schema),
    mode: "onBlur",
  });

  // Chargement des jobs disponibles depuis le backend
  useEffect(() => {
    fetch(`${API_BASE}/jobs/`)
      .then((r) => r.json())
      .then((data) => { setJobs(data); setLoadingJobs(false); })
      .catch(() => setLoadingJobs(false));
  }, []);

  const handleNext = async () => {
    const valid = await trigger(stepFields[step]);
    if (valid) setStep((s) => Math.min(s + 1, 4));
  };

  const handleBack = () => setStep((s) => Math.max(s - 1, 1));

  const onSubmit = async (data: FormData) => {
    if (!cv) { setSubmitError("Le CV est obligatoire."); return; }
    if (!lettre) { setSubmitError("La lettre de motivation est obligatoire."); return; }

    setSubmitting(true);
    setSubmitError(null);

    const formData = new FormData();
    formData.append("candidate_email", data.email);
    formData.append("cv", cv);
    formData.append("lettre", lettre);

    try {
      const res = await fetch(`${API_BASE}/apply/${data.job_id}`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        // Cas spécial : candidat déjà postulé
        if (err?.detail?.error === "ALREADY_APPLIED") {
          setAlreadyApplied({
            application_id: err.detail.application_id,
            status_v2: err.detail.status_v2,
            applied_at: err.detail.applied_at,
          });
          setSubmitting(false);
          return;
        }
        setSubmitError(err?.detail?.message || err?.detail || "Erreur lors de l'envoi.");
        setSubmitting(false);
        return;
      }

      setSubmitted(true);
    } catch {
      setSubmitError("Impossible de contacter le serveur. Vérifiez votre connexion.");
    } finally {
      setSubmitting(false);
    }
  };

  const progress = ((step - 1) / (STEPS.length - 1)) * 100;

  const resetForm = () => {
    setSubmitted(false); setStep(1); setCv(null);
    setLettre(null); setSelectedJob(null); setSubmitError(null); setAlreadyApplied(null);
  };

  // ── Candidat déjà postulé ─────────────────────────────────────────────────
  if (alreadyApplied) {
    const statusLabels: Record<string, string> = {
      APPLIED: "Reçue",
      ANALYZED: "En analyse",
      MATCHED: "Évaluée",
      PENDING: "En attente",
      PRESELECTED: "Présélectionné(e)",
      TEST_SENT: "Test envoyé",
      TEST_IN_PROGRESS: "Test en cours",
      TEST_COMPLETED: "Test complété",
      INTERVIEW_ELIGIBLE: "Éligible entretien",
      INTERVIEW_SCHEDULED: "Entretien planifié",
      REJECTED_AUTO: "Non retenu(e)",
      REJECTED_FINAL: "Non retenu(e)",
    };
    return (
      <div className="min-h-screen flex items-center justify-center p-4"
        style={{ background: "linear-gradient(135deg, hsl(220 20% 97%), hsl(199 89% 96%), hsl(222 89% 96%))" }}>
        <div className="glass-card rounded-3xl p-10 max-w-md w-full text-center">
          <div className="w-20 h-20 rounded-full bg-amber-50 border-4 border-amber-100 flex items-center justify-center mx-auto mb-6">
            <Briefcase className="w-10 h-10 text-amber-500" />
          </div>
          <h2 className="text-2xl font-bold mb-2">Déjà postulé !</h2>
          <p className="text-muted-foreground mb-4">
            Vous avez déjà soumis une candidature pour ce poste.
          </p>
          {selectedJob && (
            <p className="text-sm font-medium text-primary mb-2">Poste : {selectedJob.title}</p>
          )}
          <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 mb-6 text-left space-y-2">
            <p className="text-xs text-amber-800">
              <span className="font-semibold">Statut actuel :</span>{" "}
              {statusLabels[alreadyApplied.status_v2] || alreadyApplied.status_v2}
            </p>
            <p className="text-xs text-amber-700">
              <span className="font-semibold">Postulé le :</span>{" "}
              {new Date(alreadyApplied.applied_at).toLocaleDateString("fr-FR", {
                day: "numeric", month: "long", year: "numeric"
              })}
            </p>
          </div>
          <p className="text-xs text-muted-foreground mb-6">
            Vous recevrez un email dès que votre dossier sera traité.
          </p>
          <button onClick={resetForm}
            className="w-full py-3 rounded-xl font-semibold text-white shimmer-bg hover:opacity-90 transition-opacity">
            Postuler à un autre poste
          </button>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4"
        style={{ background: "linear-gradient(135deg, hsl(220 20% 97%), hsl(199 89% 96%), hsl(222 89% 96%))" }}>
        <div className="glass-card rounded-3xl p-10 max-w-md w-full text-center">
          <div className="w-20 h-20 rounded-full bg-green-50 border-4 border-green-100 flex items-center justify-center mx-auto mb-6">
            <CheckCircle2 className="w-10 h-10 text-green-500" />
          </div>
          <h2 className="text-2xl font-bold mb-2">Candidature envoyée !</h2>
          <p className="text-muted-foreground mb-2">Notre équipe la traitera dans les meilleurs délais.</p>
          {selectedJob && <p className="text-sm font-medium text-primary mb-8">Poste : {selectedJob.title}</p>}
          <button onClick={resetForm}
            className="w-full py-3 rounded-xl font-semibold text-white shimmer-bg hover:opacity-90 transition-opacity">
            Soumettre une nouvelle candidature
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen"
      style={{ background: "linear-gradient(135deg, hsl(220 20% 97%), hsl(199 89% 96%), hsl(222 89% 96%))" }}>
      <div className="relative z-10 max-w-2xl mx-auto px-4 py-12">
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 text-primary text-sm font-medium mb-4">
            <Sparkles className="w-4 h-4" /> Postulez en quelques étapes
          </div>
          <h1 className="text-4xl font-bold mb-3">
            <span className="gradient-text">Rejoignez notre équipe</span>
          </h1>
          <p className="text-muted-foreground text-lg">Complétez le formulaire ci-dessous</p>
        </div>

        <div className="glass-card rounded-3xl overflow-hidden">
          <div className="p-6 pb-0">
            <div className="flex items-center justify-between mb-6">
              {STEPS.map((s) => {
                const Icon = s.icon;
                const isActive = step === s.id;
                const isDone = step > s.id;
                return (
                  <div key={s.id} className="flex flex-col items-center gap-2 flex-1">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold transition-all
                      ${isDone || isActive ? "bg-primary text-white shadow-lg shadow-primary/30" : "bg-muted text-muted-foreground"}
                      ${isActive ? "scale-110" : ""}`}>
                      {isDone ? <CheckCircle2 className="w-5 h-5" /> : <Icon className="w-4 h-4" />}
                    </div>
                    <span className={`text-xs font-medium hidden sm:block ${isActive || isDone ? "text-primary" : "text-muted-foreground"}`}>
                      {s.label}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden mb-6">
              <div className="h-full rounded-full shimmer-bg transition-all duration-500"
                style={{ width: `${progress === 0 ? 5 : progress}%` }} />
            </div>
            <p className="text-xs text-muted-foreground text-right mb-2">Étape {step} sur {STEPS.length}</p>
          </div>

          <form onSubmit={handleSubmit(onSubmit)} className="p-6 pt-2 space-y-6">

            {/* Étape 1 — Identité */}
            {step === 1 && (
              <div className="space-y-5">
                <h2 className="text-lg font-bold">Informations personnelles</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <InputField label="Nom" icon={<User className="w-4 h-4" />} error={errors.nom?.message} required>
                    <input {...register("nom")} placeholder="Dupont"
                      className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm" />
                  </InputField>
                  <InputField label="Prénom" icon={<User className="w-4 h-4" />} error={errors.prenom?.message} required>
                    <input {...register("prenom")} placeholder="Marie"
                      className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm" />
                  </InputField>
                </div>
              </div>
            )}

            {/* Étape 2 — Contact */}
            {step === 2 && (
              <div className="space-y-5">
                <h2 className="text-lg font-bold">Coordonnées</h2>
                <InputField label="Email" icon={<Mail className="w-4 h-4" />} error={errors.email?.message} required>
                  <input {...register("email")} type="email" placeholder="marie.dupont@example.com"
                    className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm" />
                </InputField>
                <InputField label="Téléphone" icon={<Phone className="w-4 h-4" />} error={errors.telephone?.message} required>
                  <input {...register("telephone")} type="tel" placeholder="+216 XX XXX XXX"
                    className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm" />
                </InputField>
                <InputField label="Adresse" icon={<MapPin className="w-4 h-4" />} error={errors.adresse?.message} required>
                  <textarea {...register("adresse")} placeholder="Tunis, Tunisie" rows={2}
                    className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm resize-none" />
                </InputField>
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold">LinkedIn / Portfolio <span className="text-xs text-muted-foreground">(optionnel)</span></label>
                  <div className="relative">
                    <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"><Linkedin className="w-4 h-4" /></div>
                    <input {...register("linkedin")} type="url" placeholder="https://linkedin.com/in/votre-profil"
                      className="input-field w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-white/80 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 text-sm" />
                  </div>
                  {errors.linkedin?.message && <p className="text-xs text-destructive">{errors.linkedin.message}</p>}
                </div>
              </div>
            )}

            {/* Étape 3 — Sélection du poste depuis la DB */}
            {step === 3 && (
              <div className="space-y-5">
                <h2 className="text-lg font-bold">Votre candidature</h2>
                <div className="space-y-1.5">
                  <label className="text-sm font-semibold">Poste disponible <span className="text-primary text-xs">*</span></label>
                  <input type="hidden" {...register("job_id", { valueAsNumber: true })} />
                  <div className="relative">
                    <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none">
                      <Briefcase className="w-4 h-4" />
                    </div>
                    <button type="button" onClick={() => setJobOpen(!jobOpen)} disabled={loadingJobs}
                      className="w-full pl-10 pr-10 py-3 rounded-xl border border-border bg-white/80 text-left text-sm focus:outline-none focus:border-primary disabled:opacity-60">
                      {loadingJobs ? (
                        <span className="text-muted-foreground/60 flex items-center gap-2">
                          <Loader2 className="w-3 h-3 animate-spin" /> Chargement...
                        </span>
                      ) : (
                        <span className={selectedJob ? "" : "text-muted-foreground/60"}>
                          {selectedJob ? selectedJob.title : "Sélectionnez un poste..."}
                        </span>
                      )}
                    </button>
                    <ChevronRight className={`absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 transition-transform ${jobOpen ? "rotate-90" : ""}`} />
                  </div>

                  {jobOpen && (
                    <div className="relative z-20 w-full bg-white border border-border rounded-xl shadow-xl overflow-hidden">
                      {jobs.length === 0 ? (
                        <p className="text-sm text-muted-foreground p-4 text-center">Aucun poste disponible.</p>
                      ) : jobs.map((job) => (
                        <button key={job.id} type="button"
                          className="w-full px-4 py-3 text-left hover:bg-accent hover:text-primary transition-colors border-b border-border/40 last:border-0"
                          onClick={() => { setValue("job_id", job.id); setSelectedJob(job); setJobOpen(false); }}>
                          <p className="text-sm font-medium">{job.title}</p>
                          {job.company && <p className="text-xs text-muted-foreground">{job.company}</p>}
                        </button>
                      ))}
                    </div>
                  )}

                  {errors.job_id?.message && (
                    <p className="text-xs text-destructive">{String(errors.job_id.message)}</p>
                  )}
                </div>

                {selectedJob?.description && (
                  <div className="p-4 rounded-xl bg-accent/50 border border-border/40">
                    <p className="text-xs font-semibold text-primary mb-1">Description du poste</p>
                    <p className="text-xs text-muted-foreground line-clamp-4">{selectedJob.description}</p>
                  </div>
                )}
              </div>
            )}

            {/* Étape 4 — Documents */}
            {step === 4 && (
              <div className="space-y-5">
                <h2 className="text-lg font-bold">Documents</h2>
                <FileUpload label="CV *" description="PDF ou DOCX – 5 MB max"
                  icon={<Upload className="w-5 h-5 text-primary" />} file={cv} onFile={setCv} color="border-primary/30" />
                <FileUpload label="Lettre de motivation *" description="PDF ou DOCX – 5 MB max"
                  icon={<FileText className="w-5 h-5 text-primary" />} file={lettre} onFile={setLettre} color="border-primary/30" />
                {submitError && (
                  <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20">
                    <p className="text-xs text-destructive flex items-center gap-1"><X className="w-3 h-3" />{submitError}</p>
                  </div>
                )}
                <p className="text-xs text-muted-foreground p-4 rounded-xl bg-accent/50">
                  En soumettant ce formulaire, vous acceptez que vos données soient traitées dans le cadre de votre candidature.
                </p>
              </div>
            )}

            {/* Navigation */}
            <div className="flex items-center justify-between pt-2">
              {step > 1 ? (
                <button type="button" onClick={handleBack}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-xl border border-border bg-white/80 hover:bg-muted text-sm font-medium transition-all">
                  <ArrowLeft className="w-4 h-4" /> Précédent
                </button>
              ) : <div />}

              {step < 4 ? (
                <button type="button" onClick={handleNext}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white shimmer-bg hover:opacity-90 shadow-lg shadow-primary/30">
                  Suivant <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button type="submit" disabled={submitting}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white shimmer-bg hover:opacity-90 shadow-lg shadow-primary/30 disabled:opacity-60">
                  {submitting
                    ? <><Loader2 className="w-4 h-4 animate-spin" /> Envoi en cours...</>
                    : <><CheckCircle2 className="w-4 h-4" /> Soumettre ma candidature</>}
                </button>
              )}
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}