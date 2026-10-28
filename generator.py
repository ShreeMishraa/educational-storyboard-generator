"""
Brick 3: Master Prompt Builder & PDF Exporter.
Builds image generation prompts that faithfully reflect the client's specific
visual instructions (captured from their briefing video + script) rather than
applying generic hardcoded templates.
"""

import os
import re
import json
from fpdf import FPDF


def sanitize_text(text: str) -> str:
    if not text:
        return "NA"
    replacements = {
        '•': '-', '–': '-', '—': '-', '\u201c': '"', '\u201d': '"',
        '\u2018': "'", '\u2019': "'", '\u2026': '...'
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    return text.encode('latin-1', 'replace').decode('latin-1')


def clean_text_descriptors(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"\b(clear|lush|ripe|green)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_image_prompt(panel_spec: dict, global_style_override: str = None) -> str:
    """
    Builds a rich image generation prompt derived from the panel's AI-generated
    specifications, which themselves reflect the client's video/audio instructions.

    The prompt faithfully passes through the client-driven visual_description
    and enriches it with structural composition and text overlay directives.
    """
    layout = panel_spec.get("canvas_layout", {})
    vis_desc = clean_text_descriptors(layout.get("visual_description", ""))
    shot_type = panel_spec.get("shot_type", "Mid Shot")
    layout_mode = layout.get("layout_mode", "full_bleed")
    scene_str = (panel_spec.get("scene") or "").upper()
    client_notes = clean_text_descriptors(panel_spec.get("client_visual_notes", ""))

    # --- 1. Dynamic Aesthetic Style Detection ---
    combined_check_text = (vis_desc + " " + (global_style_override or "")).lower()
    is_explicit_monochrome = any(
        k in combined_check_text for k in [
            "monochrome", "grayscale", "black and white",
            "line art", "pencil sketch", "line-art"
        ]
    )

    if global_style_override:
        style_anchor = f"Aesthetic Style: {global_style_override}. 16:9 widescreen image."
    elif is_explicit_monochrome:
        style_anchor = (
            "Aesthetic Style: Fine black and white line-art pencil and ink illustration, "
            "crisp graphite linework, detailed hatching, high contrast, clean white "
            "background, 16:9 widescreen image."
        )
    else:
        style_anchor = (
            "Aesthetic Style: High quality 16:9 widescreen educational digital artwork, "
            "vivid colors, crisp graphic illustration, clean lighting, clear visual hierarchy."
        )

    # --- 2. Image Framing & Composition ---
    comp_parts = []
    if layout_mode == "split_3way" or "3-way" in vis_desc.lower() or "three-way" in vis_desc.lower():
        comp_parts.append(
            "Composition: 3-way vertical split screen layout divided into three equal "
            "side-by-side panels separated by thin neat black border lines."
        )
    elif layout_mode == "split_2way" or "split" in vis_desc.lower():
        comp_parts.append(
            "Composition: 2-way vertical split screen layout divided into two equal "
            "side-by-side panels separated by a neat dividing line."
        )
    elif layout_mode == "presenter_with_mog_inset" or "MOG" in shot_type:
        comp_parts.append(
            "Composition: Split layout. Left side shows the presenter; right side features "
            "a distinct floating graphic illustration card on a clean background."
        )
    elif shot_type == "Mid Shot":
        comp_parts.append("Composition: Centered mid shot framing with subject clearly in focus.")
    elif shot_type in ["FSA", "Full Screen Graphic", "Title card", "TOS 1"]:
        comp_parts.append(
            f"Composition: Full screen infographic card layout ({shot_type}) "
            "designed for educational clarity."
        )
    else:
        comp_parts.append(f"Composition: {shot_type} framing with balanced subject placement.")

    # --- 3. Scene Setting ---
    detail_parts = []
    if scene_str and scene_str != "NA":
        detail_parts.append(f"Setting & Scene: {scene_str}.")

    # --- 4. Client-Driven Visual Description (the core content) ---
    # This is the most important section: it carries the AI's detailed description
    # which was generated from watching the client's video frames + listening to
    # their Hindi audio + reading the script. Pass it through faithfully.
    if vis_desc:
        detail_parts.append(f"Visual Details: {vis_desc}")

    # --- 5. Client's Direct Visual Notes (cross-reference from video) ---
    if client_notes:
        detail_parts.append(f"Client Direction: {client_notes}")

    # --- 6. Presenter Information ---
    presenter = panel_spec.get("presenter", {})
    if presenter.get("is_present", False):
        pres_parts = []
        position = presenter.get("position", "center")
        dialogue = presenter.get("dialogue", "NA")
        audio_mode = presenter.get("audio_mode", "SYNC")

        pres_parts.append(f"Presenter visible on screen, positioned at {position}.")
        if dialogue and dialogue != "NA":
            pres_parts.append(f"Speaking ({audio_mode}): \"{dialogue}\"")
        detail_parts.append("Presenter: " + " ".join(pres_parts))

    # --- 7. On-Screen Text Overlay Badges ---
    text_directives = []
    tos_items = panel_spec.get("text_overlays", [])
    if tos_items:
        for t in tos_items:
            if isinstance(t, dict):
                badge_type = t.get("badge_type", "tos_yellow_pill")
                badge_text = clean_text_descriptors(t.get("text", ""))
                if badge_text:
                    text_directives.append(
                        f'On-Screen Text ({badge_type}): Render a clean graphic text badge '
                        f'displaying EXACT text: "{badge_text}". Typography must be bold, '
                        f'highly legible, and prominent.'
                    )
            else:
                badge_text = clean_text_descriptors(str(t))
                if badge_text:
                    text_directives.append(
                        f'On-Screen Text: Render a clean graphic text badge displaying '
                        f'EXACT text: "{badge_text}". Bold, legible typography.'
                    )

    if not text_directives:
        text_directives.append(
            "On-Screen Text Elements: No additional text overlays in this panel."
        )

    # --- 8. Image Quality Constraints ---
    constraints = [
        "Constraints: High visual clarity, centered composition, no watermarks, "
        "no logos, no camera gear, no video production artifacts, no unintended text."
    ]

    # --- Assemble the complete prompt ---
    full_prompt_sections = [
        style_anchor,
        " ".join(comp_parts),
        " ".join(detail_parts),
        "\n".join(text_directives),
        " ".join(constraints)
    ]

    return "\n\n".join([s for s in full_prompt_sections if s]).strip()


class StoryboardPromptPDF(FPDF):
    def get_effective_width(self):
        """Calculates page printable width safely across FPDF versions."""
        return self.w - 2 * self.l_margin

    def header(self):
        epw = self.get_effective_width()
        self.set_font('Helvetica', 'B', 14)
        self.cell(epw, 10, 'Master Storyboard Panel Prompts', border=0, ln=1, align='C')
        self.set_font('Helvetica', 'I', 10)
        self.cell(epw, 5, 'Client Approved 16:9 Visual Specifications', border=0, ln=1, align='C')
        self.ln(5)

    def footer(self):
        epw = self.get_effective_width()
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(epw, 10, f'Page {self.page_no()}', border=0, ln=1, align='C')


def generate_prompts_pdf(plan_data: dict, output_pdf_path: str = "output/all_storyboard_prompts.pdf") -> str:
    pdf = StoryboardPromptPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    title = sanitize_text(plan_data.get("title", "Storyboard Script"))
    panels = plan_data.get("panels", [])

    pdf.add_page()
    epw = pdf.get_effective_width()

    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(epw, 8, f"Document: {title}", ln=1)
    pdf.cell(epw, 8, f"Total Panels: {len(panels)}", ln=1)
    pdf.ln(5)

    for panel in panels:
        pid = panel.get("panel_id")
        shot_type = sanitize_text(panel.get("shot_type", "FSA"))
        scene = sanitize_text(panel.get("scene", "NA"))

        presenter = panel.get("presenter", {})
        dialogue = sanitize_text(presenter.get("dialogue", "NA"))
        audio_mode = sanitize_text(presenter.get("audio_mode", "SYNC"))

        layout = panel.get("canvas_layout", {})
        visual_desc = sanitize_text(layout.get("visual_description", ""))

        client_notes = sanitize_text(panel.get("client_visual_notes", ""))
        prompt = sanitize_text(build_image_prompt(panel))

        # Panel Header Box
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.cell(epw, 8, f" PANEL {pid:03d} | Shot: {shot_type} | Scene: {scene}", border=1, fill=True, ln=1)

        pdf.set_font('Helvetica', '', 10)
        if dialogue != "NA":
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 5, f"Dialogue ({audio_mode}): {dialogue}")
        if visual_desc:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 5, f"Visual Notes: {visual_desc}")

        # Show client's direct visual notes from the video
        if client_notes and client_notes != "NA":
            pdf.set_font('Helvetica', 'I', 9)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(epw, 5, f"Client Direction (from video): {client_notes}")
            pdf.set_font('Helvetica', '', 10)

        tos_items = panel.get("text_overlays", [])
        if tos_items:
            tos_str = " | ".join([sanitize_text(t['text'] if isinstance(t, dict) else t) for t in tos_items])
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_x(pdf.l_margin)
            pdf.cell(epw, 6, f"TOS Badge: {tos_str}", ln=1)

        pdf.ln(2)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_x(pdf.l_margin)
        pdf.cell(epw, 5, "COPY-PASTE IMAGE GENERATION PROMPT:", ln=1)

        pdf.set_font('Courier', '', 8)
        pdf.set_fill_color(248, 248, 248)
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(epw, 4, prompt, border=1, fill=True)
        pdf.ln(6)

    os.makedirs(os.path.dirname(output_pdf_path) or ".", exist_ok=True)
    pdf.output(output_pdf_path)
    return output_pdf_path
