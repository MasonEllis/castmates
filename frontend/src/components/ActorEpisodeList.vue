<script lang="ts">
import type { EpisodeAppearance as Ep } from '../types'

const episodeCache = new Map<string, Ep[]>()
const episodeInflight = new Map<string, Promise<Ep[]>>()
</script>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getActorEpisodes } from '../api'
import type { EpisodeAppearance } from '../types'

const props = defineProps<{
  titleId: string
  personId: string
  episodeCount?: number | null
  /** When true, episode panel opens automatically (e.g. table detail row). */
  autoOpen?: boolean
}>()

const expanded = ref(props.autoOpen ?? false)
const loading = ref(false)
const error = ref<string | null>(null)
const episodes = ref<EpisodeAppearance[] | null>(null)
const activeSeason = ref<number | null>(null)

function cacheKey(): string {
  return `${props.titleId}:${props.personId}`
}

const seasons = computed(() => {
  if (!episodes.value?.length) return []
  const bySeason = new Map<number, EpisodeAppearance[]>()
  for (const ep of episodes.value) {
    const list = bySeason.get(ep.season) ?? []
    list.push(ep)
    bySeason.set(ep.season, list)
  }
  return [...bySeason.entries()]
    .sort(([a], [b]) => a - b)
    .map(([season, eps]) => ({
      season,
      episodes: [...eps].sort((a, b) => a.episode - b.episode),
    }))
})

const activeEpisodes = computed(() => {
  if (!seasons.value.length) return []
  const season =
    activeSeason.value ?? seasons.value[0]?.season ?? null
  return seasons.value.find((s) => s.season === season)?.episodes ?? []
})

const countLabel = computed(() => {
  const n = props.episodeCount
  if (n === null || n === undefined) return 'episodes'
  return n === 1 ? '1 episode' : `${n} episodes`
})

watch(
  seasons,
  (groups) => {
    if (!groups.length) return
    if (
      activeSeason.value === null ||
      !groups.some((g) => g.season === activeSeason.value)
    ) {
      activeSeason.value = groups[0].season
    }
  },
  { immediate: true },
)

watch(
  () => props.autoOpen,
  (open) => {
    if (open) {
      expanded.value = true
      void loadEpisodes()
    }
  },
)

async function loadEpisodes(): Promise<void> {
  const key = cacheKey()
  if (episodeCache.has(key)) {
    episodes.value = episodeCache.get(key)!
    return
  }

  if (episodeInflight.has(key)) {
    loading.value = true
    try {
      episodes.value = await episodeInflight.get(key)!
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
    return
  }

  loading.value = true
  error.value = null

  const request = getActorEpisodes(props.titleId, props.personId)
    .then((result) => {
      episodeCache.set(key, result.episodes)
      episodeInflight.delete(key)
      return result.episodes
    })
    .catch((e: Error) => {
      episodeInflight.delete(key)
      throw e
    })

  episodeInflight.set(key, request)

  try {
    episodes.value = await request
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function toggle(): void {
  expanded.value = !expanded.value
  if (expanded.value && !episodes.value && !loading.value) {
    void loadEpisodes()
  }
}

function imdbEpisodeUrl(id: string): string {
  return `https://www.imdb.com/title/tt${id}/`
}

function formatEpisodeLabel(ep: EpisodeAppearance): string {
  return String(ep.episode)
}

function formatFullCode(ep: EpisodeAppearance): string {
  return `S${String(ep.season).padStart(2, '0')}E${String(ep.episode).padStart(2, '0')}`
}
</script>

<template>
  <div class="ep-list" :class="{ 'ep-list--open': expanded }">
    <button
      type="button"
      class="ep-list__toggle"
      :aria-expanded="expanded"
      @click="toggle"
    >
      <span class="ep-list__toggle-label">
        {{ expanded ? 'Hide' : 'View' }} {{ countLabel }}
      </span>
      <span class="ep-list__chevron" :class="{ 'ep-list__chevron--open': expanded }">
        ›
      </span>
    </button>

    <div v-if="expanded" class="ep-list__panel">
      <p v-if="loading" class="ep-list__status">
        <span class="ep-list__spinner" aria-hidden="true" />
        Loading episodes from IMDB…
      </p>

      <div v-else-if="error" class="ep-list__status ep-list__status--error">
        <span>{{ error }}</span>
        <button type="button" class="ep-list__retry" @click="loadEpisodes">
          Retry
        </button>
      </div>

      <template v-else-if="episodes?.length">
        <div
          v-if="seasons.length > 1"
          class="ep-list__seasons"
          role="tablist"
          :aria-label="`Seasons for ${countLabel}`"
        >
          <button
            v-for="group in seasons"
            :key="group.season"
            type="button"
            role="tab"
            class="ep-list__season-tab"
            :class="{ 'ep-list__season-tab--active': activeSeason === group.season }"
            :aria-selected="activeSeason === group.season"
            @click="activeSeason = group.season"
          >
            S{{ group.season }}
            <span class="ep-list__season-count">{{ group.episodes.length }}</span>
          </button>
        </div>

        <ul class="ep-list__grid">
          <li v-for="ep in activeEpisodes" :key="ep.imdb_id">
            <a
              class="ep-list__chip"
              :href="imdbEpisodeUrl(ep.imdb_id)"
              target="_blank"
              rel="noopener noreferrer"
              :title="`${formatFullCode(ep)} — ${ep.title}`"
            >
              <span class="ep-list__chip-code">{{ formatEpisodeLabel(ep) }}</span>
              <span class="ep-list__chip-title">{{ ep.title }}</span>
            </a>
          </li>
        </ul>
      </template>

      <p v-else-if="!loading" class="ep-list__status">
        No episode data found for this actor in this series.
      </p>
    </div>
  </div>
</template>

<style scoped>
.ep-list {
  margin-top: 8px;
}

.ep-list__toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-elev-2);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 10px 4px 12px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-soft);
  cursor: pointer;
  transition:
    border-color var(--transition),
    color var(--transition),
    background var(--transition);
}

.ep-list__toggle:hover {
  border-color: var(--border-strong);
  color: var(--text);
}

.ep-list--open .ep-list__toggle {
  border-color: rgba(251, 191, 36, 0.35);
  color: var(--accent);
}

.ep-list__chevron {
  display: inline-block;
  font-size: 14px;
  line-height: 1;
  transition: transform var(--transition);
  transform: rotate(90deg);
}

.ep-list__chevron--open {
  transform: rotate(-90deg);
  color: var(--accent);
}

.ep-list__panel {
  margin-top: 10px;
  padding: 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.ep-list__status {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.ep-list__status--error {
  color: var(--danger);
  flex-wrap: wrap;
}

.ep-list__retry {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 2px 8px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
}

.ep-list__retry:hover {
  border-color: var(--border-strong);
  color: var(--accent);
}

.ep-list__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-strong);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: ep-spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes ep-spin {
  to {
    transform: rotate(360deg);
  }
}

.ep-list__seasons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.ep-list__season-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 10px;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    border-color var(--transition),
    color var(--transition),
    background var(--transition);
}

.ep-list__season-tab:hover {
  color: var(--text);
  border-color: var(--border-strong);
}

.ep-list__season-tab--active {
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.4);
  color: var(--accent);
}

.ep-list__season-count {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

.ep-list__grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px;
}

.ep-list__chip {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 8px;
  text-decoration: none;
  transition:
    border-color var(--transition),
    transform var(--transition),
    background var(--transition);
  min-width: 0;
}

.ep-list__chip:hover {
  border-color: rgba(251, 191, 36, 0.45);
  background: var(--bg-elev-2);
  transform: translateY(-1px);
}

.ep-list__chip-code {
  flex: 0 0 auto;
  min-width: 1.25rem;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.ep-list__chip-title {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>