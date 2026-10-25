export type AnswerStatus = 'generating' | 'completed' | 'insufficient' | 'citation_failed' | 'interrupted' | 'failed';

export interface AnswerScope {
  material_ids: string[];
  chapter_ids: string[];
  label: string;
  fragment_count: number;
}

export interface AnswerCitation {
  snippet_id: string;
  source_url?: string;
  version_id?: string;
  filename: string;
  chapter_title: string | null;
  start_line: number;
  end_line: number;
  excerpt: string;
}

export interface AnswerSummary {
  id: string;
  version_id: string;
  question: string;
  status: AnswerStatus;
  scope: AnswerScope;
  focus_concept_id: string | null;
  citation_count: number;
  error_code: string | null;
  error_message: string | null;
  created_at: number;
}

export interface AnswerDetail extends AnswerSummary {
  course_id: string;
  text: string;
  html: string;
  citations: AnswerCitation[];
}

export interface AnswerStart {
  answer_id: string;
  version_id: string;
  scope: AnswerScope;
  focus: string | null;
  evidence_count: number;
  missing_image_count: number;
  resolution: 'keyword' | 'model' | 'none';
}

