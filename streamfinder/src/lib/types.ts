export interface TitleIndex {
	id: number;
	slug: string;
	title: string;
	title_en: string | null;
	year: number | null;
	rating: number | null;
	votes_count: number | null;
	runtime_min: number | null;
	title_type: string | null;
	vod_date: string | null;
	poster: string | null;
	genres: string[];
	tags: string[];
	countries: string[];
	platforms: string[];
	crew_ids: number[];
	link: string;
	// Hierarchy — Work vs. Release
	root_id: number | null;
	root_title_id: number | null; // top-level work's title_id (null when this row IS the work)
	is_toplevel: boolean;
	season_no: number | null;
	episode_no: number | null;
	// Rating borrowed from the série/seriál when an episode has no own rating yet.
	inherited_rating?: number;
	inherited_from?: 'série' | 'seriál';
	// Serial shape — present on top-level serial/pořad cards
	season_count?: number;
	episode_count?: number;
	first_vod_date?: string | null;
	last_vod_date?: string | null;
	is_running?: boolean;
	cadence_days?: number | null;
}

export interface TitleDetail extends TitleIndex {
	plot: string | null;
	backdrop: string | null;
	trailer_youtube_id: string | null;
	age_rating: string | null;
	directors: string[];
	actors: string[];
	screenwriters: string[];
	cinematographers: string[];
	composers: string[];
	reviews: Review[];
	vods: Vod[];
	episodes?: EpisodeRelease[]; // release timeline on top-level serials
}

export interface EpisodeRelease {
	season_no: number | null;
	episode_no: number | null;
	vod_date: string | null;
	title: string;
	platforms: string[];
}

export interface Review {
	author: string | null;
	text: string | null;
	stars: number | null;
}

export interface Vod {
	platform: string;
	url: string | null;
}

export interface Dimensions {
	genres: DimEntry[];
	tags: DimEntry[];
	countries: DimEntry[];
	platforms: DimEntry[];
	crew: CrewDimEntry[];
}

export interface DimEntry {
	name: string;
	count: number;
}

export interface CrewDimEntry {
	name: string;
	role: string;
	count: number;
}

export interface CrewEntry {
	id: number;
	name: string;
	role: string;
	count: number;
}
