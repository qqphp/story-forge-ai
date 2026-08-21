"""Transport contracts shared by HTTP route modules.

Keeping validation models outside the application entry point makes HTTP
interfaces explicit and avoids coupling business code to FastAPI setup.
"""

from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class PromptItem(BaseModel):
    text: str
    enabled: bool = True


class WorkflowOptions(BaseModel):
    writing_prompt_ids: list[str] = Field(default_factory=list)
    cover_prompt_ids: list[str] = Field(default_factory=list)
    voice: str = Field(default="zh-CN-XiaoxiaoNeural", min_length=1, max_length=120)
    speech_rate: int = Field(default=0, ge=-50, le=100)
    background_music_id: str | None = Field(default=None, max_length=40)
    background_music_volume: float = Field(default=.2, ge=0, le=1)
    background_music_fade_in: float = Field(default=2, ge=0, le=10)
    background_music_fade_out: float = Field(default=2, ge=0, le=10)


class BookCreate(BaseModel):
    book_title: str = Field(min_length=1, max_length=160)
    author: str = Field(default="", max_length=120)
    edition: str = Field(default="", max_length=120)


class WorkflowCreate(WorkflowOptions, BookCreate):
    pass


class BatchWorkflowCreate(WorkflowOptions):
    books: list[BookCreate] = Field(min_length=1, max_length=50)


MAX_PROMPT_LENGTH = 100_000
DEFAULT_IMAGE_SIZES = ["16:9", "9:16"]
IMAGE_SIZES = {"1:1", "4:5", "2:3", "3:4", "9:16", "6:7", "1.91:1", "2.35:1", "3:2", "4:3", "16:9"}


class PromptTemplateCreate(BaseModel):
    kind: str = Field(pattern="^(writing|cover)$")
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    image_sizes: list[str] = Field(default_factory=lambda: list(DEFAULT_IMAGE_SIZES), max_length=len(IMAGE_SIZES))

    @field_validator("image_sizes")
    @classmethod
    def validate_image_sizes(cls, values: list[str]) -> list[str]:
        values = list(dict.fromkeys(values))
        if not values or any(value not in IMAGE_SIZES for value in values):
            raise ValueError("图片尺寸无效")
        return values


class PromptTemplateUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    image_sizes: list[str] = Field(default_factory=lambda: list(DEFAULT_IMAGE_SIZES), max_length=len(IMAGE_SIZES))

    @field_validator("image_sizes")
    @classmethod
    def validate_image_sizes(cls, values: list[str]) -> list[str]:
        return PromptTemplateCreate.validate_image_sizes(values)


class SettingsPayload(BaseModel):
    api_base: str = "https://api.teamorouter.com/v1"
    model: str = "gpt-5.4-mini"
    image_model: str = "gpt-image-2"
    api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = "eastus"
    voice_format: str = "audio-24khz-48kbitrate-mono-mp3"
    voices: list[str] = ["zh-CN-XiaoxiaoNeural"]
    speech_rate: int = Field(default=0, ge=-50, le=100)
    video_orientation: str = Field(default="portrait", pattern="^(landscape|portrait)$")
    video_generation_method: str = Field(default="local", pattern="^(local|stock)$")
    stock_video_provider: str = Field(default="pexels", pattern="^(pexels|pixabay)$")
    pexels_api_base: str = "https://api.pexels.com/v1/videos/search"
    pexels_api_key: str = ""
    pixabay_api_base: str = "https://pixabay.com/api/videos/"
    pixabay_api_key: str = ""

    @field_validator("pexels_api_base", "pixabay_api_base")
    @classmethod
    def require_stock_api_https(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("无版权视频 API 地址必须使用 https")
        return value


class PublishTaskCreate(BaseModel):
    workflow_id: str = Field(min_length=1, max_length=40)
    platform: str = Field(default="douyin", pattern="^(douyin|kuaishou|bilibili|xiaohongshu|baijiahao)$")
    title: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=10)
    topics: list[str] = Field(default_factory=list, max_length=10)
    video_url: str = Field(default="", max_length=1000)
    cover_urls: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().lstrip("#").strip() for value in values]
        cleaned = [value for value in cleaned if value]
        if any(len(value) > 30 for value in cleaned):
            raise ValueError("单个话题不能超过30个字符")
        return list(dict.fromkeys(cleaned))

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().lstrip("#").strip() for value in values]
        cleaned = [value for value in cleaned if value]
        if any(len(value) > 20 for value in cleaned):
            raise ValueError("单个标签不能超过20个字符")
        return list(dict.fromkeys(cleaned))

    @field_validator("cover_urls")
    @classmethod
    def clean_cover_urls(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class PublishTaskStatusUpdate(BaseModel):
    status: str = Field(pattern="^(filling|ready|completed|failed)$")
    error: str = Field(default="", max_length=500)


class BackgroundMusicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="", max_length=80)

    @field_validator("url")
    @classmethod
    def require_https(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise ValueError("背景音乐链接必须使用 https")
        return value
