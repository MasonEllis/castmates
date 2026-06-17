<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { searchTitles } from '../api'
import type { TitleHit } from '../types'

const props = defineProps<{
  label: string
  placeholder?: string
  selected: TitleHit | null
}>()

const emit = defineEmits<{
  (e: 'select', hit: TitleHit): void
  (e: 'clear'): void
}>()

const query = ref<string>('')
const hits = ref<TitleHit[]>([])
const open = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const highlightIndex = ref<number>(-1)

const rootRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLElement | null>(null)

let debounceHandle: ReturnType<typeof setTimeout> | null = null
let inflight: AbortController | null = null

const isSelected = computed(() => props.selected !== null)

function formatHit(hit: TitleHit): string {
  const parts = [hit.title]
  if (hit.year) parts.push(`(${hit.year})`)
  return parts.join(' ')
}

function kindLabel(kind: string | null): string {
  if (!kind) return ''
  return kind
    .split(' ')
    .map((w) => (w === 'tv' ? 'TV' : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

function posterInitial(title: string): string {
  const trimmed = title.trim()
  if (!trimmed) return '?'
  return trimmed.charAt(0).toUpperCase()
}

function clearTimer() {
  if (debounceHandle !== null) {
    clearTimeout(debounceHandle)
    debounceHandle = null
  }
}

function cancelInflight() {
  if (inflight) {
    inflight.abort()
    inflight = null
  }
}

function runSearch(text: string) {
  clearTimer()
  cancelInflight()
  error.value = null

  const trimmed = text.trim()
  if (!trimmed) {
    hits.value = []
    highlightIndex.value = -1
    loading.value = false
    open.value = false
    return
  }

  loading.value = true
  open.value = true
  debounceHandle = setTimeout(async () => {
    const controller = new AbortController()
    inflight = controller
    try {
      const result = await searchTitles(trimmed, controller.signal)
      if (controller.signal.aborted) return
      hits.value = result
      highlightIndex.value = result.length > 0 ? 0 : -1
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      error.value = (err as Error).message
      hits.value = []
      highlightIndex.value = -1
    } finally {
      if (inflight === controller) inflight = null
      loading.value = false
    }
  }, 300)
}

// Search is triggered from the input's @input event, NOT from a watch on `query`,
// so programmatic mutations of `query` (e.g. inside `pick`) do not start a new
// search and reopen the dropdown.
function onInput(ev: Event) {
  const value = (ev.target as HTMLInputElement).value
  query.value = value
  if (props.selected) {
    emit('clear')
  }
  runSearch(value)
}

function pick(hit: TitleHit) {
  clearTimer()
  cancelInflight()
  loading.value = false
  query.value = formatHit(hit)
  hits.value = []
  highlightIndex.value = -1
  open.value = false
  emit('select', hit)
}

function clearSelection() {
  clearTimer()
  cancelInflight()
  loading.value = false
  query.value = ''
  hits.value = []
  highlightIndex.value = -1
  open.value = false
  emit('clear')
  inputRef.value?.focus()
}

function onFocus() {
  if (hits.value.length > 0) {
    open.value = true
  }
}

function onKeyDown(ev: KeyboardEvent) {
  if (ev.key === 'ArrowDown') {
    if (hits.value.length === 0) return
    ev.preventDefault()
    open.value = true
    highlightIndex.value = (highlightIndex.value + 1) % hits.value.length
    scrollHighlightedIntoView()
  } else if (ev.key === 'ArrowUp') {
    if (hits.value.length === 0) return
    ev.preventDefault()
    open.value = true
    highlightIndex.value =
      highlightIndex.value <= 0 ? hits.value.length - 1 : highlightIndex.value - 1
    scrollHighlightedIntoView()
  } else if (ev.key === 'Enter') {
    if (open.value && highlightIndex.value >= 0 && hits.value[highlightIndex.value]) {
      ev.preventDefault()
      pick(hits.value[highlightIndex.value])
    }
  } else if (ev.key === 'Escape') {
    if (open.value) {
      ev.preventDefault()
      open.value = false
    }
  }
}

function scrollHighlightedIntoView() {
  // Defer so the v-for has rendered the active class.
  queueMicrotask(() => {
    const list = listRef.value
    if (!list) return
    const item = list.querySelector<HTMLElement>('.title-search__item--active')
    item?.scrollIntoView({ block: 'nearest' })
  })
}

function onDocumentMouseDown(ev: MouseEvent) {
  if (!rootRef.value) return
  if (!rootRef.value.contains(ev.target as Node)) {
    open.value = false
  }
}

document.addEventListener('mousedown', onDocumentMouseDown)

// If the parent clears its selection externally, sync the input.
watch(
  () => props.selected,
  (sel, prev) => {
    if (sel === null && prev !== null && query.value === formatHit(prev)) {
      query.value = ''
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDocumentMouseDown)
  clearTimer()
  cancelInflight()
})
</script>

<template>
  <div ref="rootRef" class="title-search">
    <label class="title-search__label">{{ label }}</label>

    <div
      class="title-search__input-wrap"
      :class="{ 'title-search__input-wrap--selected': isSelected }"
    >
      <span
        class="title-search__leading"
        :class="{ 'title-search__leading--poster': isSelected }"
        aria-hidden="true"
      >
        <template v-if="isSelected && selected">
          <img
            v-if="selected.poster_url"
            class="title-search__leading-img"
            :src="selected.poster_url"
            :alt="''"
            loading="lazy"
            decoding="async"
          />
          <span v-else class="title-search__leading-fallback">
            {{ posterInitial(selected.title) }}
          </span>
        </template>
        <svg
          v-else
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      </span>
      <input
        ref="inputRef"
        :value="query"
        type="text"
        :placeholder="placeholder ?? 'Search movies and TV shows…'"
        autocomplete="off"
        spellcheck="false"
        role="combobox"
        aria-controls="title-search__listbox"
        :aria-expanded="open"
        aria-autocomplete="list"
        class="title-search__input"
        @input="onInput"
        @focus="onFocus"
        @keydown="onKeyDown"
      />
      <span v-if="loading" class="title-search__spinner" aria-hidden="true" />
      <button
        v-else-if="isSelected || query.length > 0"
        type="button"
        class="title-search__clear"
        :aria-label="isSelected ? 'Clear selection' : 'Clear input'"
        @click="clearSelection"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M18 6L6 18" />
          <path d="M6 6l12 12" />
        </svg>
      </button>
    </div>

    <p class="title-search__hint" :class="{ 'title-search__hint--ok': isSelected }">
      <template v-if="isSelected">
        Locked in. Click × to change.
      </template>
      <template v-else>
        Choose from the dropdown to confirm the IMDB title.
      </template>
    </p>

    <div v-if="open && (hits.length > 0 || error)" class="title-search__dropdown">
      <div v-if="error" class="title-search__error">{{ error }}</div>
      <ul
        v-else
        ref="listRef"
        id="title-search__listbox"
        class="title-search__list"
        role="listbox"
      >
        <li
          v-for="(hit, i) in hits"
          :key="hit.imdb_id"
          class="title-search__item"
          :class="{ 'title-search__item--active': i === highlightIndex }"
          role="option"
          :aria-selected="i === highlightIndex"
          @mousedown.prevent="pick(hit)"
          @mouseenter="highlightIndex = i"
        >
          <span class="title-search__poster" aria-hidden="true">
            <img
              v-if="hit.poster_url"
              :src="hit.poster_url"
              :alt="''"
              loading="lazy"
              decoding="async"
            />
            <span v-else class="title-search__poster-fallback">
              {{ posterInitial(hit.title) }}
            </span>
          </span>
          <span class="title-search__item-text">
            <span class="title-search__item-title">{{ hit.title }}</span>
            <span class="title-search__item-meta">
              <span v-if="hit.year" class="title-search__item-year">{{ hit.year }}</span>
              <span v-if="hit.kind" class="title-search__item-kind">
                {{ kindLabel(hit.kind) }}
              </span>
            </span>
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.title-search {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.title-search__label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.title-search__input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.title-search__input {
  padding-left: 42px;
  padding-right: 40px;
  height: 52px;
}

/* When a title is selected, the leading slot becomes a poster thumbnail,
   which needs more room than the search icon. */
.title-search__input-wrap--selected .title-search__input {
  padding-left: 56px;
}

.title-search__input-wrap--selected .title-search__input {
  border-color: rgba(52, 211, 153, 0.55);
  background:
    linear-gradient(0deg, var(--success-soft), var(--success-soft)),
    var(--bg-elev);
  box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.08);
}

.title-search__input-wrap--selected .title-search__input:focus {
  border-color: rgba(52, 211, 153, 0.8);
  box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.14);
}

.title-search__leading {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  pointer-events: none;
  transition: color var(--transition);
}

.title-search__leading--poster {
  left: 8px;
  width: 28px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-elev-3);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.05) inset,
    0 2px 6px rgba(0, 0, 0, 0.35);
}

.title-search__leading-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.title-search__leading-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-muted);
  background:
    radial-gradient(
      circle at 50% 30%,
      rgba(99, 102, 241, 0.18),
      transparent 70%
    ),
    var(--bg-elev-3);
}

.title-search__input-wrap--selected .title-search__leading {
  color: var(--success);
}

.title-search__input-wrap:focus-within .title-search__leading {
  color: var(--accent);
}

.title-search__input-wrap--selected:focus-within .title-search__leading {
  color: var(--success);
}

.title-search__spinner {
  position: absolute;
  right: 14px;
  top: 50%;
  width: 14px;
  height: 14px;
  margin-top: -7px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: title-search-spin 0.7s linear infinite;
}

@keyframes title-search-spin {
  to {
    transform: rotate(360deg);
  }
}

.title-search__clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: transparent;
  color: var(--text-muted);
  border: none;
  border-radius: 8px;
  width: 28px;
  height: 28px;
  padding: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.title-search__clear:hover {
  background: var(--bg-elev-3);
  color: var(--text);
}

.title-search__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  min-height: 16px;
  line-height: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.title-search__hint--ok {
  color: var(--success);
  font-weight: 500;
}

.title-search__dropdown {
  position: absolute;
  z-index: 20;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  max-height: 340px;
  overflow-y: auto;
  box-shadow: var(--shadow-lg);
  animation: title-search-fade 140ms ease-out;
}

@keyframes title-search-fade {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.title-search__error {
  padding: 14px;
  color: var(--danger);
  font-size: 14px;
}

.title-search__list {
  list-style: none;
  margin: 0;
  padding: 6px;
}

.title-search__item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition);
}

.title-search__item--active,
.title-search__item:hover {
  background: var(--bg-elev-2);
}

.title-search__item--active {
  background: var(--accent-soft);
}

.title-search__poster {
  flex: 0 0 auto;
  width: 36px;
  height: 52px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-elev-3);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 1px 3px rgba(0, 0, 0, 0.35);
}

.title-search__poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.title-search__poster-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-muted);
  background:
    radial-gradient(
      circle at 50% 30%,
      rgba(99, 102, 241, 0.2),
      transparent 70%
    ),
    var(--bg-elev-3);
}

.title-search__item-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.title-search__item-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.title-search__item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-search__item-year {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
}

.title-search__item-kind {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent);
  background: rgba(251, 191, 36, 0.14);
  border: 1px solid rgba(251, 191, 36, 0.22);
  padding: 2px 7px;
  border-radius: 999px;
}
</style>
