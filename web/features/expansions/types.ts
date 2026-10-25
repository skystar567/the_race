export interface Expansion {
  id: string;
  course_id: string;
  version_id: string;
  answer_id: string | null;
  concept_id: string | null;
  question: string;
  status: 'completed' | 'failed';
  text: string;
  error_code: string | null;
  error_message: string | null;
  origin: 'model_expansion';
  created_at: number;
}
