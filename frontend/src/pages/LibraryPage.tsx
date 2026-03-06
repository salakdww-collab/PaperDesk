import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import {
  addReview,
  attachmentUrl,
  bibtexExportUrl,
  confirmPaper,
  deletePaper,
  deleteReview,
  fetchPaper,
  fetchPapers,
  fetchReviews,
  fetchTags,
  openExternalUrl,
  openAttachment,
  searchPapers,
  updatePaper,
  updateReview,
  uploadPdf,
} from '../lib/api'
import { applyTagSuggestion, splitTagInputForSuggestions } from '../lib/tag-suggestions'
import { parseTagsInput } from '../lib/tag-utils'

interface DraftState {
  draftId: string
  title: string
  originalTitle: string
  summary: string
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function findAcronymRange(text: string, acronym: string): [number, number] | null {
  const wordRegex = /[A-Za-z0-9]+/g
  const words: Array<{ start: number; end: number; initial: string }> = []
  let match = wordRegex.exec(text)

  while (match) {
    words.push({
      start: match.index,
      end: match.index + match[0].length,
      initial: match[0][0].toUpperCase(),
    })
    match = wordRegex.exec(text)
  }

  if (words.length < acronym.length) return null

  for (let index = 0; index <= words.length - acronym.length; index += 1) {
    const initials = words
      .slice(index, index + acronym.length)
      .map((item) => item.initial)
      .join('')
    if (initials === acronym) {
      return [words[index].start, words[index + acronym.length - 1].end]
    }
  }

  return null
}

function highlightMatch(text: string, query: string): ReactNode {
  const normalizedText = text || ''
  const normalizedQuery = query.trim()
  if (!normalizedQuery) return normalizedText

  const acronym = normalizedQuery.replace(/[^A-Za-z0-9]/g, '').toUpperCase()
  if (/^[A-Z0-9]{2,10}$/.test(acronym) && !normalizedQuery.includes(' ')) {
    const acronymRange = findAcronymRange(normalizedText, acronym)
    if (acronymRange) {
      const [start, end] = acronymRange
      return (
        <>
          {normalizedText.slice(0, start)}
          <mark>{normalizedText.slice(start, end)}</mark>
          {normalizedText.slice(end)}
        </>
      )
    }
  }

  const tokens = normalizedQuery.split(/\s+/).filter(Boolean)
  if (tokens.length === 0) return normalizedText

  const pattern = new RegExp(`(${tokens.map((item) => escapeRegExp(item)).join('|')})`, 'ig')
  const tokenSet = new Set(tokens.map((item) => item.toLowerCase()))
  const parts = normalizedText.split(pattern)

  return (
    <>
      {parts.map((part, index) =>
        tokenSet.has(part.toLowerCase()) ? (
          <mark key={`${part}-${index}`}>{part}</mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        ),
      )}
    </>
  )
}

function estimatePillWidth(label: string) {
  const approxCharWidth = 7.4
  return Math.ceil(label.length * approxCharWidth) + 30
}

function normalizeDraftAbstract(raw: string | undefined): string {
  if (!raw) return ''
  const compact = raw
    .replace(/\r\n/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  if (compact.length <= 4000) return compact
  return `${compact.slice(0, 4000)}…`
}

export function LibraryPage() {
  const ALL_LIBRARY_TAG = '__all__'
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [draft, setDraft] = useState<DraftState | null>(null)
  const [reviewText, setReviewText] = useState('')
  const [editingReviewId, setEditingReviewId] = useState<string | null>(null)
  const [editingReviewText, setEditingReviewText] = useState('')
  const [tagsInput, setTagsInput] = useState('')
  const [isTagsOpen, setIsTagsOpen] = useState(false)
  const [activeLibraryTag, setActiveLibraryTag] = useState(ALL_LIBRARY_TAG)
  const [librarySort, setLibrarySort] = useState<'updated_desc' | 'updated_asc' | 'year_desc' | 'year_asc' | 'title_asc'>('updated_desc')
  const [showAllLibraryTags, setShowAllLibraryTags] = useState(false)
  const [visibleLibraryTags, setVisibleLibraryTags] = useState<string[]>([])
  const [tagSuggestOpen, setTagSuggestOpen] = useState(false)
  const [isPdfDragActive, setIsPdfDragActive] = useState(false)
  const [dragDepth, setDragDepth] = useState(0)
  const [uploadErrorMessage, setUploadErrorMessage] = useState<string | null>(null)
  const [selectedPaperIds, setSelectedPaperIds] = useState<string[]>([])
  const [exportErrorMessage, setExportErrorMessage] = useState<string | null>(null)
  const libraryFilterPrimaryRef = useRef<HTMLDivElement | null>(null)
  const librarySortLabelRef = useRef<HTMLLabelElement | null>(null)

  const query = searchParams.get('q') || ''
  const selectedPaperId = searchParams.get('paper')

  const updateParams = (updates: { q?: string | null; paper?: string | null }) => {
    const next = new URLSearchParams(searchParams)

    if (updates.q !== undefined) {
      const value = updates.q || ''
      if (value) {
        next.set('q', value)
      } else {
        next.delete('q')
      }
    }

    if (updates.paper !== undefined) {
      if (updates.paper) {
        next.set('paper', updates.paper)
      } else {
        next.delete('paper')
      }
    }

    setSearchParams(next, { replace: true })
  }

  const papersQuery = useQuery({
    queryKey: ['papers', query],
    queryFn: () => fetchPapers({ q: query || undefined, page_size: 50 }),
  })

  const searchQuery = useQuery({
    queryKey: ['search', query],
    queryFn: () => searchPapers(query),
    enabled: query.trim().length > 0,
  })

  const reviewsQuery = useQuery({
    queryKey: ['reviews', selectedPaperId],
    queryFn: () => fetchReviews(selectedPaperId!),
    enabled: Boolean(selectedPaperId),
  })

  const selectedPaperQuery = useQuery({
    queryKey: ['paper', selectedPaperId],
    queryFn: () => fetchPaper(selectedPaperId!),
    enabled: Boolean(selectedPaperId),
  })

  const tagsCatalogQuery = useQuery({
    queryKey: ['tags-catalog'],
    queryFn: fetchTags,
  })

  const uploadMutation = useMutation({
    mutationFn: uploadPdf,
    onSuccess: (data) => {
      setUploadErrorMessage(null)
      setDraft({
        draftId: data.paper_draft_id,
        title: data.metadata_candidate.title || '',
        originalTitle: data.metadata_candidate.title || '',
        summary: normalizeDraftAbstract(data.metadata_candidate.abstract),
      })
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail
      setUploadErrorMessage(typeof detail === 'string' ? detail : 'Upload failed. Please try again.')
    },
  })

  const confirmMutation = useMutation({
    mutationFn: confirmPaper,
    onSuccess: () => {
      setDraft(null)
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const addReviewMutation = useMutation({
    mutationFn: () => addReview(selectedPaperId!, { note_text: reviewText }),
    onSuccess: () => {
      setReviewText('')
      queryClient.invalidateQueries({ queryKey: ['reviews', selectedPaperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const updateReviewMutation = useMutation({
    mutationFn: (payload: { reviewId: string; noteText: string }) =>
      updateReview(payload.reviewId, { note_text: payload.noteText }),
    onSuccess: () => {
      setEditingReviewId(null)
      setEditingReviewText('')
      queryClient.invalidateQueries({ queryKey: ['reviews', selectedPaperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const deleteReviewMutation = useMutation({
    mutationFn: (reviewId: string) => deleteReview(reviewId),
    onSuccess: (_, reviewId) => {
      if (editingReviewId === reviewId) {
        setEditingReviewId(null)
        setEditingReviewText('')
      }
      queryClient.invalidateQueries({ queryKey: ['reviews', selectedPaperId] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
    },
  })

  const deletePaperMutation = useMutation({
    mutationFn: (paperId: string) => deletePaper(paperId),
    onSuccess: (_, paperId) => {
      if (selectedPaperId === paperId) {
        updateParams({ paper: null })
      }
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['search'] })
      queryClient.invalidateQueries({ queryKey: ['reviews'] })
    },
  })

  const updateTagsMutation = useMutation({
    mutationFn: (payload: { paperId: string; tags: string[] }) =>
      updatePaper(payload.paperId, { tags: payload.tags }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['papers'] })
      queryClient.invalidateQueries({ queryKey: ['paper', selectedPaperId] })
    },
  })

  const exportBibtexMutation = useMutation({
    mutationFn: (paperIds: string[]) => openExternalUrl(bibtexExportUrl(paperIds)),
    onSuccess: () => {
      setExportErrorMessage(null)
    },
    onError: () => {
      setExportErrorMessage('Failed to export BibTeX. Please check selected papers and try again.')
    },
  })

  const selectedPaper = useMemo(() => {
    if (selectedPaperQuery.data) return selectedPaperQuery.data
    return (papersQuery.data?.items || []).find((paper) => paper.id === selectedPaperId) || null
  }, [papersQuery.data, selectedPaperId, selectedPaperQuery.data])

  const items = papersQuery.data?.items || []
  const reviews = reviewsQuery.data || []
  const searchItems = useMemo(() => searchQuery.data?.items || [], [searchQuery.data])
  const showSearchEmpty = query && !searchQuery.isFetching && searchItems.length === 0
  const numberFormatter = useMemo(() => new Intl.NumberFormat(), [])
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
    if (!selectedPaper) {
      setTagsInput('')
      return
    }
    setTagsInput(selectedPaper.tags.map((item) => item.name).join(', '))
  }, [selectedPaper?.id, selectedPaper?.tags])

  const beginEditReview = (reviewId: string, text: string) => {
    setEditingReviewId(reviewId)
    setEditingReviewText(text)
  }

  const handleImportFile = (file?: File | null) => {
    if (!file) return
    const name = file.name.toLowerCase()
    const isPdf = name.endsWith('.pdf') || file.type === 'application/pdf'
    if (!isPdf) {
      setUploadErrorMessage('Only PDF files are supported.')
      return
    }
    setUploadErrorMessage(null)
    uploadMutation.mutate(file)
  }

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragDepth((value) => value + 1)
    setIsPdfDragActive(true)
  }

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragDepth((value) => {
      const next = Math.max(0, value - 1)
      if (next === 0) setIsPdfDragActive(false)
      return next
    })
  }

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    if (!isPdfDragActive) setIsPdfDragActive(true)
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setDragDepth(0)
    setIsPdfDragActive(false)
    const file = event.dataTransfer.files?.[0]
    handleImportFile(file)
  }

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
  const currentTagKey = selectedPaper
    ? selectedPaper.tags.map((item) => item.name.trim().toLowerCase()).sort().join('|')
    : ''
  const draftTagKey = dedupedTags.map((item) => item.toLowerCase()).sort().join('|')
  const tagsChanged = currentTagKey !== draftTagKey
  const sortedAttachments = selectedPaper
    ? [...selectedPaper.attachments].sort(
        (left, right) => new Date(left.imported_at).getTime() - new Date(right.imported_at).getTime(),
      )
    : []
  const mainAttachment = sortedAttachments[0] || null
  const summaryLabel = 'Summary'
  const libraryTagRanking = useMemo(() => {
    const counts = new Map<string, number>()
    for (const paper of items) {
      const perPaper = new Set(
        paper.tags.map((tag) => tag.name.trim()).filter(Boolean),
      )
      for (const tagName of perPaper) {
        counts.set(tagName, (counts.get(tagName) || 0) + 1)
      }
    }
    const ranked = Array.from(counts.entries())
      .sort((left, right) => {
        if (left[1] !== right[1]) return right[1] - left[1]
        return left[0].localeCompare(right[0])
      })
      .map(([tagName]) => tagName)
    return { counts, ranked }
  }, [items])
  const availableLibraryTags = libraryTagRanking.ranked
  const extraLibraryTags = useMemo(
    () => availableLibraryTags.filter((tagName) => !visibleLibraryTags.includes(tagName)),
    [availableLibraryTags, visibleLibraryTags],
  )
  const filteredItems = useMemo(() => {
    if (activeLibraryTag === ALL_LIBRARY_TAG) return items
    return items.filter((paper) => paper.tags.some((tag) => tag.name === activeLibraryTag))
  }, [ALL_LIBRARY_TAG, activeLibraryTag, items])
  const sortedFilteredItems = useMemo(() => {
    const rows = [...filteredItems]
    rows.sort((left, right) => {
      if (librarySort === 'updated_asc' || librarySort === 'updated_desc') {
        const leftTime = new Date(left.updated_at).getTime()
        const rightTime = new Date(right.updated_at).getTime()
        return librarySort === 'updated_asc' ? leftTime - rightTime : rightTime - leftTime
      }
      if (librarySort === 'year_asc' || librarySort === 'year_desc') {
        const leftYear = left.year ?? -9999
        const rightYear = right.year ?? -9999
        if (leftYear !== rightYear) {
          return librarySort === 'year_asc' ? leftYear - rightYear : rightYear - leftYear
        }
      }
      return (left.title || '').localeCompare(right.title || '')
    })
    return rows
  }, [filteredItems, librarySort])
  const filteredIdSet = useMemo(() => new Set(sortedFilteredItems.map((paper) => paper.id)), [sortedFilteredItems])
  const selectedCount = selectedPaperIds.length
  const allFilteredSelected = sortedFilteredItems.length > 0
    && sortedFilteredItems.every((paper) => selectedPaperIds.includes(paper.id))
  const selectedIdsInSortOrder = useMemo(
    () => sortedFilteredItems.map((paper) => paper.id).filter((paperId) => selectedPaperIds.includes(paperId)),
    [selectedPaperIds, sortedFilteredItems],
  )
  const selectedPapersInSortOrder = useMemo(
    () => sortedFilteredItems.filter((paper) => selectedPaperIds.includes(paper.id)),
    [selectedPaperIds, sortedFilteredItems],
  )
  const selectedMissingManualBib = useMemo(
    () => selectedPapersInSortOrder.filter((paper) => !paper.bibtex_override?.trim()),
    [selectedPapersInSortOrder],
  )

  const togglePaperSelection = (paperId: string, checked: boolean) => {
    setSelectedPaperIds((current) => {
      if (checked) {
        return current.includes(paperId) ? current : [...current, paperId]
      }
      return current.filter((item) => item !== paperId)
    })
    setExportErrorMessage(null)
  }

  const setAllFilteredSelection = (checked: boolean) => {
    setSelectedPaperIds((current) => {
      if (!checked) {
        return current.filter((paperId) => !filteredIdSet.has(paperId))
      }
      const merged = new Set(current)
      for (const paper of sortedFilteredItems) {
        merged.add(paper.id)
      }
      return Array.from(merged)
    })
    setExportErrorMessage(null)
  }

  useEffect(() => {
    if (activeLibraryTag === ALL_LIBRARY_TAG) return
    if (!availableLibraryTags.includes(activeLibraryTag)) {
      setActiveLibraryTag(ALL_LIBRARY_TAG)
    }
  }, [ALL_LIBRARY_TAG, activeLibraryTag, availableLibraryTags])

  useEffect(() => {
    if (extraLibraryTags.length === 0 && showAllLibraryTags) {
      setShowAllLibraryTags(false)
    }
  }, [extraLibraryTags.length, showAllLibraryTags])

  useEffect(() => {
    setSelectedPaperIds((current) => current.filter((paperId) => filteredIdSet.has(paperId)))
  }, [filteredIdSet])

  useEffect(() => {
    const computeVisibleTags = () => {
      const primary = libraryFilterPrimaryRef.current
      const sortLabel = librarySortLabelRef.current
      if (!primary) {
        setVisibleLibraryTags(availableLibraryTags)
        return
      }

      const containerWidth = primary.clientWidth
      const baseGap = 8
      const allWidth = estimatePillWidth('All')
      const moreWidth = estimatePillWidth('More')
      const tagBudget = Math.max(0, containerWidth - allWidth - baseGap * 3)

      const visible: string[] = []
      let used = 0
      for (let index = 0; index < availableLibraryTags.length; index += 1) {
        const tagName = availableLibraryTags[index]
        const width = estimatePillWidth(`#${tagName}`)
        const remaining = availableLibraryTags.length - index - 1
        const reserveMore = remaining > 0 ? moreWidth + baseGap : 0
        if (used + width + reserveMore <= tagBudget) {
          visible.push(tagName)
          used += width + baseGap
        } else {
          break
        }
      }

      if (availableLibraryTags.length > 0 && visible.length === 0) {
        visible.push(availableLibraryTags[0])
      }

      if (
        activeLibraryTag !== ALL_LIBRARY_TAG
        && availableLibraryTags.includes(activeLibraryTag)
        && !visible.includes(activeLibraryTag)
      ) {
        if (visible.length === 0) {
          visible.push(activeLibraryTag)
        } else {
          visible[visible.length - 1] = activeLibraryTag
        }
      }

      const visibleSet = new Set(visible)
      setVisibleLibraryTags(availableLibraryTags.filter((tagName) => visibleSet.has(tagName)))
    }

    computeVisibleTags()

    let observer: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => computeVisibleTags())
      if (libraryFilterPrimaryRef.current) observer.observe(libraryFilterPrimaryRef.current)
      if (librarySortLabelRef.current) observer.observe(librarySortLabelRef.current)
    }
    window.addEventListener('resize', computeVisibleTags)

    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', computeVisibleTags)
    }
  }, [ALL_LIBRARY_TAG, activeLibraryTag, availableLibraryTags])

  const exportSelectedBibtex = () => {
    if (selectedIdsInSortOrder.length === 0 || exportBibtexMutation.isPending) {
      return
    }
    if (selectedMissingManualBib.length > 0) {
      const preview = selectedMissingManualBib
        .slice(0, 3)
        .map((paper) => paper.title || paper.id)
        .join(', ')
      const suffix = selectedMissingManualBib.length > 3 ? ', ...' : ''
      setExportErrorMessage(`Manual BibTeX required before export: ${preview}${suffix}`)
      return
    }
    setExportErrorMessage(null)
    exportBibtexMutation.mutate(selectedIdsInSortOrder)
  }

  return (
    <section className="page-grid">
      <div className="panel">
        <h2>Import PDF</h2>
        <div
          className={`upload-dropzone ${isPdfDragActive ? 'is-drag-active' : ''}`}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <label htmlFor="pdf-upload">Drag & drop PDF here, or select a file</label>
          <input
            id="pdf-upload"
            name="pdf_upload"
            type="file"
            accept="application/pdf"
            aria-label="Select PDF file"
            onChange={(e) => {
              const file = e.target.files?.[0]
              handleImportFile(file)
              e.currentTarget.value = ''
            }}
          />
        </div>
        {uploadMutation.isPending ? <p aria-live="polite">Uploading…</p> : null}
        {uploadErrorMessage ? <p aria-live="polite">{uploadErrorMessage}</p> : null}
      </div>

      <div className="panel">
        <h2>Search</h2>
        <p className="meta-row">Use keywords in title or abstract.</p>
        <div className="search-row">
          <div className="search-input-wrap">
            <label htmlFor="paper-search" className="sr-only">Search papers</label>
            <input
              id="paper-search"
              name="paper_search"
              autoComplete="off"
              type="text"
              placeholder="Title or abstract…"
              value={query}
              onChange={(e) => updateParams({ q: e.target.value })}
            />
            {query ? (
              <button
                type="button"
                className="icon-button"
                aria-label="Clear search"
                onClick={() => updateParams({ q: null })}
              >
                ×
              </button>
            ) : null}
          </div>
        </div>
        {query ? (
          <p className="meta-row search-status" aria-live="polite">
            {searchQuery.isFetching
              ? 'Searching…'
              : `${numberFormatter.format(searchItems.length)} match${searchItems.length === 1 ? '' : 'es'}`}
          </p>
        ) : null}

        {query && searchItems.length > 0 ? (
          <div className="search-results">
            {searchItems.map((item) => (
              <button
                key={item.paper_id}
                className="search-result-card"
                onClick={() => updateParams({ paper: item.paper_id })}
              >
                <span className="result-title">{highlightMatch(item.title || item.paper_id, query)}</span>
                <span className="result-snippet">{highlightMatch(item.snippet || 'No snippet available.', query)}</span>
                <span className="result-meta">Title/abstract match</span>
              </button>
            ))}
          </div>
        ) : null}

        {showSearchEmpty ? <p aria-live="polite">No results found.</p> : null}
      </div>

      <div className="panel library-panel">
        <h2>Library</h2>
        <div className="library-filter-bar" aria-label="Tag categories">
          <div className="library-filter-primary" ref={libraryFilterPrimaryRef}>
            <button
              type="button"
              className={`tag-filter-btn ${activeLibraryTag === ALL_LIBRARY_TAG ? 'is-active' : ''}`}
              onClick={() => setActiveLibraryTag(ALL_LIBRARY_TAG)}
            >
              All
            </button>
            {visibleLibraryTags.map((tagName) => (
              <button
                key={tagName}
                type="button"
                className={`tag-filter-btn ${activeLibraryTag === tagName ? 'is-active' : ''}`}
                onClick={() => setActiveLibraryTag(tagName)}
              >
                #{tagName}
              </button>
            ))}
            {extraLibraryTags.length > 0 ? (
              <button
                type="button"
                className={`tag-filter-btn library-more-btn ${showAllLibraryTags ? 'is-active' : ''}`}
                onClick={() => setShowAllLibraryTags((value) => !value)}
              >
                {showAllLibraryTags ? 'Less' : 'More'}
              </button>
            ) : null}
          </div>
          <label htmlFor="library-sort" className="library-sort-label" ref={librarySortLabelRef}>
            Sort
            <select
              id="library-sort"
              value={librarySort}
              onChange={(e) => setLibrarySort(e.target.value as typeof librarySort)}
            >
              <option value="updated_desc">Updated (newest)</option>
              <option value="updated_asc">Updated (oldest)</option>
              <option value="year_desc">Year (newest)</option>
              <option value="year_asc">Year (oldest)</option>
              <option value="title_asc">Title (A-Z)</option>
            </select>
          </label>
        </div>
        {showAllLibraryTags && extraLibraryTags.length > 0 ? (
          <div className="library-extra-tags" aria-label="More tag categories">
            {extraLibraryTags.map((tagName) => (
              <button
                key={`extra-${tagName}`}
                type="button"
                className={`tag-filter-btn ${activeLibraryTag === tagName ? 'is-active' : ''}`}
                onClick={() => setActiveLibraryTag(tagName)}
              >
                #{tagName}
              </button>
            ))}
          </div>
        ) : null}
        <div className="library-tools-row">
          <p className="meta-row library-selection-summary">
            Selected: {selectedCount}
          </p>
          <div className="row wrap-row library-actions">
            <button
              type="button"
              className="secondary"
              disabled={sortedFilteredItems.length === 0}
              onClick={() => setAllFilteredSelection(true)}
            >
              Select All (Current Filter)
            </button>
            <button
              type="button"
              className="secondary"
              disabled={selectedCount === 0}
              onClick={() => {
                setSelectedPaperIds([])
                setExportErrorMessage(null)
              }}
            >
              Clear Selection
            </button>
            <button
              type="button"
              disabled={selectedCount === 0 || exportBibtexMutation.isPending || selectedMissingManualBib.length > 0}
              onClick={exportSelectedBibtex}
            >
              {exportBibtexMutation.isPending ? 'Exporting…' : `Export .bib (${selectedCount})`}
            </button>
          </div>
        </div>
        {selectedMissingManualBib.length > 0 ? (
          <div className="missing-bib-panel" aria-live="polite">
            <p className="meta-row">
              {selectedMissingManualBib.length} selected paper{selectedMissingManualBib.length === 1 ? '' : 's'} missing manual BibTeX:
            </p>
            <div className="missing-bib-list">
              {selectedMissingManualBib.map((paper) => (
                <button
                  key={`missing-bib-${paper.id}`}
                  type="button"
                  className="missing-bib-item"
                  onClick={() => updateParams({ paper: paper.id })}
                >
                  {paper.title || paper.id}
                </button>
              ))}
            </div>
          </div>
        ) : null}
        {exportErrorMessage ? <p aria-live="polite">{exportErrorMessage}</p> : null}
        <table className="paper-table">
          <caption className="sr-only">Imported papers</caption>
          <thead>
            <tr>
              <th scope="col" className="select-col">
                <label htmlFor="select-all-papers" className="sr-only">Select all papers in current filter</label>
                <input
                  id="select-all-papers"
                  name="select_all_papers"
                  type="checkbox"
                  checked={allFilteredSelected}
                  aria-label="Select all papers in current filter"
                  onChange={(event) => setAllFilteredSelection(event.target.checked)}
                />
              </th>
              <th scope="col">Title</th>
              <th scope="col">Updated</th>
            </tr>
          </thead>
          <tbody>
            {sortedFilteredItems.length === 0 ? (
              <tr>
                <td colSpan={3}>
                  <p className="meta-row">
                    {items.length === 0
                      ? 'No papers yet. Import your first PDF above.'
                      : 'No papers in this tag category.'}
                  </p>
                </td>
              </tr>
            ) : null}
            {sortedFilteredItems.map((paper) => (
              <tr
                key={paper.id}
                className={`${paper.id === selectedPaperId ? 'is-selected ' : ''}${selectedPaperIds.includes(paper.id) ? 'is-checked' : ''}`.trim() || undefined}
              >
                <td className="select-col">
                  <label htmlFor={`select-paper-${paper.id}`} className="sr-only">
                    Select {paper.title || 'Untitled'}
                  </label>
                  <input
                    id={`select-paper-${paper.id}`}
                    name={`select_paper_${paper.id}`}
                    type="checkbox"
                    checked={selectedPaperIds.includes(paper.id)}
                    onChange={(event) => togglePaperSelection(paper.id, event.target.checked)}
                  />
                </td>
                <td className="title-cell">
                  <div className="library-title-block">
                    <button className="title-button" onClick={() => updateParams({ paper: paper.id })}>
                      {paper.title || 'Untitled'}
                    </button>
                    {paper.year ? <small className="library-row-year">{paper.year}</small> : null}
                    {paper.tags.length > 0 ? (
                      <div className="library-row-tags">
                        {paper.tags.map((tag) => (
                          <span key={`${paper.id}-${tag.id}`} className="library-row-tag">#{tag.name}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </td>
                <td className="meta-cell">
                  <time dateTime={paper.updated_at}>
                    {dateFormatter.format(new Date(paper.updated_at))}
                  </time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel selected-panel">
        <h2>Paper Snapshot</h2>
        {!selectedPaper ? (
          <p>Click a title in Library to view abstract and your notes.</p>
        ) : (
          <div className="selected-paper">
            <h3>{selectedPaper.title || 'Untitled'}</h3>
            <div className="meta-chips">
              {selectedPaper.year ? <span className="chip">{selectedPaper.year}</span> : null}
              {selectedPaper.venue ? <span className="chip">{selectedPaper.venue}</span> : null}
            </div>

            <div className="section-card">
              <div className="section-header">
                <h3 className="section-title">Tags</h3>
                <button
                  className="section-toggle"
                  aria-label={isTagsOpen ? 'Collapse tags' : 'Expand tags'}
                  aria-expanded={isTagsOpen}
                  aria-controls="library-tags-panel"
                  onClick={() => setIsTagsOpen((value) => !value)}
                >
                  {isTagsOpen ? '−' : '+'}
                </button>
              </div>
              {selectedPaper.tags.length > 0 ? (
                <div className="meta-chips">
                  {selectedPaper.tags.map((tag) => (
                    <span key={tag.id} className="chip">#{tag.name}</span>
                  ))}
                </div>
              ) : (
                <p className="meta-row">No tags yet.</p>
              )}
              {isTagsOpen ? (
                <div id="library-tags-panel">
                  <label htmlFor="paper-tags-input">Comma-separated tags (supports `,` `，` `;` `；`)</label>
                  <input
                    id="paper-tags-input"
                    name="paper_tags_input"
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
                        paperId: selectedPaper.id,
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

            <div className="section-card">
              <h3 className="section-title">Open Options</h3>
              {mainAttachment ? (
                <div className="row wrap-row">
                  <button onClick={() => openAttachment(mainAttachment.id, 'preview')}>
                    Open Main PDF in Preview
                  </button>
                  <a
                    className="link-button"
                    href={attachmentUrl(mainAttachment.id)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open Main PDF in Browser
                  </a>
                </div>
              ) : (
                <p>No main PDF found.</p>
              )}
              <div className="row wrap-row">
                <Link className="link-button secondary-link" to={`/papers/${selectedPaper.id}`}>
                  Open Detail Page
                </Link>
                <button
                  className="danger"
                  onClick={() => {
                    const ok = window.confirm('Delete this paper and all notes?')
                    if (!ok) return
                    deletePaperMutation.mutate(selectedPaper.id)
                  }}
                >
                  Delete Paper
                </button>
              </div>
            </div>

            <div className="section-card">
              <h3 className="section-title">{summaryLabel}</h3>
              <p className="review-body">
                {selectedPaper.summary || `No ${summaryLabel.toLowerCase()} yet.`}
              </p>
            </div>

            <div className="section-card">
              <h3 className="section-title">Notes</h3>
              <label htmlFor="review-input">Add a New Note</label>
              <textarea
                id="review-input"
                name="review_text"
                autoComplete="off"
                value={reviewText}
                onChange={(e) => setReviewText(e.target.value)}
                rows={4}
              />
              <button
                disabled={!reviewText.trim() || addReviewMutation.isPending}
                onClick={() => addReviewMutation.mutate()}
              >
                Add Note
              </button>

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

            <p className="meta-row">
              Manage supplemental files and links in the Detail Page.
            </p>
          </div>
        )}
      </div>

      {draft ? (
        <div className="modal" role="dialog" aria-modal="true" aria-labelledby="confirm-title-heading">
          <div className="modal-card">
            <h2 id="confirm-title-heading">Confirm title</h2>
            <label htmlFor="draft-title">Title</label>
            <input
              id="draft-title"
              name="draft_title"
              autoComplete="off"
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
            />
            <label>Original title (read-only)</label>
            <p className="meta-row">{draft.originalTitle || 'No original title extracted.'}</p>
            <label htmlFor="draft-abstract">Summary (optional)</label>
            <textarea
              id="draft-abstract"
              name="draft_abstract"
              autoComplete="off"
              wrap="soft"
              value={draft.summary}
              onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
              rows={6}
            />
            <div className="row">
              <button
                disabled={!draft.title.trim()}
                onClick={() =>
                  confirmMutation.mutate({
                    paper_draft_id: draft.draftId,
                    title: draft.title.trim(),
                    authors: [],
                    summary: draft.summary || undefined,
                    tags: [],
                  })
                }
              >
                Save
              </button>
              <button onClick={() => setDraft(null)} className="secondary">Cancel</button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
