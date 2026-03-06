import axios from 'axios'
import type {
  BackupItem,
  DuplicateCandidate,
  Note,
  Paper,
  PaperListResponse,
  PaperRelationItem,
  PaperRelationsResponse,
  RelationCandidate,
  RelationType,
  Review,
  SearchResponse,
  Tag,
} from './types'

const defaultBaseURL =
  typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000'
const baseURL = import.meta.env.VITE_API_BASE_URL || defaultBaseURL

export const api = axios.create({
  baseURL,
})

export async function uploadPdf(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/api/v1/import/pdf', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as {
    paper_draft_id: string
    attachment_id: string
    parse_status: string
    metadata_candidate: {
      title?: string
      authors: string[]
      year?: number
      venue?: string
      doi?: string
      arxiv_id?: string
      abstract?: string
      language?: string
    }
  }
}

export async function confirmPaper(payload: {
  paper_draft_id: string
  title: string
  authors: string[]
  year?: number
  venue?: string
  doi?: string
  arxiv_id?: string
  abstract?: string
  summary?: string
  summary_label?: string
  language?: string
  tags: string[]
}) {
  const { data } = await api.post('/api/v1/papers/confirm', payload)
  return data as Paper
}

export async function fetchPapers(params?: {
  page?: number
  page_size?: number
  q?: string
  status?: string
  sort?: string
}) {
  const { data } = await api.get('/api/v1/papers', { params })
  return data as PaperListResponse
}

export async function fetchPaper(id: string) {
  const { data } = await api.get(`/api/v1/papers/${id}`)
  return data as Paper
}

export async function updatePaper(id: string, payload: Partial<{
  title: string
  authors: string[]
  year: number
  venue: string
  doi: string
  arxiv_id: string
  abstract: string
  summary: string
  bibtex_override: string | null
  scholar_url: string | null
  summary_label: string
  language: string
  tags: string[]
}>) {
  const { data } = await api.post(`/api/v1/papers/${id}`, payload)
  return data as Paper
}

export async function deletePaper(id: string) {
  await api.delete(`/api/v1/papers/${id}`)
}

export async function searchPapers(q: string) {
  const { data } = await api.get('/api/v1/search', { params: { q } })
  return data as SearchResponse
}

export async function fetchNotes(paperId: string) {
  const { data } = await api.get(`/api/v1/papers/${paperId}/notes`)
  return data as Note[]
}

export async function addNote(paperId: string, payload: {
  attachment_id?: string
  page_number?: number
  quote_text?: string
  note_text: string
}) {
  const { data } = await api.post(`/api/v1/papers/${paperId}/notes`, payload)
  return data as Note
}

export async function deleteNote(noteId: string) {
  await api.delete(`/api/v1/notes/${noteId}`)
}

export async function fetchReviews(paperId: string) {
  const { data } = await api.get(`/api/v1/papers/${paperId}/reviews`)
  return data as Review[]
}

export async function addReview(paperId: string, payload: {
  attachment_id?: string
  page_number?: number
  quote_text?: string
  note_text: string
}) {
  const { data } = await api.post(`/api/v1/papers/${paperId}/reviews`, payload)
  return data as Review
}

export async function deleteReview(reviewId: string) {
  await api.delete(`/api/v1/reviews/${reviewId}`)
}

export async function updateReview(reviewId: string, payload: {
  attachment_id?: string
  page_number?: number
  quote_text?: string
  note_text: string
}) {
  const { data } = await api.patch(`/api/v1/reviews/${reviewId}`, payload)
  return data as Review
}

export async function fetchDuplicates(paperId: string) {
  const { data } = await api.get(`/api/v1/papers/${paperId}/duplicates`)
  return data as DuplicateCandidate[]
}

export async function resolveDuplicates(
  paperId: string,
  items: Array<{ duplicate_paper_id: string; status: 'ignored' | 'confirmed_duplicate' }>,
) {
  await api.post(`/api/v1/papers/${paperId}/duplicates/resolve`, { items })
}

export async function fetchCitation(paperId: string, style: 'bibtex' | 'apa') {
  const { data } = await api.get(`/api/v1/papers/${paperId}/citation`, { params: { style } })
  return data as { paper_id: string; style: 'bibtex' | 'apa'; citation: string }
}

export async function fetchCitationBatch(paperIds: string[], style: 'bibtex' | 'apa') {
  const { data } = await api.post('/api/v1/citation/batch', { paper_ids: paperIds, style })
  return data as {
    style: 'bibtex' | 'apa'
    items: Array<{ paper_id: string; style: 'bibtex' | 'apa'; citation: string }>
  }
}

export function bibtexExportUrl(paperIds: string[]) {
  const params = new URLSearchParams({ paper_ids: paperIds.join(',') })
  return `${baseURL}/api/v1/citation/export/bib?${params.toString()}`
}

export async function runBackup(kind: 'daily' | 'weekly') {
  const { data } = await api.post('/api/v1/backup/run', { kind })
  return data as BackupItem
}

export async function listBackups() {
  const { data } = await api.get('/api/v1/backup/list')
  return data as BackupItem[]
}

export async function restoreBackup(filename: string) {
  await api.post('/api/v1/backup/restore', { filename })
}

export async function fetchTags() {
  const { data } = await api.get('/api/v1/tags')
  return data as Tag[]
}

export function attachmentUrl(attachmentId: string) {
  return `${baseURL}/api/v1/attachments/${attachmentId}/file`
}

export async function openAttachment(attachmentId: string, target: 'preview' | 'browser') {
  await api.post(`/api/v1/attachments/${attachmentId}/open`, null, {
    params: { target },
  })
}

export async function openExternalUrl(url: string) {
  await api.post('/api/v1/open/external', null, { params: { url } })
}

export async function deleteAttachment(attachmentId: string) {
  await api.delete(`/api/v1/attachments/${attachmentId}`)
}

export async function uploadPaperAttachment(paperId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post(`/api/v1/papers/${paperId}/attachments`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data as { id: string; original_filename: string; page_count: number; file_size: number; imported_at: string }
}

export async function addPaperLink(paperId: string, payload: { label?: string; url: string }) {
  const { data } = await api.post(`/api/v1/papers/${paperId}/links`, payload)
  return data as { id: number; paper_id: string; label?: string | null; url: string; created_at: string }
}

export async function deletePaperLink(linkId: number) {
  await api.delete(`/api/v1/paper-links/${linkId}`)
}

export async function fetchPaperRelations(paperId: string) {
  const { data } = await api.get(`/api/v1/papers/${paperId}/relations`)
  return data as PaperRelationsResponse
}

export async function fetchRelationCandidates(
  paperId: string,
  params?: { q?: string; limit?: number },
) {
  const { data } = await api.get(`/api/v1/papers/${paperId}/relations/candidates`, { params })
  return data as RelationCandidate[]
}

export async function addPaperRelation(paperId: string, payload: {
  target_paper_id: string
  relation_type: RelationType
  note?: string
}) {
  const { data } = await api.post(`/api/v1/papers/${paperId}/relations`, payload)
  return data as PaperRelationItem
}

export async function deletePaperRelation(relationId: number) {
  await api.delete(`/api/v1/paper-relations/${relationId}`)
}
