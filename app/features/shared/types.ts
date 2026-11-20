export type PromptTemplate = {
  id: string;
  kind: "writing" | "cover";
  name: string;
  text: string;
  image_sizes?: string[];
};

export type Asset = {
  prompt_id?: string | null;
  orientation?: "landscape" | "portrait";
  template_id?: string;
  url: string;
  voice?: string;
  speech_rate?: number;
  prompt?: string;
  prompt_name?: string;
  image_ratio?: string;
  resolution?: string;
  duration?: number;
  draft_id?: string;
};
export type SubtitleTrack = { draft_id: string; voice: string; srt_url: string; txt_url: string; json_url: string };

export type Draft = { id: string; prompt: string; text: string };
export type VoiceItem = {
  short_name: string;
  locale: string;
  locale_name: string;
  local_name: string;
  display_name: string;
  gender: string;
  voice_type: string;
  status: string;
  sample_rate_hertz: string;
  styles: string[];
  roles: string[];
  secondary_locales: string[];
  scenarios: string[];
  personalities: string[];
};
export type BackgroundMusic = { id: string; name: string; url: string; category: string; created_at: number; is_default: boolean };
export type SubtitleStyle = {
  font_id: string;
  font_size: number; text_color: string; bold: boolean; mode: "box" | "outline";
  background_color: string; background_opacity: number; outline_color: string; outline_width: number;
  position: "top" | "center" | "bottom"; margin_horizontal: number; margin_vertical: number | null;
};
export type RequestLog = { id: number; request_type: string; request_url: string; request_params: Record<string, unknown>; created_at: number };
export type WorkspacePage = "workspace" | "prompts" | "models" | "voice" | "video" | "logs";
export type AppSettings = { background_blur_enabled: boolean; background_blur_strength: number; background_overlay_enabled: boolean; background_overlay_opacity: number; record_label_image_id?: string | null; text_api_base: string; text_api_key: string; image_api_base: string; image_api_key: string; model: string; image_model: string; azure_speech_key: string; azure_speech_base: string; voice_format: string; voices: string[]; speech_rate: number; video_orientation: "landscape" | "portrait"; burn_subtitles: boolean; subtitle_style: SubtitleStyle; video_generation_method: "local" | "stock"; stock_video_provider: "pexels" | "pixabay"; pexels_api_base: string; pexels_api_key: string; pixabay_api_base: string; pixabay_api_key: string };
export type Workflow = {
  local_cover?: boolean;
  id: string; book_title: string; author: string; edition: string; status: string;
  step: number; progress: number; created_at: number; updated_at?: number; description?: string; error?: string;
  video_regenerating?: boolean; video_error?: string;
  audio_regenerating?: boolean; audio_error?: string;
  output_dir?: string; tags?: string[]; topics?: string[]; original_drafts?: Draft[]; polished_drafts?: Draft[]; covers?: Asset[]; audio?: Asset[]; subtitles?: SubtitleTrack[]; videos?: Asset[]; cover_prompts?: PromptTemplate[];
};
