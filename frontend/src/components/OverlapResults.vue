<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ActorEpisodeList from './ActorEpisodeList.vue'
import type { SharedActor, TitleSummary } from '../types'

const props = defineProps<{
  titles: TitleSummary[]
  shared: SharedActor[]
}>()

const emit = defineEmits<{
  (e: 'remove', imdbId: string): void
}>()

// Sort key is either 'name', 'combined', or 'title:<index>'.
type SortKey = 'name' | 'combined' | `title:${number}`
type SortDir = 'desc' | 'asc'
type View = 'grid' | 'table'

const sortKey = ref<SortKey>('combined')
const sortDir = ref<SortDir>('desc')
const expanded = ref<Set<string>>(new Set())
const view = ref<View>('grid')

watch(
  () => props.titles.map((t) => t.imdb_id).join(','),
  () => {
    sortKey.value = 'combined'
    sortDir.value = 'desc'
    expanded.value = new Set()
  },
)

const episodesAvailable = computed(() =>
  props.shared.some((a) => a.episodes.some((e) => e !== null)),
)

function ep(n: number | null | undefined): number {
  return n ?? 0
}

function combined(a: SharedActor): number {
  return a.episodes.reduce<number>((sum, e) => sum + ep(e), 0)
}

const sortedRows = computed(() => {
  const rows = [...props.shared]
  const dirMul = sortDir.value === 'asc' ? 1 : -1
  const key = sortKey.value

  rows.sort((a, b) => {
    let cmp = 0
    if (key === 'name') {
      cmp = a.name.localeCompare(b.name)
    } else if (key === 'combined') {
      cmp = combined(a) - combined(b)
    } else if (key.startsWith('title:')) {
      const idx = Number(key.slice('title:'.length))
      cmp = ep(a.episodes[idx]) - ep(b.episodes[idx])
    }
    if (cmp === 0) cmp = a.name.localeCompare(b.name)
    return cmp * dirMul
  })

  return rows
})

function setSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'name' ? 'asc' : 'desc'
  }
}

function sortArrow(key: SortKey): string {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'desc' ? '▼' : '▲'
}

function isExpanded(id: string): boolean {
  return expanded.value.has(id)
}

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

function titleLabel(t: TitleSummary): string {
  return t.year ? `${t.title} (${t.year})` : t.title
}

function imdbPersonUrl(id: string): string {
  return `https://www.imdb.com/name/nm${id}/`
}

function imdbTitleUrl(id: string): string {
  return `https://www.imdb.com/title/tt${id}/`
}

function isTvTitle(kind: string | null): boolean {
  return kind !== null && kind.toLowerCase().includes('tv')
}

function hasEpisodeCount(n: number | null | undefined): boolean {
  return n !== null && n !== undefined && n > 0
}

function epLabel(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n === 1 ? '1 ep' : `${n} eps`
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function titleInitial(title: string): string {
  const trimmed = title.trim()
  if (!trimmed) return '?'
  return trimmed.charAt(0).toUpperCase()
}

// Total colspan for the expanded detail row:
// 1 (chevron) + 1 (actor) + 2 per title + 1 (total, when present)
const detailColspan = computed(
  () => 2 + props.titles.length * 2 + (episodesAvailable.value ? 1 : 0),
)

const sortOptions = computed(() => {
  const opts: { key: SortKey; label: string }[] = []
  if (episodesAvailable.value) {
    opts.push({ key: 'combined', label: 'Total episodes' })
  }
  props.titles.forEach((t, i) => {
    opts.push({ key: `title:${i}` as SortKey, label: `Eps in ${t.title}` })
  })
  opts.push({ key: 'name', label: 'Name (A–Z)' })
  return opts
})

function selectSort(e: Event) {
  const key = (e.target as HTMLSelectElement).value as SortKey
  if (key === sortKey.value) return
  sortKey.value = key
  sortDir.value = key === 'name' ? 'asc' : 'desc'
}
</script>

<template>
  <section class="overlap">
    <header class="overlap__header">
      <div class="overlap__heading-row">
        <div>
          <p class="overlap__eyebrow">Shared cast</p>
          <h2 class="overlap__heading">
            <span class="overlap__count">{{ shared.length }}</span>
            {{ shared.length === 1 ? 'actor appears' : 'actors appear' }}
            in all {{ titles.length }} titles
          </h2>
        </div>

        <div v-if="shared.length > 0" class="overlap__toolbar">
          <label class="overlap__sort" v-if="view === 'grid'">
            <span class="overlap__sort-label">Sort by</span>
            <select
              class="overlap__sort-select"
              :value="sortKey"
              @change="selectSort"
            >
              <option
                v-for="opt in sortOptions"
                :key="opt.key"
                :value="opt.key"
              >
                {{ opt.label }}
              </option>
            </select>
          </label>

          <div class="overlap__view" role="tablist" aria-label="Result view">
            <button
              type="button"
              role="tab"
              :aria-selected="view === 'grid'"
              class="overlap__view-btn"
              :class="{ 'overlap__view-btn--active': view === 'grid' }"
              @click="view = 'grid'"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <rect x="3" y="3" width="7" height="7" rx="1.5" />
                <rect x="14" y="3" width="7" height="7" rx="1.5" />
                <rect x="3" y="14" width="7" height="7" rx="1.5" />
                <rect x="14" y="14" width="7" height="7" rx="1.5" />
              </svg>
              Cards
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="view === 'table'"
              class="overlap__view-btn"
              :class="{ 'overlap__view-btn--active': view === 'table' }"
              @click="view = 'table'"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                width="14"
                height="14"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
              Table
            </button>
          </div>
        </div>
      </div>

      <ul class="overlap__chips" aria-label="Titles being compared">
        <li
          v-for="t in titles"
          :key="t.imdb_id"
          class="overlap__chip"
        >
          <a
            class="overlap__chip-link"
            :href="imdbTitleUrl(t.imdb_id)"
            target="_blank"
            rel="noopener noreferrer"
            :title="`Open ${titleLabel(t)} on IMDB`"
          >
            <span class="overlap__chip-poster" aria-hidden="true">
              <img
                v-if="t.poster_url"
                :src="t.poster_url"
                :alt="''"
                loading="lazy"
                decoding="async"
              />
              <span v-else class="overlap__chip-poster-fallback">
                {{ titleInitial(t.title) }}
              </span>
            </span>
            <span class="overlap__chip-text">{{ titleLabel(t) }}</span>
          </a>
          <button
            type="button"
            class="overlap__chip-remove"
            :aria-label="`Remove ${titleLabel(t)} from comparison`"
            :title="`Remove ${titleLabel(t)} from comparison`"
            @click="emit('remove', t.imdb_id)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="12"
              height="12"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M18 6L6 18" />
              <path d="M6 6l12 12" />
            </svg>
          </button>
        </li>
      </ul>
    </header>

    <p v-if="shared.length === 0" class="overlap__empty">
      <span class="overlap__empty-icon" aria-hidden="true">∅</span>
      No actor appears in all of these titles. Try removing one of the more
      obscure picks, or note that IMDB's top-cast pages cap at ~260 names per
      title.
    </p>

    <!-- ---------- GRID VIEW ---------- -->
    <div v-else-if="view === 'grid'" class="overlap__grid">
      <article
        v-for="actor in sortedRows"
        :key="actor.imdb_id"
        class="actor-card"
      >
        <a
          class="actor-card__photo"
          :href="imdbPersonUrl(actor.imdb_id)"
          target="_blank"
          rel="noopener noreferrer"
          :aria-label="`Open ${actor.name} on IMDB`"
        >
          <img
            v-if="actor.headshot_url"
            :src="actor.headshot_url"
            :alt="actor.name"
            loading="lazy"
          />
          <span v-else class="actor-card__photo-placeholder" aria-hidden="true">
            {{ initials(actor.name) }}
          </span>
          <span
            v-if="episodesAvailable"
            class="actor-card__badge"
            :title="`${combined(actor)} total episodes`"
          >
            {{ combined(actor) }}
          </span>
        </a>

        <div class="actor-card__body">
          <a
            class="actor-card__name"
            :href="imdbPersonUrl(actor.imdb_id)"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ actor.name }}
          </a>

          <ul class="actor-card__roles">
            <li
              v-for="(t, i) in titles"
              :key="t.imdb_id"
              class="actor-card__role"
            >
              <div class="actor-card__role-title" :title="titleLabel(t)">
                {{ t.title }}
              </div>
              <div class="actor-card__role-meta">
                <span class="actor-card__role-name">
                  {{ actor.roles[i] ?? '—' }}
                </span>
                <span
                  v-if="actor.episodes[i] !== null && actor.episodes[i] !== undefined"
                  class="actor-card__role-eps"
                >
                  {{ epLabel(actor.episodes[i]) }}
                </span>
              </div>
              <ActorEpisodeList
                v-if="isTvTitle(t.kind) && hasEpisodeCount(actor.episodes[i])"
                :title-id="t.imdb_id"
                :person-id="actor.imdb_id"
                :episode-count="actor.episodes[i]"
              />
            </li>
          </ul>
        </div>
      </article>
    </div>

    <!-- ---------- TABLE VIEW ---------- -->
    <div v-else class="overlap__table-wrap">
      <table class="overlap__table">
        <thead>
          <tr>
            <th scope="col" class="th-expand" aria-label="Expand row"></th>
            <th
              scope="col"
              class="th-sortable"
              :class="{ 'th-sortable--active': sortKey === 'name' }"
              @click="setSort('name')"
            >
              Actor
              <span class="th-sortable__arrow">{{ sortArrow('name') }}</span>
            </th>
            <template v-for="(t, i) in titles" :key="t.imdb_id">
              <th scope="col" class="th-title" :title="t.title">
                {{ t.title }}
              </th>
              <th
                scope="col"
                class="th-sortable th-eps"
                :class="{ 'th-sortable--active': sortKey === `title:${i}` }"
                :title="`Sort by episodes in ${t.title}`"
                @click="setSort(`title:${i}`)"
              >
                Eps
                <span class="th-sortable__arrow">{{ sortArrow(`title:${i}`) }}</span>
              </th>
            </template>
            <th
              v-if="episodesAvailable"
              scope="col"
              class="th-sortable th-eps"
              :class="{ 'th-sortable--active': sortKey === 'combined' }"
              title="Sort by combined episode count"
              @click="setSort('combined')"
            >
              Total
              <span class="th-sortable__arrow">{{ sortArrow('combined') }}</span>
            </th>
          </tr>
        </thead>
        <tbody
          v-for="actor in sortedRows"
          :key="actor.imdb_id"
          class="row-group"
        >
          <tr
            class="row-main"
            :class="{ 'row-main--open': isExpanded(actor.imdb_id) }"
            @click="toggle(actor.imdb_id)"
          >
            <td class="cell-expand" aria-hidden="true">
              <span
                class="chevron"
                :class="{ 'chevron--open': isExpanded(actor.imdb_id) }"
              >›</span>
            </td>
            <td class="cell-name">
              <a
                :href="imdbPersonUrl(actor.imdb_id)"
                target="_blank"
                rel="noopener noreferrer"
                @click.stop
              >{{ actor.name }}</a>
            </td>
            <template v-for="(t, i) in titles" :key="t.imdb_id">
              <td class="cell-role">{{ actor.roles[i] ?? '—' }}</td>
              <td class="cell-eps">{{ epLabel(actor.episodes[i]) }}</td>
            </template>
            <td v-if="episodesAvailable" class="cell-eps cell-eps--total">
              {{ combined(actor) }}
            </td>
          </tr>
          <tr v-if="isExpanded(actor.imdb_id)" class="row-detail">
            <td :colspan="detailColspan">
              <div class="actor-detail">
                <a
                  class="actor-detail__photo"
                  :href="imdbPersonUrl(actor.imdb_id)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    v-if="actor.headshot_url"
                    :src="actor.headshot_url"
                    :alt="actor.name"
                    loading="lazy"
                  />
                  <span
                    v-else
                    class="actor-detail__photo-placeholder"
                    aria-hidden="true"
                  >{{ initials(actor.name) }}</span>
                </a>
                <div class="actor-detail__body">
                  <a
                    class="actor-detail__name"
                    :href="imdbPersonUrl(actor.imdb_id)"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ actor.name }} ↗</a>
                  <dl class="actor-detail__roles">
                    <div
                      v-for="(t, i) in titles"
                      :key="t.imdb_id"
                      class="actor-detail__role"
                    >
                      <dt>{{ titleLabel(t) }}</dt>
                      <dd>
                        <span>{{ actor.roles[i] ?? '—' }}</span>
                        <span
                          v-if="actor.episodes[i] !== null && actor.episodes[i] !== undefined"
                          class="actor-detail__eps"
                        >{{ epLabel(actor.episodes[i]) }}</span>
                      </dd>
                      <dd
                        v-if="isTvTitle(t.kind) && hasEpisodeCount(actor.episodes[i])"
                        class="actor-detail__episode-block"
                      >
                        <ActorEpisodeList
                          :title-id="t.imdb_id"
                          :person-id="actor.imdb_id"
                          :episode-count="actor.episodes[i]"
                        />
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.overlap {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Header --------------------------------------------------------- */

.overlap__header {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.overlap__heading-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.overlap__eyebrow {
  margin: 0 0 4px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}

.overlap__heading {
  margin: 0;
  font-size: clamp(20px, 2.2vw, 26px);
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.overlap__count {
  background: var(--accent-grad);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 800;
}

.overlap__toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.overlap__sort {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 4px 4px 4px 12px;
  height: 38px;
}

.overlap__sort-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.overlap__sort-select {
  font: inherit;
  appearance: none;
  background:
    linear-gradient(45deg, transparent 50%, var(--text-muted) 50%) calc(100% - 14px) 50% / 5px 5px no-repeat,
    linear-gradient(135deg, var(--text-muted) 50%, transparent 50%) calc(100% - 9px) 50% / 5px 5px no-repeat,
    var(--bg-elev-2);
  color: var(--text);
  border: none;
  border-radius: 8px;
  height: 30px;
  padding: 0 28px 0 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  outline: none;
}

.overlap__sort-select:focus-visible {
  box-shadow: 0 0 0 2px rgba(251, 191, 36, 0.5);
}

.overlap__view {
  display: inline-flex;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 3px;
  gap: 2px;
}

.overlap__view-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  color: var(--text-muted);
  border: none;
  border-radius: 8px;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
  height: 30px;
}

.overlap__view-btn:hover:not(.overlap__view-btn--active) {
  color: var(--text);
  background: var(--bg-elev-2);
}

.overlap__view-btn--active {
  background: var(--bg-elev-3);
  color: var(--text);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04) inset;
}

.overlap__chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.overlap__chip {
  display: inline-flex;
  align-items: stretch;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 999px;
  overflow: hidden;
  transition:
    border-color var(--transition),
    transform var(--transition);
}

.overlap__chip:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.overlap__chip-link {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 4px 4px 4px;
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  transition: color var(--transition);
}

.overlap__chip-link:hover {
  color: var(--accent);
}

.overlap__chip-poster {
  flex: 0 0 auto;
  width: 26px;
  height: 36px;
  border-radius: 999px 6px 6px 999px;
  overflow: hidden;
  background: var(--bg-elev-3);
}

.overlap__chip-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.overlap__chip-poster-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
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

.overlap__chip-text {
  padding-right: 6px;
  white-space: nowrap;
}

.overlap__chip-remove {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  padding: 0;
  border: none;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  border-radius: 0;
  cursor: pointer;
  transition:
    background var(--transition),
    color var(--transition);
}

.overlap__chip-remove:hover {
  background: var(--danger-soft);
  color: var(--danger);
}

.overlap__chip-remove:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 2px rgba(248, 113, 113, 0.55);
}

/* Empty state --------------------------------------------------- */

.overlap__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 36px 24px;
  background: var(--bg-elev);
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  color: var(--text-muted);
  text-align: center;
  line-height: 1.6;
}

.overlap__empty-icon {
  font-size: 28px;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--bg-elev-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

/* GRID VIEW ----------------------------------------------------- */

.overlap__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.actor-card {
  display: flex;
  flex-direction: column;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition:
    transform var(--transition),
    border-color var(--transition),
    box-shadow var(--transition);
}

.actor-card:hover {
  transform: translateY(-3px);
  border-color: var(--border-strong);
  box-shadow: var(--shadow-md);
}

.actor-card__photo {
  position: relative;
  display: block;
  aspect-ratio: 3 / 4;
  background: linear-gradient(180deg, var(--bg-elev-2), var(--bg-elev-3));
  overflow: hidden;
}

.actor-card__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 400ms cubic-bezier(0.2, 0.7, 0.3, 1);
}

.actor-card:hover .actor-card__photo img {
  transform: scale(1.04);
}

.actor-card__photo-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 44px;
  font-weight: 800;
  color: var(--text-muted);
  letter-spacing: -0.02em;
  background:
    radial-gradient(
      circle at 50% 30%,
      rgba(251, 191, 36, 0.12),
      transparent 65%
    ),
    var(--bg-elev-2);
}

.actor-card__badge {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(10, 11, 16, 0.78);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(251, 191, 36, 0.35);
  font-variant-numeric: tabular-nums;
}

.actor-card__body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
}

.actor-card__name {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  text-decoration: none;
  letter-spacing: -0.005em;
  line-height: 1.25;
}

.actor-card__name:hover {
  color: var(--accent);
}

.actor-card__roles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.actor-card__role {
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.actor-card__role:first-child {
  border-top: none;
  padding-top: 0;
}

.actor-card__role-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.actor-card__role-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.actor-card__role-name {
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

.actor-card__role-eps {
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* TABLE VIEW ---------------------------------------------------- */

.overlap__table-wrap {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow-x: auto;
}

.overlap__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

thead th {
  position: sticky;
  top: 0;
  background: var(--bg-elev-2);
  border-bottom: 1px solid var(--border);
  padding: 12px 14px;
  text-align: left;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  font-weight: 700;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

.th-expand {
  width: 36px;
}

th.th-eps,
td.cell-eps {
  text-align: right;
  font-variant-numeric: tabular-nums;
  width: 80px;
  white-space: nowrap;
}

th.th-title {
  color: var(--text-muted);
  min-width: 120px;
  max-width: 220px;
}

th.th-sortable {
  cursor: pointer;
  transition: color var(--transition);
}

th.th-sortable:hover {
  color: var(--text);
}

th.th-sortable--active {
  color: var(--accent);
}

.th-sortable__arrow {
  display: inline-block;
  width: 12px;
  text-align: center;
  font-size: 10px;
  margin-left: 4px;
}

tbody td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

tr.row-main {
  cursor: pointer;
  transition: background var(--transition);
}

tr.row-main:hover {
  background: var(--bg-elev-2);
}

tr.row-main--open {
  background: var(--bg-elev-2);
}

tr.row-main--open td {
  border-bottom-color: transparent;
}

.cell-expand {
  padding: 0 0 0 14px;
  color: var(--text-muted);
}

.chevron {
  display: inline-block;
  font-size: 16px;
  transition: transform var(--transition);
  transform-origin: center;
}

.chevron--open {
  transform: rotate(90deg);
  color: var(--accent);
}

.cell-name {
  min-width: 140px;
}

.cell-name a {
  color: var(--text);
  font-weight: 500;
  text-decoration: none;
}

.cell-name a:hover {
  color: var(--accent);
  text-decoration: underline;
}

.cell-role {
  color: var(--text-muted);
}

.cell-eps--total {
  font-weight: 700;
  color: var(--accent);
}

tr.row-detail td {
  background: var(--bg-elev-2);
  padding: 0 14px 18px;
  border-bottom: 1px solid var(--border);
  white-space: normal;
  max-width: none;
}

.actor-detail {
  display: flex;
  gap: 18px;
  padding: 10px 0 0;
}

.actor-detail__photo {
  flex: 0 0 120px;
  width: 120px;
  height: 160px;
  background: var(--bg);
  border-radius: 10px;
  overflow: hidden;
  display: block;
}

.actor-detail__photo img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.actor-detail__photo-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  font-weight: 800;
  color: var(--text-muted);
}

.actor-detail__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 4px;
}

.actor-detail__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  text-decoration: none;
  white-space: nowrap;
}

.actor-detail__name:hover {
  color: var(--accent);
}

.actor-detail__roles {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}

.actor-detail__role {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.actor-detail__role dt {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.actor-detail__role dd {
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  color: var(--text);
}

.actor-detail__eps {
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  font-weight: 600;
}

.actor-detail__episode-block {
  margin: 8px 0 0;
}

/* Responsive ---------------------------------------------------- */

@media (max-width: 640px) {
  .overlap__grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }

  .actor-card__body {
    padding: 12px;
  }
}
</style>
