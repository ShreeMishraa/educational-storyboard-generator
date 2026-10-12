"""
Brick 2: Multimodal Script & Video Storyboard Director.
Parses script input alongside uploaded Hindi client instruction audio/video files
using gemini-2.5-flash or gemini-2.0-flash.
"""

import os
import time
import json
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from parser import parse_script_to_panels, extract_audio_from_video

load_dotenv()


class TextOverlay(BaseModel):
    badge_type: str = Field(description="tos_yellow_pill, title_header, summary_bullet, step_header")
    text: str = Field(description="Exact on-screen text to display")


class PresenterSpec(BaseModel):
    is_present: bool = Field(description="Whether presenter is visually visible in frame")
    audio_mode: str = Field(description="SYNC, V.O., or NA")
    position: str = Field(description="center, left_third, or NA")
    dialogue: str = Field(description="Exact presenter line spoken in this frame, or NA")


class CanvasLayout(BaseModel):
    layout_mode: str = Field(description="full_bleed, presenter_with_mog_inset, split_2way, split_3way, title_card")
    visual_description: str = Field(description="Rich visual composition describing characters, props, background, zoom levels, overlays, and action strictly derived from the script and client video")


class PanelPlanItem(BaseModel):
    panel_id: int = Field(description="Sequential 1-based panel number")
    shot_type: str = Field(description="Mid Shot, FSA, MOG, Title card, Summary, Split screen, Close Up")
    scene: str = Field(description="Scene slugline extracted or inferred from script e.g. INT. STUDIO - DAY, INT. CLASSROOM - DAY, EXT. LOCATION - DAY, or NA")
    presenter: PresenterSpec
    canvas_layout: CanvasLayout
    text_overlays: List[TextOverlay] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list, description="Reference tags e.g. ['ref 1']")


class StoryboardPlan(BaseModel):
    title: str
    script_code: Optional[str] = None
    total_panels: int
    panels: List[PanelPlanItem]


GENERIC_STORYBOARD_DIRECTOR_PROMPT = """
You are a professional educational storyboard director. You have been provided a script document and an attached client explanation file (containing spoken Hindi instructions/video explanations).

STRICT DIRECTORIAL RULES:
1. Listen carefully to the attached client spoken Hindi instructions. Extract every specific requirement mentioned by the client (layout, asset placement, color choices vs. line-art, character gestures, graphic cards).
2. Cross-reference the Hindi client instructions with the written script beats to build a granular frame-by-frame storyboard (~55 to 65 panels for a standard educational script).
3. Break down physical multi-step actions into consecutive individual panels.
4. Every time a list item or bullet point is spoken, create a dedicated build panel showing progressive on-screen text/graphic additions.
5. If comparisons or split visuals are described, assign layout_mode 'split_2way' or 'split_3way'.
6. Translate dynamic motion notes (camera zooms, icon popups) into static video-frame visual diagrams (highlight glows, thought bubbles, arrows, crossed icons).
7. Ensure seamless character, prop, and setting continuity across consecutive panels so the images can be compiled directly into a video.
"""


def plan_storyboard(parsed_doc: dict, media_file_path: Optional[str] = None, client=None, model_name: Optional[str] = None) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_actual_api_key_here":
        return {
            "title": parsed_doc.get("title", "Storyboard Script"),
            "total_panels": 0,
            "panels": []
        }

    if client is None:
        from google import genai
        client = genai.Client(api_key=api_key)

    if model_name is None:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    paragraphs = parsed_doc.get("raw_paragraphs", [])
    ref_images_map = parsed_doc.get("ref_images_map", {})
    script_text = "\n".join(paragraphs)

    contents = []

    # Upload extracted audio/video to Gemini Files API if provided
    uploaded_file = None
    if media_file_path and os.path.exists(media_file_path):
        audio_file_path = extract_audio_from_video(media_file_path)
        print(f"Uploading media file to Gemini API: {audio_file_path}...")
        uploaded_file = client.files.upload(file=audio_file_path)
        
        # Wait until file processing completes if necessary
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        contents.append(uploaded_file)

    prompt = f"{GENERIC_STORYBOARD_DIRECTOR_PROMPT}\n\n=== SOURCE SCRIPT ===\n{script_text}"
    contents.append(prompt)

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_schema": StoryboardPlan,
                "temperature": 0.1
            }
        )
        plan_dict = json.loads(response.text)
    finally:
        # Clean up uploaded file from Gemini storage
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

    # Attach extracted reference image paths
    for panel in plan_dict.get("panels", []):
        ref_paths = []
        for r in panel.get("references", []):
            clean_r = r.strip("()").lower()
            if clean_r in ref_images_map:
                ref_paths.append(ref_images_map[clean_r])
        panel["ref_image_paths"] = ref_paths

    return plan_dict