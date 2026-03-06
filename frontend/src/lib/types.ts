export interface Author {
  id: number
  name: string
}

export interface Attachment {
  id: string
  original_filename: string
  page_count: number
  file_size: number
  imported_at: string
}

export interface PaperLink {
  id: number
  paper_id: string
  label?: string | null
  url: string
  created_at: string
}

export interface Tag {
  id: number
  name: string
  color?: string | null
}

export interface Paper {
  id: string
  status: string
  title?: string | null
  original_title?: string | null
  year?: number | null
  venue?: string | null
  doi?: string | null
  arxiv_id?: string | null
  abstract?: string | null
  summary?: string | null
  bibtex_override?: string | null
  scholar_url?: string | null
  summary_label?: string | null
  language?: string | null
  needs_manual_metadata: boolean
  created_at: string
  updated_at: string
  authors: Author[]
  attachments: Attachment[]
  tags: Tag[]
  links: PaperLink[]
}

export interface PaperListResponse {
  total: number
  page: number
  page_size: number
  items: Paper[]
}

export interface SearchResponse {
  query: string
  scope: 'meta'
  items: Array<{
    paper_id: string
    title?: string | null
    score?: number | null
    snippet?: string | null
  }>
}

export type RelationType = 'cite' | 'related'

export interface PaperRelationItem {
  relation_id: number
  peer_paper_id: string
  peer_title?: string | null
  peer_year?: number | null
  note?: string | null
  updated_at: string
  relation_type: RelationType
  read_only: boolean
}

export interface PaperRelationsResponse {
  paper_id: string
  cites: PaperRelationItem[]
  cited_by: PaperRelationItem[]
  related: PaperRelationItem[]
}

export interface RelationCandidate {
  paper_id: string
  title?: string | null
  year?: number | null
  snippet?: string | null
  score?: number | null
  existing_types: RelationType[]
}

export interface Note {
  id: string
  paper_id: string
  attachment_id?: string | null
  page_number?: number | null
  quote_text?: string | null
  note_text: string
  created_at: string
  updated_at: string
}

export interface Review extends Note {}

export interface DuplicateCandidate {
  paper_id: string
  title?: string | null
  score: number
}

export interface BackupItem {
  filename: string
  size: number
  created_at: string
}
