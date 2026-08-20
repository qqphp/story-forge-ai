export type PromptTemplate = {
  id: string;
  kind: "writing" | "cover";
  name: string;
  text: string;
  image_sizes?: string[];
};

export type Asset = {
  url: string;
  voice?: string;
  speech_rate?: number;
  prompt?: string;
  prompt_name?: string;
  image_ratio?: string;
  resolution?: string;
  draft_id?: string;
};

export type Draft = { id: string; prompt: string; text: string };
export type VoiceItem = { short_name: string; locale: string; local_name: string; display_name: string; gender: string };
export type BackgroundMusic = { id: string; name: string; url: string; category: string; created_at: number };
export type RequestLog = { id: number; request_type: string; request_url: string; request_params: Record<string, unknown>; created_at: number };
export type PublishPlatform = "douyin" | "kuaishou" | "bilibili" | "xiaohongshu" | "baijiahao";
export type PublishTask = { id: string; workflow_id: string; book_title: string; platform: PublishPlatform; status: string; title: string; description: string; tags: string[]; topics: string[]; video_url: string; cover_url: string; covers: Asset[]; created_at: number; updated_at: number; error: string };
export type WorkspacePage = "workspace" | "publish" | "prompts" | "models" | "voice" | "logs";
export type AppSettings = { api_base: string; model: string; image_model: string; api_key: string; azure_speech_key: string; azure_speech_region: string; voice_format: string; voices: string[]; speech_rate: number };
export type Workflow = {
  id: string; book_title: string; author: string; edition: string; status: string;
  step: number; progress: number; created_at: number; description?: string; error?: string;
  output_dir?: string; tags?: string[]; topics?: string[]; original_drafts?: Draft[]; polished_drafts?: Draft[]; covers?: Asset[]; audio?: Asset[]; videos?: Asset[]; cover_prompts?: PromptTemplate[];
};
