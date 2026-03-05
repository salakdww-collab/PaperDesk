import { parseTagsInput } from './tag-utils'

const TAG_SEPARATORS = /[\n\r,，;；]/

export function splitTagInputForSuggestions(raw: string): {
  committedTags: string[]
  searchTerm: string
} {
  let lastSeparatorIndex = -1
  for (let index = raw.length - 1; index >= 0; index -= 1) {
    if (TAG_SEPARATORS.test(raw[index])) {
      lastSeparatorIndex = index
      break
    }
  }

  if (lastSeparatorIndex < 0) {
    return { committedTags: [], searchTerm: raw.trim() }
  }

  const committedRaw = raw.slice(0, lastSeparatorIndex + 1)
  const searchRaw = raw.slice(lastSeparatorIndex + 1)
  return {
    committedTags: parseTagsInput(committedRaw),
    searchTerm: searchRaw.trim(),
  }
}

export function applyTagSuggestion(raw: string, selectedTag: string): string {
  const { committedTags } = splitTagInputForSuggestions(raw)
  const existing = new Set(committedTags.map((item) => item.toLowerCase()))
  const nextTags = [...committedTags]

  if (!existing.has(selectedTag.toLowerCase())) {
    nextTags.push(selectedTag)
  }

  return `${nextTags.join(', ')}${nextTags.length > 0 ? ', ' : ''}`
}
