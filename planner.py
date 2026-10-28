"""
Brick 2: Multimodal Script & Video Storyboard Director.
Uploads the client's briefing video DIRECTLY to Gemini Files API so it can
see the slides AND hear the Hindi audio in a SINGLE generate_content call.

Free-tier optimized:
  - 1 file upload  (video or audio)
  - 1 generate_content call
  = 2 total API interactions
"""

import os
import time
import json
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from parser import (
    parse_script_to_panels,
    extract_audio_from_video,
    should_upload_video_directly,
)

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
    visual_description: str = Field(
        description="Exhaustive visual composition describing EVERY element the client "
        "showed or described: exact characters, props, backgrounds, color palettes, "
        "graphic card layouts, icon placements, text badge positions, zoom levels, "
        "arrows, highlights, and all action — strictly derived from matching the "
        "client video frames and Hindi audio instructions to the script."
    )


class PanelPlanItem(BaseModel):
    panel_id: int = Field(description="Sequential 1-based panel number")
    shot_type: str = Field(description="Mid Shot, FSA, MOG, Title card, Summary, Split screen, Close Up")
    scene: str = Field(description="Scene slugline extracted or inferred from script e.g. INT. STUDIO - DAY, INT. CLASSROOM - DAY, EXT. LOCATION - DAY, or NA")
    presenter: PresenterSpec
    canvas_layout: CanvasLayout
    text_overlays: List[TextOverlay] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list, description="Reference tags e.g. ['ref 1']")
    client_visual_notes: str = Field(
        default="",
        description="Direct notes from the client video/audio about how this specific "
        "panel should look — transcribed or paraphrased from the Hindi instructions."
    )


class StoryboardPlan(BaseModel):
    title: str
    script_code: Optional[str] = None
    total_panels: int
    panels: List[PanelPlanItem]


MULTIMODAL_STORYBOARD_DIRECTOR_PROMPT = """
You are a professional educational storyboard director. You have been given:
  1. A written SCRIPT document with scene directions, visual cues (FSA, MOG, TOS badges, split screens), and presenter dialogue.
  2. A CLIENT BRIEFING VIDEO / AUDIO file — the client explains in Hindi exactly how each scene should look, showing slides and visual references on screen while speaking.

YOUR TASK — STRICT RULES:

A) WATCH + LISTEN CAREFULLY:
   - If a VIDEO file is attached: examine the visual frames (they show the client's desired slide layouts, reference artwork, graphic compositions). ALSO listen to the Hindi audio track for the client's spoken instructions.
   - If only AUDIO is attached: listen to the complete Hindi audio — the client explains shot-by-shot what they want.
   - Cross-reference what you SEE and HEAR with the written script. The client's briefing follows the script sequentially.

B) MATCH CLIENT INSTRUCTIONS TO SCRIPT BEATS:
   - Map each segment of the client's video/audio explanation to the corresponding section of the written script.
   - When the client describes a specific visual (e.g., "yahan pe ek airplane dikhana hai", "is slide mein split screen hoga"), capture that EXACT instruction and apply it to the matching script beat.
   - If the client shows a specific reference image or slide layout on screen, describe that EXACT visual composition in the panel's visual_description — do NOT invent your own layout.

C) PANEL GENERATION RULES:
   1. Generate one panel for every distinct visual beat. A "beat" changes whenever:
      - The visual composition changes (new graphic, new layout, new character position)
      - A new text overlay (TOS badge) appears on screen
      - The script explicitly marks a new scene (FSA, MOG, INSERT, TOS directive)
      - The client describes a new visual element appearing
   2. For multi-step sequences (progressive bullet builds, step-by-step reveals), create SEPARATE consecutive panels for each step.
   3. Break physical actions into individual panels.
   4. Capture EVERY TOS badge text EXACTLY as written in the script.

D) VISUAL DESCRIPTION QUALITY:
   - Each panel's visual_description must be a COMPLETE, self-contained image prompt.
   - Include: exact subject(s), pose/action/expression, clothing, props, background, color palette, lighting, camera framing, graphic overlays, arrows, icons, text badges, and layout structure.
   - If the client showed a specific style (colorful illustration, line art, monochrome), state that explicitly.
   - NEVER use vague descriptions like "appropriate visual" or "relevant image". Be exhaustively specific.

E) CLIENT VISUAL NOTES:
   - For each panel, populate client_visual_notes with what the client specifically said (paraphrased Hindi to English) about that visual.

F) CONTINUITY:
   - Maintain character appearance, clothing, setting, and prop consistency across panels.

Generate approximately 55-75 panels for a standard educational script. Output valid JSON matching the schema.
"""


def plan_storyboard(
    parsed_doc: dict,
    media_file_path: Optional[str] = None,
    client=None,
    model_name: Optional[str] = None
) -> Dict[str, Any]:

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
    uploaded_file = None

    # --- SINGLE FILE UPLOAD STRATEGY (free-tier optimized) ---
    #
    # Option A: Video is small enough → upload the MP4 directly.
    #           Gemini sees the frames AND hears the audio in one file.
    #           Cost: 1 upload + 1 generate_content = 2 API calls total.
    #
    # Option B: Video is too large OR file is audio-only → extract MP3,
    #           upload that. Gemini hears the instructions but doesn't
    #           see the slides. Still 1 upload + 1 generate = 2 API calls.

    if media_file_path and os.path.exists(media_file_path):
        if should_upload_video_directly(media_file_path):
            # OPTION A: Direct video upload — full multimodal (frames + audio)
            file_to_upload = media_file_path
            file_size_mb = os.path.getsize(media_file_path) / (1024 * 1024)
            print(f"Uploading video directly to Gemini ({file_size_mb:.1f} MB) — AI will see slides + hear audio...")
            contents.append(
                "[CLIENT BRIEFING VIDEO] This video contains the client's screen recording "
                "where they walk through the script. WATCH the visual frames — they show the "
                "exact slide layouts, graphic compositions, and reference art the client wants. "
                "LISTEN to the Hindi audio — the client explains each scene's requirements. "
                "Match what you see and hear to the script below."
            )
        else:
            # OPTION B: Extract audio only (large video or audio-only file)
            file_to_upload = extract_audio_from_video(media_file_path)
            print(f"Uploading audio to Gemini — AI will hear Hindi instructions...")
            contents.append(
                "[CLIENT HINDI AUDIO] Listen to the COMPLETE audio. The client explains in "
                "Hindi how each scene should look — visual elements, character placements, "
                "graphic styles, colors, and layout preferences. Match the instructions to "
                "the script below."
            )

        uploaded_file = client.files.upload(file=file_to_upload)

        # Wait until file processing completes
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        contents.append(uploaded_file)

    # Add the script text and director prompt
    prompt = f"{MULTIMODAL_STORYBOARD_DIRECTOR_PROMPT}\n\n=== SOURCE SCRIPT ===\n{script_text}"
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
