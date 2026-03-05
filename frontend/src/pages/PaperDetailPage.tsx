import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import {
  addPaperRelation,
  addReview,
  addPaperLink,
  attachmentUrl,
  deleteAttachment,
  deletePaper,
  deletePaperRelation,
  deletePaperLink,
  deleteReview,
  fetchPaper,
  fetchPaperRelations,
  fetchRelationCandidates,
  fetchReviews,
  fetchTags,
  openAttachment,
  updatePaper,
  updateReview,
  uploadPaperAttachment,
} from '../lib/api'
import { applyTagSuggestion, splitTagInputForSuggestions } from '../lib/tag-suggestions'
import { parseTagsInput } from '../lib/tag-utils'
import type { RelationType } from '../lib/types'

export function PaperDetailPage() {
  const { paperId } = useParams<{ paperId: string }>()
  const queryClient = useQueryClient()
  const [reviewText, setReviewText] = useState('')
  const [editingReviewId, setEditingReviewId] = useState<string | null>(null)
  const [editingReviewText, setEditingReviewText] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [titleInput, setTitleInput] = useState('')
  const [summaryInput, setSummaryInput] = useState('')
  const [linkLabelInput, setLinkLabelInput] = useState('')
  const [linkUrlInput, setLinkUrlInput] = useState('')
  const [isTagsOpen, setIsTagsOpen] = useState(false)
  const [isSupplementalOpen, setIsSupplementalOpen] = useState(false)
  const [isLinksOpen, setIsLinksOpen] = useState(false)
  const [tagSuggestOpen, setTagSuggestOpen] = useState(false)
  const [relationTypeInput, setRelationTypeInput] = useState<RelationType>('related')
  const [relationNoteInput, setRelationNoteInput] = useState('')
  const [relationSearchInput, setRelationSearchInput] = useState('')
  const [relationSearchQuery, setRelationSearchQuery] = useState('')
  const [isRelationScoreHelpOpen, setIsRelationScoreHelpOpen] = useState(false)

  const paperQuery = useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => fetchPaper(paperId!),
    enabled: Boolean(paperId),
  })

  const reviewsQuery = useQuery({
    queryKey: ['reviews', paperId],
    queryFn: () => fetchReviews(paperId!),
    enabled: Boolean(paperId),
  })

  const tagsCatalogQuery = useQuery({
    queryKey: ['tags-catalog'],
    queryFn: fetchTags,
  })

  const relationsQuery = useQuery({
    queryKey: ['paper-relations', paperId],
    queryFn: () => fetchPaperRelations(paperId!),
    enabled: Boolean(paperId) && paperQuery.data?.status === 'confirmed',
  })

  const relationCandidatesQuery = useQuery({
    queryKey: ['paper-relation-candidates', paperId, relationSearchQuery],
    queryFn: () =>
      fetchRelationCandidates(paperId!, {
        q: relationSearchQuery || undefined,
        limit: 10,
      }),
    enabled: Boolean(paperId) && paperQuery.data?.status === 'confirmed',
  })

  const reviewMutation = useMutation({
    mutationFn: () => addReview(paperId!, { note_text: reviewText }),
    onSuccess: () => {
      setReviewText('')
      queryClient.invalidateQueries({ queryKey: ['reviews', paperId] })
    },
  })

  const deleteReviewMutation = useMutation({
    mutationFn: (reviewId: string) => deleteReview(reviewId),
    onSuccess: (_, reviewId) => {
      if (editingReviewId === reviewId) {
        setEditingReviewId(null)
        setEditingReviewText('')
      }
      queryClient.invalidateQueries({ queryKey: ['reviews', paperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const updateReviewMutation = useMutation({
    mutationFn: (payload: { reviewId: string; noteText: string }) =>
      updateReview(payload.reviewId, { note_text: payload.noteText }),
    onSuccess: () => {
      setEditingReviewId(null)
      setEditingReviewText('')
      queryClient.invalidateQueries({ queryKey: ['reviews', paperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const deletePaperMutation = useMutation({
    mutationFn: (id: string) => deletePaper(id),
    onSuccess: () => {
      window.location.href = '/'
    },
  })

  const updateTagsMutation = useMutation({
    mutationFn: (payload: { paperId: string; tags: string[] }) =>
      updatePaper(payload.paperId, { tags: payload.tags }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
    },
  })

  const updateMetadataMutation = useMutation({
    mutationFn: (payload: { paperId: string; title: string; summary: string }) =>
      updatePaper(payload.paperId, {
        title: payload.title,
        summary: payload.summary,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const uploadAttachmentMutation = useMutation({
    mutationFn: (payload: { paperId: string; file: File }) =>
      uploadPaperAttachment(payload.paperId, payload.file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const deleteAttachmentMutation = useMutation({
    mutationFn: (attachmentId: string) => deleteAttachment(attachmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const addLinkMutation = useMutation({
    mutationFn: (payload: { paperId: string; label?: string; url: string }) =>
      addPaperLink(payload.paperId, { label: payload.label, url: payload.url }),
    onSuccess: () => {
      setLinkLabelInput('')
      setLinkUrlInput('')
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
    },
  })

  const deleteLinkMutation = useMutation({
    mutationFn: (linkId: number) => deletePaperLink(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', paperId] })
    },
  })

  const addRelationMutation = useMutation({
    mutationFn: (payload: { target_paper_id: string; relation_type: RelationType; note?: string }) =>
      addPaperRelation(paperId!, payload),
    onSuccess: () => {
      setRelationNoteInput('')
      queryClient.invalidateQueries({ queryKey: ['paper-relations', paperId] })
      queryClient.invalidateQueries({ queryKey: ['paper-relation-candidates', paperId] })
    },
  })

  const deleteRelationMutation = useMutation({
    mutationFn: (relationId: number) => deletePaperRelation(relationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-relations', paperId] })
      queryClient.invalidateQueries({ queryKey: ['paper-relation-candidates', paperId] })
    },
  })

  const reviews = reviewsQuery.data || []
  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }),
    [],
  )

  useEffect(() => {
    if (!editingReviewId) return
    const current = reviews.find((item) => item.id === editingReviewId)
    if (!current) {
      setEditingReviewId(null)
      setEditingReviewText('')
    }
  }, [editingReviewId, reviews])

  useEffect(() => {
    if (!paperQuery.data) {
      setTagsInput('')
      setTitleInput('')
      setSummaryInput('')
      return
    }
    setTagsInput(paperQuery.data.tags.map((item) => item.name).join(', '))
    setTitleInput(paperQuery.data.title || '')
    setSummaryInput(paperQuery.data.summary || paperQuery.data.abstract || '')
  }, [paperQuery.data?.id, paperQuery.data?.tags, paperQuery.data?.title, paperQuery.data?.summary, paperQuery.data?.abstract])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setRelationSearchQuery(relationSearchInput.trim())
    }, 300)
    return () => {
      window.clearTimeout(timer)
    }
  }, [relationSearchInput])

  const beginEditReview = (reviewId: string, text: string) => {
    setEditingReviewId(reviewId)
    setEditingReviewText(text)
  }

  if (!paperId) return <p>Missing paper id.</p>
  if (paperQuery.isLoading) return <p>Loading paper…</p>
  if (!paperQuery.data) return <p>Paper not found.</p>

  const paper = paperQuery.data
  const dedupedTags = parseTagsInput(tagsInput)
  const tagInputState = useMemo(
    () => splitTagInputForSuggestions(tagsInput),
    [tagsInput],
  )
  const tagSuggestions = useMemo(() => {
    const catalog = tagsCatalogQuery.data || []
    if (catalog.length === 0) return []
    const committed = new Set(tagInputState.committedTags.map((item) => item.toLowerCase()))
    const term = tagInputState.searchTerm.toLowerCase()
    return catalog
      .map((item) => item.name)
      .filter((name) => !committed.has(name.toLowerCase()))
      .filter((name) => (term ? name.toLowerCase().includes(term) : true))
      .sort((left, right) => {
        const leftLower = left.toLowerCase()
        const rightLower = right.toLowerCase()
        const leftPrefix = term ? (leftLower.startsWith(term) ? 0 : 1) : 0
        const rightPrefix = term ? (rightLower.startsWith(term) ? 0 : 1) : 0
        if (leftPrefix !== rightPrefix) return leftPrefix - rightPrefix
        return leftLower.localeCompare(rightLower)
      })
      .slice(0, 8)
  }, [tagInputState.committedTags, tagInputState.searchTerm, tagsCatalogQuery.data])
  const currentTagKey = paper.tags.map((item) => item.name.trim().toLowerCase()).sort().join('|')
  const draftTagKey = dedupedTags.map((item) => item.toLowerCase()).sort().join('|')
  const tagsChanged = currentTagKey !== draftTagKey
  const normalizedCurrentTitle = (paper.title || '').trim()
  const normalizedDraftTitle = titleInput.trim()
  const normalizedCurrentSummary = (paper.summary || '').trim()
  const normalizedDraftSummary = summaryInput.trim()
  const metadataChanged = normalizedCurrentTitle !== normalizedDraftTitle
    || normalizedCurrentSummary !== normalizedDraftSummary
  const sortedAttachments = [...paper.attachments].sort(
    (left, right) => new Date(left.imported_at).getTime() - new Date(right.imported_at).getTime(),
  )
  const mainAttachment = sortedAttachments[0] || null
  const supplementalAttachments = sortedAttachments.slice(1)
  const formatFileSize = (size: number) => {
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }
  const relationGroups = relationsQuery.data || { cites: [], cited_by: [], related: [] }
  const relationCandidates = relationCandidatesQuery.data || []

  return (
    <section className="detail-grid">
      <div className="panel full-span">
        <Link to="/" className="link-button secondary-link">Back to Library</Link>
        <h1>{paper.title || 'Untitled'}</h1>
        <label htmlFor="detail-title-input">Title</label>
        <input
          id="detail-title-input"
          name="detail_title_input"
          autoComplete="off"
          type="text"
          placeholder="Paper title…"
          value={titleInput}
          onChange={(e) => setTitleInput(e.target.value)}
        />
        <label htmlFor="detail-summary-input">Summary</label>
        <textarea
          id="detail-summary-input"
          name="detail_summary_input"
          autoComplete="off"
          placeholder="e.g., key idea, method, and findings…"
          value={summaryInput}
          onChange={(e) => setSummaryInput(e.target.value)}
          rows={6}
        />
        <button
          className="secondary"
          disabled={!normalizedDraftTitle || !metadataChanged || updateMetadataMutation.isPending}
          onClick={() =>
            updateMetadataMutation.mutate({
              paperId: paper.id,
              title: normalizedDraftTitle,
              summary: normalizedDraftSummary,
            })
          }
        >
          Save Title & Summary
        </button>
        {updateMetadataMutation.isPending ? <p aria-live="polite">Saving metadata…</p> : null}
        {updateMetadataMutation.isError ? <p aria-live="polite">Failed to save metadata.</p> : null}
        <div className="section-card">
          <div className="section-header">
            <h2 className="section-title">Tags</h2>
            <button
              className="section-toggle"
              aria-label={isTagsOpen ? 'Collapse tags' : 'Expand tags'}
              aria-expanded={isTagsOpen}
              aria-controls="detail-tags-panel"
              onClick={() => setIsTagsOpen((value) => !value)}
            >
              {isTagsOpen ? '−' : '+'}
            </button>
          </div>
          {paper.tags.length > 0 ? (
            <div className="meta-chips">
              {paper.tags.map((tag) => (
                <span key={tag.id} className="chip">#{tag.name}</span>
              ))}
            </div>
          ) : (
            <p className="meta-row">No tags yet.</p>
          )}
          {isTagsOpen ? (
            <div id="detail-tags-panel">
              <label htmlFor="detail-paper-tags-input">Comma-separated tags (supports `,` `，` `;` `；`)</label>
              <input
                id="detail-paper-tags-input"
                name="detail_paper_tags_input"
                autoComplete="off"
                type="text"
                placeholder="nlp, survey, baseline…"
                value={tagsInput}
                onChange={(e) => {
                  setTagsInput(e.target.value)
                  setTagSuggestOpen(true)
                }}
                onFocus={() => setTagSuggestOpen(true)}
                onBlur={() => {
                  window.setTimeout(() => setTagSuggestOpen(false), 100)
                }}
              />
              {tagSuggestOpen && tagSuggestions.length > 0 ? (
                <div className="tag-suggest-panel" role="listbox" aria-label="Tag suggestions">
                  {tagSuggestions.map((name) => (
                    <button
                      key={name}
                      type="button"
                      className="tag-suggest-item"
                      onMouseDown={(event) => {
                        event.preventDefault()
                        setTagsInput(applyTagSuggestion(tagsInput, name))
                        setTagSuggestOpen(true)
                      }}
                    >
                      #{name}
                    </button>
                  ))}
                </div>
              ) : null}
              <button
                className="secondary"
                disabled={!tagsChanged || updateTagsMutation.isPending}
                onClick={() =>
                  updateTagsMutation.mutate({
                    paperId: paper.id,
                    tags: dedupedTags,
                  })
                }
              >
                Save Tags
              </button>
              {updateTagsMutation.isPending ? <p aria-live="polite">Saving tags…</p> : null}
              {updateTagsMutation.isError ? <p aria-live="polite">Failed to save tags.</p> : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel full-span">
        <h2 className="section-title">Open Options</h2>
        {mainAttachment ? (
          <div className="row open-options-row">
            <button onClick={() => openAttachment(mainAttachment.id, 'preview')}>Open Main PDF in Preview</button>
            <a className="link-button" href={attachmentUrl(mainAttachment.id)} target="_blank" rel="noreferrer">
              Open Main PDF in Browser
            </a>
            <button
              className="danger"
              onClick={() => {
                const ok = window.confirm('Delete this paper and all notes?')
                if (!ok) return
                deletePaperMutation.mutate(paper.id)
              }}
            >
              Delete Paper
            </button>
          </div>
        ) : (
          <div className="row open-options-row">
            <p className="meta-row">No main PDF found.</p>
            <button
              className="danger"
              onClick={() => {
                const ok = window.confirm('Delete this paper and all notes?')
                if (!ok) return
                deletePaperMutation.mutate(paper.id)
              }}
            >
              Delete Paper
            </button>
          </div>
        )}
      </div>

      <div className="panel full-span">
        <h2 className="section-title">Original Metadata (Read-only)</h2>
        <h3 className="section-title">Original Title</h3>
        <p className="review-body">{paper.original_title || 'No original title extracted.'}</p>
        <h3 className="section-title">Original Abstract</h3>
        <p className="review-body">{paper.abstract || 'No abstract extracted yet.'}</p>
      </div>

      <div className="panel full-span">
        <div className="section-header">
          <h2 className="section-title">Linked Papers</h2>
          <button
            className="help-toggle"
            aria-label={isRelationScoreHelpOpen ? 'Hide score explanation' : 'Show score explanation'}
            aria-expanded={isRelationScoreHelpOpen}
            onClick={() => setIsRelationScoreHelpOpen((value) => !value)}
          >
            ?
          </button>
        </div>
        {isRelationScoreHelpOpen ? (
          <div className="score-help-box">
            <p className="meta-row">
              Score uses weighted text similarity based on title and abstract, with values from 0 to 100.
            </p>
            <p className="meta-row">
              Search mode (with keywords): title 70% + abstract 30%.
            </p>
            <p className="meta-row">
              Auto mode (Top 10): title 65% + abstract 25% + combined text 10%.
            </p>
            <p className="meta-row">
              Similarity uses RapidFuzz matching and candidates below threshold are filtered out.
            </p>
          </div>
        ) : null}
        {paper.status !== 'confirmed' ? (
          <p className="meta-row">Linked papers are available only for confirmed papers.</p>
        ) : (
          <>
            <div className="linked-groups">
              <div className="section-card linked-group">
                <h3 className="linked-title">Cites ({relationGroups.cites.length})</h3>
                <div className="list">
                  {relationGroups.cites.length === 0 ? (
                    <p className="meta-row">No cited papers.</p>
                  ) : (
                    relationGroups.cites.map((item) => (
                      <article key={item.relation_id} className="review-item relation-item">
                        <p className="review-body">
                          <Link to={`/papers/${item.peer_paper_id}`}>
                            {item.peer_title || 'Untitled'}
                          </Link>
                          {item.peer_year ? ` (${item.peer_year})` : ''}
                        </p>
                        {item.note ? <p className="meta-row relation-note">{item.note}</p> : null}
                        <div className="row wrap-row review-actions">
                          <button
                            className="danger"
                            disabled={deleteRelationMutation.isPending}
                            onClick={() => deleteRelationMutation.mutate(item.relation_id)}
                          >
                            Remove
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </div>

              <div className="section-card linked-group">
                <h3 className="linked-title">Cited by ({relationGroups.cited_by.length})</h3>
                <div className="list">
                  {relationGroups.cited_by.length === 0 ? (
                    <p className="meta-row">No incoming citations.</p>
                  ) : (
                    relationGroups.cited_by.map((item) => (
                      <article key={item.relation_id} className="review-item relation-item">
                        <p className="review-body">
                          <Link to={`/papers/${item.peer_paper_id}`}>
                            {item.peer_title || 'Untitled'}
                          </Link>
                          {item.peer_year ? ` (${item.peer_year})` : ''}
                        </p>
                        {item.note ? <p className="meta-row relation-note">{item.note}</p> : null}
                        <div className="row wrap-row review-actions">
                          <span className="read-only-badge">Read only</span>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </div>

              <div className="section-card linked-group">
                <h3 className="linked-title">Related ({relationGroups.related.length})</h3>
                <div className="list">
                  {relationGroups.related.length === 0 ? (
                    <p className="meta-row">No related papers.</p>
                  ) : (
                    relationGroups.related.map((item) => (
                      <article key={item.relation_id} className="review-item relation-item">
                        <p className="review-body">
                          <Link to={`/papers/${item.peer_paper_id}`}>
                            {item.peer_title || 'Untitled'}
                          </Link>
                          {item.peer_year ? ` (${item.peer_year})` : ''}
                        </p>
                        {item.note ? <p className="meta-row relation-note">{item.note}</p> : null}
                        <div className="row wrap-row review-actions">
                          <button
                            className="danger"
                            disabled={deleteRelationMutation.isPending}
                            onClick={() => deleteRelationMutation.mutate(item.relation_id)}
                          >
                            Remove
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="section-card relation-add-panel">
              <h3 className="linked-title">Add Relation</h3>
              <div className="relation-form-grid">
                <label htmlFor="relation-type-select">
                  Relation Type
                  <select
                    id="relation-type-select"
                    value={relationTypeInput}
                    onChange={(e) => setRelationTypeInput(e.target.value as RelationType)}
                  >
                    <option value="related">related</option>
                    <option value="cite">cite</option>
                  </select>
                </label>

                <label htmlFor="relation-note-input">
                  Note (optional)
                  <input
                    id="relation-note-input"
                    name="relation_note_input"
                    autoComplete="off"
                    maxLength={500}
                    placeholder="Why this relation matters…"
                    value={relationNoteInput}
                    onChange={(e) => setRelationNoteInput(e.target.value)}
                  />
                </label>

                <label htmlFor="relation-search-input">
                  Search Candidates
                  <input
                    id="relation-search-input"
                    name="relation_search_input"
                    autoComplete="off"
                    placeholder="e.g., causal inference, kernel methods…"
                    value={relationSearchInput}
                    onChange={(e) => setRelationSearchInput(e.target.value)}
                  />
                </label>
              </div>

              {relationCandidatesQuery.isLoading ? <p aria-live="polite">Loading candidates…</p> : null}
              {relationCandidatesQuery.isError ? <p aria-live="polite">Failed to load candidates.</p> : null}

              <div className="list relation-candidate-list">
                {relationCandidates.length === 0 ? (
                  <p className="meta-row">No candidates found.</p>
                ) : (
                  relationCandidates.map((candidate) => {
                    const alreadyLinked = candidate.existing_types.includes(relationTypeInput)
                    return (
                      <article key={candidate.paper_id} className="review-item relation-candidate-item">
                        <p className="review-body">
                          <Link to={`/papers/${candidate.paper_id}`}>
                            {candidate.title || 'Untitled'}
                          </Link>
                          {candidate.year ? ` (${candidate.year})` : ''}
                        </p>
                        {candidate.snippet ? <p className="meta-row relation-note">{candidate.snippet}</p> : null}
                        <div className="row wrap-row review-actions">
                          {typeof candidate.score === 'number' ? (
                            <small>Score {candidate.score.toFixed(2)}</small>
                          ) : null}
                          {candidate.existing_types.length > 0 ? (
                            <div className="meta-chips">
                              {candidate.existing_types.map((typeName) => (
                                <span key={`${candidate.paper_id}-${typeName}`} className="chip">
                                  exists: {typeName}
                                </span>
                              ))}
                            </div>
                          ) : null}
                          <button
                            className="secondary"
                            disabled={alreadyLinked || addRelationMutation.isPending}
                            onClick={() =>
                              addRelationMutation.mutate({
                                target_paper_id: candidate.paper_id,
                                relation_type: relationTypeInput,
                                note: relationNoteInput.trim() || undefined,
                              })
                            }
                          >
                            {alreadyLinked ? `Already ${relationTypeInput}` : `Add ${relationTypeInput}`}
                          </button>
                        </div>
                      </article>
                    )
                  })
                )}
              </div>

              {addRelationMutation.isError ? <p aria-live="polite">Failed to add relation.</p> : null}
            </div>
          </>
        )}
      </div>

      <div className="panel full-span">
        <h2>Notes</h2>
        <label htmlFor="paper-review-input">Add a New Note</label>
        <textarea
          id="paper-review-input"
          name="paper_review_text"
          autoComplete="off"
          value={reviewText}
          onChange={(e) => setReviewText(e.target.value)}
          rows={5}
        />
        <button disabled={!reviewText.trim() || reviewMutation.isPending} onClick={() => reviewMutation.mutate()}>Add Note</button>

        <div className="list review-list">
          {reviews.length === 0 ? (
            <p className="meta-row">No notes yet.</p>
          ) : (
            reviews.map((review) => {
              const isEditing = editingReviewId === review.id
              const draftText = isEditing ? editingReviewText : review.note_text
              const changed = draftText.trim() !== review.note_text.trim()
              return (
                <article key={review.id} className="review-item">
                  {isEditing ? (
                    <textarea
                      value={editingReviewText}
                      onChange={(e) => setEditingReviewText(e.target.value)}
                      rows={4}
                      autoFocus
                    />
                  ) : (
                    <p className="review-body">{review.note_text}</p>
                  )}
                  <div className="row wrap-row review-actions">
                    {isEditing ? (
                      <>
                        <button
                          className="secondary"
                          disabled={!editingReviewText.trim() || !changed || updateReviewMutation.isPending}
                          onClick={() =>
                            updateReviewMutation.mutate({
                              reviewId: review.id,
                              noteText: editingReviewText.trim(),
                            })
                          }
                        >
                          Save
                        </button>
                        <button
                          className="secondary"
                          onClick={() => {
                            setEditingReviewId(null)
                            setEditingReviewText('')
                          }}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        className="secondary"
                        onClick={() => beginEditReview(review.id, review.note_text)}
                      >
                        Edit
                      </button>
                    )}
                    <button
                      className="danger"
                      disabled={deleteReviewMutation.isPending}
                      onClick={() => {
                        const ok = window.confirm('Delete this note?')
                        if (!ok) return
                        deleteReviewMutation.mutate(review.id)
                      }}
                    >
                      Delete
                    </button>
                    <small>{dateFormatter.format(new Date(review.updated_at))}</small>
                  </div>
                </article>
              )
            })
          )}
        </div>
      </div>

      <div className="panel full-span">
        <div className="section-header">
          <h2 className="section-title">Supplemental Files</h2>
          <button
            className="section-toggle"
            aria-label={isSupplementalOpen ? 'Collapse supplemental files' : 'Expand supplemental files'}
            aria-expanded={isSupplementalOpen}
            aria-controls="detail-supplemental-panel"
            onClick={() => setIsSupplementalOpen((value) => !value)}
          >
            {isSupplementalOpen ? '−' : '+'}
          </button>
        </div>
        {isSupplementalOpen ? (
          <div id="detail-supplemental-panel">
            <p className="meta-row">The first uploaded file is treated as the main paper body.</p>
            <label htmlFor="detail-extra-attachment-input">Upload supplemental file</label>
            <input
              id="detail-extra-attachment-input"
              name="detail_extra_attachment_input"
              type="file"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (!file) return
                uploadAttachmentMutation.mutate({ paperId: paper.id, file })
                e.currentTarget.value = ''
              }}
            />
            {uploadAttachmentMutation.isPending ? <p aria-live="polite">Uploading file…</p> : null}
            {uploadAttachmentMutation.isError ? <p aria-live="polite">Upload failed. Please try again.</p> : null}
            <div className="list file-list">
              {supplementalAttachments.length === 0 ? (
                <p className="meta-row">No supplemental files yet.</p>
              ) : (
                supplementalAttachments.map((attachment) => (
                  <article key={attachment.id} className="review-item">
                    <p className="review-body">{attachment.original_filename}</p>
                    <div className="row wrap-row review-actions">
                      <button
                        className="secondary"
                        onClick={() => openAttachment(attachment.id, 'preview')}
                      >
                        Open
                      </button>
                      <a
                        className="link-button secondary-link"
                        href={attachmentUrl(attachment.id)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Download
                      </a>
                      <button
                        className="danger"
                        disabled={deleteAttachmentMutation.isPending}
                        onClick={() => {
                          const ok = window.confirm('Delete this supplemental file?')
                          if (!ok) return
                          deleteAttachmentMutation.mutate(attachment.id)
                        }}
                      >
                        Delete
                      </button>
                      <small>{formatFileSize(attachment.file_size)}</small>
                    </div>
                  </article>
                ))
              )}
            </div>
            {deleteAttachmentMutation.isError ? <p aria-live="polite">Failed to delete file.</p> : null}
          </div>
        ) : null}
      </div>

      <div className="panel full-span">
        <div className="section-header">
          <h2 className="section-title">Links</h2>
          <button
            className="section-toggle"
            aria-label={isLinksOpen ? 'Collapse links' : 'Expand links'}
            aria-expanded={isLinksOpen}
            aria-controls="detail-links-panel"
            onClick={() => setIsLinksOpen((value) => !value)}
          >
            {isLinksOpen ? '−' : '+'}
          </button>
        </div>
        {isLinksOpen ? (
          <div id="detail-links-panel">
            <label htmlFor="detail-paper-link-label">Link Label (Optional)</label>
            <input
              id="detail-paper-link-label"
              name="detail_paper_link_label"
              autoComplete="off"
              type="text"
              placeholder="GitHub, Project Page…"
              value={linkLabelInput}
              onChange={(e) => setLinkLabelInput(e.target.value)}
            />
            <label htmlFor="detail-paper-link-url">URL</label>
            <input
              id="detail-paper-link-url"
              name="detail_paper_link_url"
              autoComplete="off"
              type="url"
              inputMode="url"
              placeholder="https://github.com/org/repo…"
              value={linkUrlInput}
              onChange={(e) => setLinkUrlInput(e.target.value)}
            />
            <button
              className="secondary"
              disabled={!linkUrlInput.trim() || addLinkMutation.isPending}
              onClick={() =>
                addLinkMutation.mutate({
                  paperId: paper.id,
                  label: linkLabelInput.trim() || undefined,
                  url: linkUrlInput.trim(),
                })
              }
            >
              Add Link
            </button>
            {addLinkMutation.isError ? <p aria-live="polite">Failed to add link. Use a valid URL.</p> : null}
            <div className="list link-list">
              {paper.links.length === 0 ? (
                <p className="meta-row">No links yet.</p>
              ) : (
                paper.links.map((link) => (
                  <article key={link.id} className="review-item">
                    <p className="review-body">
                      {link.label ? `${link.label}: ` : ''}
                      <a href={link.url} target="_blank" rel="noreferrer">{link.url}</a>
                    </p>
                    <div className="row wrap-row review-actions">
                      <button
                        className="danger"
                        disabled={deleteLinkMutation.isPending}
                        onClick={() => deleteLinkMutation.mutate(link.id)}
                      >
                        Remove Link
                      </button>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}
