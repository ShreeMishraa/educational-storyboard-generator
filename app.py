import os
import json
import shutil
import streamlit as st
from parser import parse_script_to_panels
from planner import plan_storyboard
from generator import generate_prompts_pdf, build_image_prompt

st.set_page_config(page_title="AI Storyboard Generator", layout="wide")
st.title("🎬 Multimodal Educational Storyboard Pipeline")
st.write("Upload your script file (.docx/.pdf), visual reference file (.pdf/.docx), and client Hindi video/audio instructions (.mp4/.mp3).")

input_dir = "input"
output_dir = "output"
os.makedirs(input_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# --- SIDEBAR & WORKSPACE RESET ---
st.sidebar.header("📁 Mandatory Client Files")

if st.sidebar.button("🧹 Clear Workspace"):
    for folder in [input_dir, output_dir]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"Error clearing {file_path}: {e}")
    st.sidebar.success("Workspace reset successfully.")
    st.rerun()

uploaded_script = st.sidebar.file_uploader("1. Script Document (.docx / .pdf)", type=["docx", "pdf"])
uploaded_ref_doc = st.sidebar.file_uploader("2. Visual Reference File (.pdf / .docx)", type=["pdf", "docx"])
uploaded_media = st.sidebar.file_uploader("3. Client Hindi Video / Audio Instructions (.mp4 / .mp3 / .m4a)", type=["mp4", "mp3", "m4a"])

script_saved_path = None
ref_doc_saved_path = None
media_saved_path = None

if uploaded_script:
    script_saved_path = os.path.join(input_dir, uploaded_script.name)
    with open(script_saved_path, "wb") as f:
        f.write(uploaded_script.getbuffer())
    st.sidebar.success(f"Script: {uploaded_script.name}")

if uploaded_ref_doc:
    ref_doc_saved_path = os.path.join(input_dir, uploaded_ref_doc.name)
    with open(ref_doc_saved_path, "wb") as f:
        f.write(uploaded_ref_doc.getbuffer())
    st.sidebar.success(f"Ref File: {uploaded_ref_doc.name}")

if uploaded_media:
    media_saved_path = os.path.join(input_dir, uploaded_media.name)
    with open(media_saved_path, "wb") as f:
        f.write(uploaded_media.getbuffer())
    st.sidebar.success(f"Media File: {uploaded_media.name}")

plan_file_path = os.path.join(output_dir, "current_panel_plan.json")

# --- PARSE AND PLAN ACTION ---
if script_saved_path:
    if st.sidebar.button("🚀 Parse & Generate Plan"):
        progress = st.progress(0, text="Starting multimodal analysis...")

        progress.progress(10, text="📄 Parsing script document...")
        parsed_data = parse_script_to_panels(script_saved_path, ref_doc_saved_path)

        progress.progress(25, text="🎥 Uploading media & analyzing with Gemini (single API call)...")
        panel_data = plan_storyboard(parsed_data, media_file_path=media_saved_path)

        progress.progress(90, text="💾 Saving storyboard plan...")
        with open(plan_file_path, "w", encoding="utf-8") as f:
            json.dump(panel_data, f, indent=2)

        progress.progress(100, text="✅ Done!")

        st.success(f"Successfully generated {panel_data['total_panels']} panels for '{uploaded_script.name}'!")
        st.rerun()

# --- DISPLAY STORYBOARD GRID ---
if os.path.exists(plan_file_path):
    with open(plan_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    panels = data.get("panels", [])
    script_title = data.get("title", "Storyboard Script")

    st.subheader(f"📄 Active Script: {script_title}")

    pdf_path = os.path.join(output_dir, "all_storyboard_prompts.pdf")

    if st.button("Generate Master Prompts PDF"):
        generate_prompts_pdf(data, pdf_path)
        st.success(f"Exported Master PDF for {len(panels)} panels!")

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as pdf_file:
            st.download_button(
                label="📥 Download All Panel Prompts (PDF)",
                data=pdf_file,
                file_name="storyboard_prompts.pdf",
                mime="application/pdf"
            )

    st.divider()
    st.subheader(f"📋 Storyboard Panels & Prompts Grid ({len(panels)} Panels)")

    for panel in panels:
        pid = panel["panel_id"]
        ref_imgs = panel.get("ref_image_paths", [])
        prompt_text = build_image_prompt(panel)
        client_notes = panel.get("client_visual_notes", "")

        st.markdown(f"### Panel {pid:03d} — {panel['shot_type']} ({panel['scene']})")

        c1, c2, c3 = st.columns([1, 1, 1])

        # Column 1: Client Reference Image + Client Direction Notes
        with c1:
            st.write("**Client Reference Image:**")
            if ref_imgs and os.path.exists(ref_imgs[0]):
                st.image(ref_imgs[0], caption=f"Reference ({panel['references'][0]})")
            else:
                st.caption("No reference image attached.")

            if client_notes:
                st.info(f"🎬 **Client Direction:** {client_notes}")

        # Column 2: Copy-Paste Prompt Box
        with c2:
            st.write("**Copy-Paste Prompt for Image Generation:**")
            st.code(prompt_text, language="text")

        # Column 3: Script Details
        with c3:
            st.write("**Script Details:**")
            if panel["presenter"]["dialogue"] != "NA":
                st.markdown(f"**Dialogue ({panel['presenter']['audio_mode']}):** {panel['presenter']['dialogue']}")
            if panel["canvas_layout"]["visual_description"]:
                st.markdown(f"**Visual:** {panel['canvas_layout']['visual_description']}")
            if panel["text_overlays"]:
                tos_items = [t['text'] if isinstance(t, dict) else t for t in panel["text_overlays"]]
                st.warning(f"**TOS Badge:** {' | '.join(tos_items)}")

        st.divider()
else:
    st.info("👈 Upload your script, reference file, and Hindi instruction video in the sidebar, then click 'Parse & Generate Plan'.")
