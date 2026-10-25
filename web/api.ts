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
