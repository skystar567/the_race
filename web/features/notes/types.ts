export interface NoteCitation {
  snippet_id: string;
  source_url?: string;
  version_id?: string;
  quote?: string;
  filename: string;
  chapter_title: string | null;
  start_line: number;
  end_line: number;
  excerpt: string;
}

export interface NoteSummary {
  id: string;
  title: string;
  version_id: string | null;
  source_type: 'manual' | 'concept' | 'answer' | 'expansion';
  source_id: string | null;
  expansion: boolean;
  revision: number;
  citation_count: number;
  needs_review: boolean;
  review_reason: string | null;
  updated_at: number;
}

export interface NoteDetail extends NoteSummary {
  course_id: string;
  body_md: string;
  html: string;
  citations: NoteCitation[];
  created_at: number;
}

