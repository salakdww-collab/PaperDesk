export function parseTagsInput(raw: string): string[] {
  const seen = new Set<string>()
  const tags: string[] = []

  for (const part of raw.split(/[\n\r,，;；]+/)) {
    const value = part.trim()
    if (!value) continue
    const key = value.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    tags.push(value)
  }

  return tags
}
