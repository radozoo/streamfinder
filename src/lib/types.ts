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
	link: string;
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
}

export interface DimEntry {
	name: string;
	count: number;
}
