import { knowledgeUrl, type Chapter, type MaterialDetail } from '../../api';

export type CoverageStatus = 'unorganized' | 'partial' | 'organized';

export interface ScopeCoverage {
  status: CoverageStatus;
  organized_fragments: number;
  total_fragments: number;
}

export interface KnowledgeCoverage {
  course_id: string;
  version_id: string | null;
  materials: Array<Omit<MaterialDetail, 'status' | 'chapters'> & ScopeCoverage & {
    chapters: Array<Chapter & ScopeCoverage>;
  }>;
}

export const COVERAGE_LABEL: Record<CoverageStatus, string> = {
  unorganized: '尚未整理', partial: '部分已整理', organized: '已整理',
};

export function coverageUrl(courseId: string, versionId?: string | null): string {
  return knowledgeUrl(courseId) + '/coverage' + (versionId ? `?version_id=${encodeURIComponent(versionId)}` : '');
}

