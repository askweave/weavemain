"""Structured contracts between Genesis and Gemini, and between the API and the dashboard."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

PACKAGE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}(\.[a-z][a-z0-9_]{1,30}){1,4}$")
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
# Kotlin and Java keywords cannot be package segments.
RESERVED_SEGMENTS = {
    "as", "break", "class", "continue", "do", "else", "false", "for", "fun", "if", "in", "interface",
    "is", "null", "object", "package", "return", "super", "this", "throw", "true", "try", "typealias",
    "typeof", "val", "var", "when", "while", "abstract", "boolean", "byte", "case", "catch", "char",
    "default", "double", "enum", "extends", "final", "finally", "float", "goto", "implements", "import",
    "instanceof", "int", "long", "native", "new", "private", "protected", "public", "short", "static",
    "switch", "synchronized", "throws", "transient", "void", "volatile", "const", "assert", "strictfp",
}


class ThemeMode(str, Enum):
    system = "system"
    light = "light"
    dark = "dark"


class AppCategory(str, Enum):
    calculator = "calculator"
    habit_tracker = "habit_tracker"
    flashcards = "flashcards"
    workout_tracker = "workout_tracker"
    todo_list = "todo_list"


# Dependencies the protected template already provides. The model may only *declare* these;
# it can never add new ones (build.gradle.kts is server-controlled).
ALLOWED_DEPENDENCIES = {
    "compose-material3",
    "compose-foundation",
    "compose-ui",
    "material-icons-core",
    "activity-compose",
    "lifecycle-viewmodel-compose",
    "lifecycle-runtime-ktx",
    "core-ktx",
}


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(description="Path relative to app/src/main/java/com/genesis/app/, e.g. 'GenesisApp.kt' or 'data/Store.kt'")
    content: str = Field(description="Complete Kotlin source of the file")


class AppManifest(BaseModel):
    """What Gemini must return for a generation request."""

    model_config = ConfigDict(extra="forbid")
    app_name: str = Field(min_length=1, max_length=30)
    package_id: str = Field(description="Android applicationId, e.g. com.genesis.gymtracker")
    category: AppCategory
    description: str = Field(min_length=1, max_length=400)
    features: list[str] = Field(min_length=1, max_length=12)
    primary_color: str = Field(description="Brand color as #RRGGBB")
    theme_mode: ThemeMode = Field(default=ThemeMode.system, description="'system' (default), 'light' or 'dark'")
    dependencies: list[str] = Field(default_factory=list, description="Subset of the allowed dependency keys")
    validation_rules: list[str] = Field(default_factory=list, max_length=12,
                                        description="Checks a reviewer should verify in the generated app")
    files: list[GeneratedFile] = Field(min_length=1)

    @field_validator("app_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"[\w][\w .&'+-]{0,29}", v, flags=re.UNICODE):
            raise ValueError("app_name contains unsupported characters")
        return v

    @field_validator("package_id")
    @classmethod
    def _package(cls, v: str) -> str:
        v = v.strip()
        if not PACKAGE_ID_RE.fullmatch(v):
            raise ValueError("package_id must look like com.example.app (lowercase, 2-5 segments)")
        if any(seg in RESERVED_SEGMENTS for seg in v.split(".")):
            raise ValueError("package_id uses a reserved keyword")
        return v

    @field_validator("primary_color")
    @classmethod
    def _color(cls, v: str) -> str:
        v = v.strip()
        if not HEX_COLOR_RE.fullmatch(v):
            raise ValueError("primary_color must be #RRGGBB")
        return v.upper()

    @field_validator("dependencies")
    @classmethod
    def _deps(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - ALLOWED_DEPENDENCIES)
        if unknown:
            raise ValueError(f"dependencies not allowed: {unknown}")
        return v

    @field_validator("features", "validation_rules")
    @classmethod
    def _short_items(cls, v: list[str]) -> list[str]:
        return [item.strip()[:200] for item in v if item.strip()]


class RepairPatch(BaseModel):
    """Minimal patch Gemini returns for a failed compile: whole-file replacements only."""

    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(max_length=1000)
    files: list[GeneratedFile] = Field(min_length=1)


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=10, max_length=4000)
    app_name: str | None = Field(default=None, max_length=30)

    @field_validator("prompt")
    @classmethod
    def _prompt(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Describe the app in at least 10 characters")
        return v

    @field_validator("app_name")
    @classmethod
    def _app_name(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if not re.fullmatch(r"[\w][\w .&'+-]{0,29}", v, flags=re.UNICODE):
            raise ValueError("App name may use letters, numbers, spaces and . & ' + -")
        return v
