export interface TitleHit {
  imdb_id: string
  title: string
  year: number | null
  kind: string | null
  poster_url: string | null
}

export interface TitleSummary {
  imdb_id: string
  title: string
  year: number | null
  kind: string | null
  poster_url: string | null
}

export interface EpisodeAppearance {
  imdb_id: string
  season: number
  episode: number
  title: string
}

export interface ActorEpisodesResult {
  title_id: string
  person_id: string
  episodes: EpisodeAppearance[]
}

export interface SharedActor {
  imdb_id: string
  name: string
  headshot_url: string | null
  // roles[i] and episodes[i] correspond to titles[i] in OverlapResult.
  roles: (string | null)[]
  episodes: (number | null)[]
}

export interface OverlapResult {
  titles: TitleSummary[]
  shared: SharedActor[]
}
