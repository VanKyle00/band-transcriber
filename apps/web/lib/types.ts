export type StemArtifacts = {
  name: string;
  experimental: boolean;
  warnings: string[];
  audio?: string;
  midi?: string;
  musicxml?: string;
  sheet_pdf?: string;
  sheet_svg?: string;
  tab?: string;
  tab_alphatex?: string;
};

export type JobStatus = "queued" | "processing" | "done" | "error";

export type Job = {
  id: string;
  status: JobStatus;
  stage?: string;
  source_type?: string;
  artifacts?: { stems: StemArtifacts[] };
  error?: string;
  created_at?: string;
  expires_at?: string;
};

export const ALL_STEMS = ["drums", "bass", "vocals", "guitar", "piano"] as const;
