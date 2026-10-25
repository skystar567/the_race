export interface Course {
  id: string;
  name: string;
  material_count: number;
}

export interface Material {
  id: string;
  course_id: string;
  filename: string;
  byte_size: number;
  status: 'imported';
  created_at: string;
}

export interface Chapter {
  id: string;
  title: string;
  level: number;
  parent_id: string | null;
  start_line: number;
  end_line: number;
}

export interface MaterialDetail extends Material {
  chapters: Chapter[];
  fragment_count: number;
  missing_image_count: number;
}

export interface Fragment {
  id: string;
  chapter_id: string | null;
  start_line: number;
  end_line: number;
  markdown: string;
  html: string;
}

export type RelationKind = 'contains' | 'precedes' | 'contrasts';
export type RelationOrigin = 'source' | 'suggested';

export interface Citation {
  snippet_id: string;
  quote: string;
}

export interface KnowledgeConcept {
  id: string;
  name: string;
  aliases: string[];
  definition: string;
  page_md: string;
  chapter_ids: string[];
  status: string;
  is_new: boolean;
  citations: Citation[];
}

export interface KnowledgeRelation {
  id: string;
  kind: RelationKind;
  from_type: 'chapter' | 'concept';
  from_id: string;
  to_type: 'chapter' | 'concept';
  to_id: string;
  origin: RelationOrigin;
  citation: Citation | null;
  reason: string;
}

export interface KnowledgeChapter {
  id: string;
  title: string;
  level: number;
  parent_id: string | null;
  start_line: number;
  end_line: number;
  material_id: string;
  filename: string;
}

export interface KnowledgeFragment {
  id: string;
  chapter_id: string | null;
  start_line: number;
  end_line: number;
  kind: string;
  markdown: string;
  missing_images: number;
  material_id: string;
  filename: string;
}

export interface KnowledgeSnapshot {
  course_id: string;
  version_id: string | null;
  state: 'published' | 'unpublished';
  concepts: KnowledgeConcept[];
  relations: KnowledgeRelation[];
  chapters: KnowledgeChapter[];
  fragments: KnowledgeFragment[];
  selection: { material_ids: string[]; chapter_ids: string[] } | null;
  summary: { new_concepts: number; updated_concepts: number; conflicts: number } | null;
}

export interface ConceptDetail extends KnowledgeConcept {
  version_id: string;
  html: string;
  citations: Array<Citation & {
    filename: string;
    start_line: number;
    end_line: number;
    chapter_title: string | null;
  }>;
}

export interface SourceDetail extends KnowledgeFragment {
  version_id: string;
  chapter_title: string | null;
  html: string;
}

export interface TaskStep {
  name: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  attempts: number;
}

export interface Task {
  id: string;
  course_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  selection: { material_ids: string[]; chapter_ids: string[] };
  scope: { characters: number; fragments: number; chapters: number };
  version_id: string | null;
  error_code: string | null;
  error_message: string | null;
  steps: TaskStep[];
}

export interface ModelStatus {
  model: string;
  configured: boolean;
  message: string;
}

export interface KnowledgeVersion {
  id: string;
  task_id: string;
  state: 'candidate' | 'published' | 'failed';
  parent_version_id: string | null;
  created_at: string;
  is_current: boolean;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body: { detail?: unknown } = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `请求未完成（${response.status}），请检查输入后重试。`);
  }
  return response.json() as Promise<T>;
}

export function materialUrl(courseId: string, materialId: string): string {
  return `/api/courses/${encodeURIComponent(courseId)}/materials/${encodeURIComponent(materialId)}`;
}

export function knowledgeUrl(courseId: string): string {
  return `/api/courses/${encodeURIComponent(courseId)}/knowledge`;
}

export function conceptUrl(courseId: string, versionId: string, conceptId: string): string {
  return `${knowledgeUrl(courseId)}/versions/${encodeURIComponent(versionId)}/concepts/${encodeURIComponent(conceptId)}`;
}

export function sourceUrl(courseId: string, versionId: string, snippetId: string): string {
  return `${knowledgeUrl(courseId)}/versions/${encodeURIComponent(versionId)}/sources/${encodeURIComponent(snippetId)}`;
}

export function tasksUrl(courseId: string): string {
  return `/api/courses/${encodeURIComponent(courseId)}/tasks`;
}

export type AnswerStatus = 'generating' | 'completed' | 'insufficient' | 'citation_failed' | 'interrupted' | 'failed';

export interface AnswerScope {
  material_ids: string[];
  chapter_ids: string[];
  label: string;
  fragment_count: number;
}

export interface AnswerCitation {
  snippet_id: string;
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
