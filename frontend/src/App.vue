<script setup lang="ts">
import { computed, ref } from 'vue'
import { getOverlap } from './api'
import TitleSearch from './components/TitleSearch.vue'
import OverlapResults from './components/OverlapResults.vue'
import type { OverlapResult, TitleHit } from './types'

const MIN_TITLES = 2
const MAX_TITLES = 10

const titles = ref<(TitleHit | null)[]>([null, null])
const result = ref<OverlapResult | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

const selectedIds = computed(() =>
  titles.value.filter((t): t is TitleHit => t !== null).map((t) => t.imdb_id),
)

const filledCount = computed(
  () => titles.value.filter((t) => t !== null).length,
)

const canSubmit = computed(() => {
  if (loading.value) return false
  if (titles.value.length < MIN_TITLES) return false
  if (titles.value.some((t) => t === null)) return false
  const ids = selectedIds.value
  return new Set(ids).size === ids.length
})

let inflight: AbortController | null = null

function clearResultState() {
  result.value = null
  error.value = null
}

function onSelect(index: number, hit: TitleHit) {
  titles.value[index] = hit
  clearResultState()
}

function onClear(index: number) {
  titles.value[index] = null
  clearResultState()
}

function addTitle() {
  if (titles.value.length >= MAX_TITLES) return
  titles.value.push(null)
  clearResultState()
}

function removeTitle(index: number) {
  if (titles.value.length <= MIN_TITLES) return
  titles.value.splice(index, 1)
  clearResultState()
}

/** Called from <OverlapResults> when the user clicks × on a title chip in
 *  the results header. Drops that title from the lineup so they can re-pick
 *  without rebuilding the comparison from scratch. */
function removeTitleById(imdbId: string) {
  const index = titles.value.findIndex((t) => t?.imdb_id === imdbId)
  if (index === -1) return
  if (titles.value.length > MIN_TITLES) {
    titles.value.splice(index, 1)
  } else {
    titles.value[index] = null
  }
  clearResultState()
}

async function findOverlap() {
  const ids = selectedIds.value
  if (ids.length < MIN_TITLES) return
  if (inflight) inflight.abort()
  const controller = new AbortController()
  inflight = controller

  loading.value = true
  error.value = null
  result.value = null
  try {
    const r = await getOverlap(ids, controller.signal)
    if (controller.signal.aborted) return
    result.value = r
  } catch (e) {
    if ((e as Error).name === 'AbortError') return
    error.value = (e as Error).message
  } finally {
    if (inflight === controller) inflight = null
    loading.value = false
  }
}
</script>

<template>
  <div class="app">
    <header class="hero">
      <div class="hero__inner">
        <a class="hero__brand" href="/" aria-label="Castmates home">
          <img
            class="hero__brand-mark"
            src="/castmates-logo.svg?v=2"
            alt=""
            width="112"
            height="112"
            decoding="async"
          />
          <span class="hero__brand-word">Castmates</span>
        </a>

        <h1 class="hero__title">
          Find the actors
          <span class="hero__title-grad">two shows have in common.</span>
        </h1>

        <p class="hero__tagline">
          Pick any two (or more) movies and TV shows — we'll surface every
          performer who appears across the whole list, with roles and episode
          counts from IMDB.
        </p>
      </div>
    </header>

    <main class="app__main">
      <section class="picker" aria-label="Pick titles to compare">
        <div class="picker__head">
          <div class="picker__head-text">
            <h2 class="picker__heading">Your lineup</h2>
            <p class="picker__sub">
              {{ filledCount }} of {{ titles.length }} titles selected
            </p>
          </div>
          <div class="picker__progress" :aria-hidden="true">
            <div
              v-for="i in titles.length"
              :key="i"
              class="picker__dot"
              :class="{ 'picker__dot--filled': titles[i - 1] !== null }"
            />
          </div>
        </div>

        <div class="picker__titles">
          <div
            v-for="(t, i) in titles"
            :key="i"
            class="picker__slot"
          >
            <TitleSearch
              :label="`Title ${i + 1}`"
              placeholder="Search movies and TV shows…"
              :selected="t"
              @select="(hit) => onSelect(i, hit)"
              @clear="() => onClear(i)"
            />
            <button
              v-if="titles.length > MIN_TITLES"
              class="picker__remove"
              type="button"
              :aria-label="`Remove Title ${i + 1}`"
              :title="`Remove Title ${i + 1}`"
              @click="removeTitle(i)"
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
        </div>

        <div class="picker__actions">
          <button
            class="picker__add"
            type="button"
            :disabled="titles.length >= MAX_TITLES"
            @click="addTitle"
          >
            <svg
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
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
            Add another title
          </button>

          <button
            class="picker__submit"
            type="button"
            :disabled="!canSubmit"
            @click="findOverlap"
          >
            <span v-if="loading" class="picker__submit-spinner" aria-hidden="true" />
            <span>{{ loading ? 'Searching IMDB…' : 'Find the shared cast' }}</span>
            <svg
              v-if="!loading"
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              stroke-width="2.25"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <path d="M5 12h14" />
              <path d="M13 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </section>

      <section v-if="error" class="alert alert--error" role="alert">
        <span class="alert__icon" aria-hidden="true">!</span>
        <div>
          <strong>Something went wrong.</strong>
          <div class="alert__body">{{ error }}</div>
        </div>
      </section>

      <section v-if="loading && !result" class="loading-card" aria-live="polite">
        <div class="loading-card__pulse" aria-hidden="true">
          <span /><span /><span />
        </div>
        <div class="loading-card__text">
          <strong>Fetching cast lists from IMDB…</strong>
          <p>
            This can take 10–30 seconds for large casts. Repeated comparisons
            for the same titles are cached for instant replays.
          </p>
        </div>
      </section>

      <OverlapResults
        v-if="result"
        :titles="result.titles"
        :shared="result.shared"
        @remove="removeTitleById"
      />
    </main>

    <footer class="app__footer">
      <span>
        Data via the open-source
        <a href="https://github.com/tveronesi/imdbinfo" target="_blank" rel="noopener">
          imdbinfo
        </a>
        library. Not affiliated with IMDB.
      </span>
    </footer>
  </div>
</template>

<style scoped>
.app {
  max-width: 1180px;
  margin: 0 auto;
  padding: 56px 28px 64px;
  display: flex;
  flex-direction: column;
  gap: 36px;
  min-height: 100%;
}

/* Hero ------------------------------------------------------------ */

.hero {
  position: relative;
}

.hero__inner {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 760px;
}

.hero__brand {
  display: inline-flex;
  align-items: center;
  gap: 16px;
  align-self: flex-start;
  text-decoration: none;
  color: inherit;
  outline: none;
  border-radius: 14px;
  padding: 4px 4px 4px 0;
  transition: transform var(--transition);
}

.hero__brand:hover {
  color: inherit;
}

.hero__brand:focus-visible {
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.55);
}

.hero__brand-mark {
  width: 112px;
  height: 112px;
  display: block;
  filter:
    drop-shadow(0 18px 36px rgba(99, 102, 241, 0.32))
    drop-shadow(0 6px 14px rgba(239, 68, 68, 0.22));
  transition: transform 280ms cubic-bezier(0.2, 0.7, 0.3, 1);
  transform-origin: center;
}

.hero__brand:hover .hero__brand-mark {
  transform: rotate(-6deg) scale(1.04);
}

.hero__brand-word {
  font-size: 38px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--text);
  line-height: 1;
}

@media (max-width: 640px) {
  .hero__brand {
    gap: 12px;
  }

  .hero__brand-mark {
    width: 80px;
    height: 80px;
  }

  .hero__brand-word {
    font-size: 28px;
  }
}

.hero__title {
  margin: 0;
  font-size: clamp(34px, 5vw, 52px);
  font-weight: 800;
  letter-spacing: -0.02em;
  line-height: 1.05;
  color: var(--text);
}

.hero__title-grad {
  display: block;
  background: var(--accent-grad);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  padding-top: 2px;
}

.hero__tagline {
  margin: 0;
  color: var(--text-soft);
  font-size: clamp(15px, 1.6vw, 17px);
  line-height: 1.55;
  max-width: 62ch;
}

/* Picker ---------------------------------------------------------- */

.app__main {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.picker {
  display: flex;
  flex-direction: column;
  gap: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0)) ,
    var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: 24px 26px;
  box-shadow: var(--shadow-md);
  position: relative;
  /* No `overflow: hidden` here — the typeahead dropdowns inside need to
     extend past the card edges. The decorative gradient border is drawn
     in-bounds via ::before so it doesn't need clipping. */
}

.picker::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.28),
    rgba(217, 70, 239, 0.18) 50%,
    transparent 80%
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask-composite: exclude;
  pointer-events: none;
  opacity: 0.8;
}

.picker__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.picker__heading {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.picker__sub {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.picker__progress {
  display: flex;
  gap: 6px;
}

.picker__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bg-elev-3);
  transition: background var(--transition), box-shadow var(--transition);
}

.picker__dot--filled {
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.18);
}

.picker__titles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}

.picker__slot {
  position: relative;
}

.picker__remove {
  position: absolute;
  top: -10px;
  right: -10px;
  z-index: 5;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--bg-elev-2);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}

.picker__remove:hover {
  border-color: var(--danger);
  color: var(--danger);
  background: var(--bg-elev);
  transform: scale(1.05);
}

.picker__actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.picker__add {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: transparent;
  color: var(--text-muted);
  border: 1px dashed var(--border-strong);
  padding: 10px 16px;
  border-radius: 999px;
  font-weight: 500;
}

.picker__add:hover:not(:disabled) {
  color: var(--accent);
  border-color: rgba(251, 191, 36, 0.6);
  background: var(--accent-soft);
}

.picker__submit {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  background: var(--accent-grad);
  color: #1a0f00;
  height: 48px;
  padding: 0 22px;
  min-width: 220px;
  justify-content: center;
  border-radius: 999px;
  font-weight: 700;
  letter-spacing: 0.01em;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.25) inset,
    0 10px 30px -10px rgba(251, 146, 24, 0.6);
}

.picker__submit:hover:not(:disabled) {
  filter: brightness(1.05);
  transform: translateY(-1px);
}

.picker__submit:disabled {
  background: var(--bg-elev-3);
  color: var(--text-muted);
  box-shadow: none;
}

.picker__submit-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 0, 0, 0.25);
  border-top-color: rgba(0, 0, 0, 0.9);
  border-radius: 50%;
  animation: app-spin 0.7s linear infinite;
}

@keyframes app-spin {
  to {
    transform: rotate(360deg);
  }
}

/* Alerts ---------------------------------------------------------- */

.alert {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-elev);
}

.alert__icon {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
}

.alert--error {
  border-color: rgba(248, 113, 113, 0.35);
  background: var(--danger-soft);
  color: var(--danger);
}

.alert--error .alert__icon {
  background: var(--danger);
  color: var(--bg);
}

.alert__body {
  color: var(--text-soft);
  margin-top: 2px;
  font-size: 14px;
}

/* Loading card --------------------------------------------------- */

.loading-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elev);
}

.loading-card__pulse {
  display: flex;
  gap: 6px;
  align-items: flex-end;
  height: 20px;
}

.loading-card__pulse span {
  display: block;
  width: 6px;
  border-radius: 4px;
  background: var(--accent);
  animation: app-bars 1s ease-in-out infinite;
}

.loading-card__pulse span:nth-child(1) {
  height: 60%;
  animation-delay: -0.2s;
}

.loading-card__pulse span:nth-child(2) {
  height: 100%;
  animation-delay: -0.1s;
}

.loading-card__pulse span:nth-child(3) {
  height: 80%;
}

@keyframes app-bars {
  0%, 100% {
    transform: scaleY(0.6);
    opacity: 0.6;
  }
  50% {
    transform: scaleY(1);
    opacity: 1;
  }
}

.loading-card__text strong {
  display: block;
  font-weight: 600;
  color: var(--text);
}

.loading-card__text p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 14px;
}

/* Footer --------------------------------------------------------- */

.app__footer {
  margin-top: auto;
  padding-top: 28px;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 13px;
}

/* Responsive ---------------------------------------------------- */

@media (max-width: 640px) {
  .app {
    padding: 32px 16px 40px;
    gap: 28px;
  }

  .picker {
    padding: 20px 18px;
  }

  .picker__submit {
    width: 100%;
    min-width: 0;
  }

  .picker__add {
    width: 100%;
    justify-content: center;
  }
}
</style>
