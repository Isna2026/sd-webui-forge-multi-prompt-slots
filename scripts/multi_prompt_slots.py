# This script was generated/optimized with the help of AI(Gemini and Qwen3.6).

import modules.scripts as scripts
import gradio as gr
from modules.processing import process_images, Processed
from modules.shared import state, opts
from modules.paths import data_path
import random
import os
import datetime
import json
import re
from pathlib import Path

# --- Constants for safety and limits ---
MAX_SEED = 4294967295
TASK_LIMIT_WARNING = 100
TASK_LIMIT_MAX = 500
MAX_RESOLUTION = 2048

# --- UI Localization definitions ---
LOCALIZATION = {
    "en_US": {
        "title": "Multi Prompt Slots",
        "file_accordion": "File Save/Load",
        "upload_label": "Load Prompt File (.json)",
        "save_btn": "Save Current Config (incl. Main)",
        "save_complete": "Save Complete: ",
        "p_mode": "Positive Mode",
        "n_mode": "Negative Mode",
        "mode_overwrite": "Overwrite",
        "mode_append": "Append",
        "seed_mode": "Seed Mode",
        "seed_fixed": "Fixed",
        "seed_rand_img": "Random Image",
        "seed_rand_set": "Random Set",
        "seed_info": "Fixed: If -1, seed is locked within the set.",
        "filter_label": "Target Slots (e.g., 1,3-5,9-)",
        "main_only_label": "Main Only (Ignore Slots)",
        "xyz_label": "Enable Inline XYZ (@@)",
        "size_label": "Enable Size Control ($$)",
        "toggle_btn": "Toggle All Boxes",
        "toggle_more": "Show More",
        "toggle_less": "Show Less",
        "clear_btn": "Clear All Prompts",
        "clear_slot_btn": "Clear Slots",
        "gen_btn": "Generate (Multi)",
        "check_btn": "Check Image Count",
        "slot_p": "Positive",
        "slot_n": "Negative",
        "task_limit_max": "Task limit exceeded ({count}/{max}). Check @@ or $$ settings.",
        "task_warning": "Generating large batch ({count} images). Watch for VRAM/Freeze."
    },
    "ja_JP": {
        "title": "Multi Prompt Slots",
        "file_accordion": "ファイルの保存・読み込み",
        "upload_label": "プロンプトファイルを読み込む (.json)",
        "save_btn": "現在の設定を保存（メイン含む）",
        "save_complete": "保存完了: ",
        "p_mode": "ポジティブ・モード",
        "n_mode": "ネガティブ・モード",
        "mode_overwrite": "上書き",
        "mode_append": "追加",
        "seed_mode": "シード・モード",
        "seed_fixed": "固定",
        "seed_rand_img": "画像ごとランダム",
        "seed_rand_set": "セット内共通ランダム",
        "seed_info": "固定: -1の場合はセット内でシードを固定します",
        "filter_label": "生成対象スロット (例: 1,3-5,9-)",
        "main_only_label": "Mainのみ生成 (スロット無視)",
        "xyz_label": "Inline XYZ (@@) を有効化",
        "size_label": "サイズ指定 ($$) を有効化",
        "toggle_btn": "全ボックスの表示切替",
        "toggle_more": "表示を増やす",
        "toggle_less": "表示を減らす",
        "clear_btn": "全プロンプトをクリア",
        "clear_slot_btn": "スロットをクリア",
        "gen_btn": "生成 (Multi)",
        "check_btn": "事前に枚数を確認",
        "slot_p": "Positive",
        "slot_n": "Negative",
        "task_limit_max": "タスク数上限({count}/{max})を超えました。@@展開や$$サイズ指定を見直してください。",
        "task_warning": "大量生成中({count}枚)。VRAM不足やフリーズにご注意ください。"
    }
}

def get_text(key):
    """Retrieves localized text based on WebUI settings."""
    lang = getattr(opts, "localization", "en_US")
    if lang not in LOCALIZATION:
        lang = "en_US"
    return LOCALIZATION[lang].get(key, LOCALIZATION["en_US"][key])

class Script(scripts.Script):
    def __init__(self):
        self.main_p_ref = None
        self.main_n_ref = None

    def title(self):
        return get_text("title")

    def show(self, is_img2img):
        return True

    def ui(self, is_img2img):
        """Defines the Gradio interface for the script."""
        main_p_state = gr.State(value="")
        main_n_state = gr.State(value="")
        is_expanded = gr.State(value=False)

        prefix = "img2img" if is_img2img else "txt2img"

        with gr.Column():
            # Configuration File Handling
            with gr.Accordion(get_text("file_accordion"), open=False):
                with gr.Row():
                    upload_file = gr.File(label=get_text("upload_label"), file_types=[".json"])
                    save_btn = gr.Button(get_text("save_btn"), variant="primary")
                download_output = gr.File(label=get_text("save_complete"), visible=False)

            # Global Generation Settings
            with gr.Row():
                p_mode = gr.Radio(choices=[get_text("mode_overwrite"), get_text("mode_append")], 
                                  value=get_text("mode_append"), label=get_text("p_mode"))
                n_mode = gr.Radio(choices=[get_text("mode_overwrite"), get_text("mode_append")], 
                                  value=get_text("mode_append"), label=get_text("n_mode"))
                seed_mode = gr.Radio(
                    choices=[get_text("seed_fixed"), get_text("seed_rand_img"), get_text("seed_rand_set")], 
                    value=get_text("seed_rand_img"), label=get_text("seed_mode"), info=get_text("seed_info")
                )

            # Filtering and Advanced Control
            with gr.Row():
                gen_filter = gr.Textbox(
                    label=get_text("filter_label"), 
                    placeholder="1,3-5,9- / 'main' (Blank=All)", 
                    lines=1
                )
                main_only = gr.Checkbox(label=get_text("main_only_label"), value=False)
                inline_xyz = gr.Checkbox(label=get_text("xyz_label"), value=True)
                size_control = gr.Checkbox(label=get_text("size_label"), value=True)

            # Utility Buttons
            with gr.Row():
                toggle_btn = gr.Button(get_text("toggle_btn"))
                clear_all_btn = gr.Button(get_text("clear_btn"), variant="stop")
                clear_slot_btn = gr.Button(get_text("clear_slot_btn"), variant="secondary")

            gr.HTML("<div style='height: 20px;'></div>")
            
            # --- Image count check button and result row ---
            with gr.Row(elem_id=f"{prefix}_multi_prompt_counter_row"):
                gen_btn_clone = gr.Button(get_text("gen_btn"), variant="primary", elem_id=f"{prefix}_multi_prompt_gen_clone")
                interrupt_btn_clone = gr.Button("Interrupt", variant="stop", elem_id=f"{prefix}_multi_prompt_interrupt_clone")
                check_count_btn = gr.Button(get_text("check_btn"), variant="secondary")
                count_display = gr.HTML(value="<span style='color: #2ed573; font-weight: bold;'>- images</span>", elem_id=f"{prefix}_multi_prompt_count_display")

            # Custom styling for prompt slots
            gr.HTML("""
            <style>
                .prompt-p textarea {
                    background-color: #ffffff !important;
                    border: 1px solid #e6e3e3 !important;
                }
                .prompt-p span {
                    color: #1bad02 !important;
                    font-weight: bold !important;
                }
                .prompt-n textarea {
                    background-color: #fff8f8 !important;
                    border: 1px solid #fcdede !important;
                }
                .prompt-n span {
                    color: #c07070 !important;
                    font-weight: bold !important;
                }
            </style>
            """)

            # Prompt Slot Definition (30 slots x 2 textboxes)
            prompt_data = []
            for i in range(30):
                visible = i < 3
                p_box = gr.Textbox(label=f"{get_text('slot_p')} {i+1}", lines=2, visible=visible, elem_classes=["prompt", "prompt-p"])
                n_box = gr.Textbox(label=f"{get_text('slot_n')} {i+1}", lines=2, visible=visible, elem_classes=["prompt", "prompt-n"])
                prompt_data.extend([p_box, n_box])

            # JS targets for triggering main UI buttons
            target_gen_id = f"{prefix}_generate"
            target_intr_id = f"{prefix}_interrupt"

            # Sync Interrupt button via JS
            interrupt_btn_clone.click(fn=None, _js=f"() => {{ document.getElementById('{target_intr_id}').click(); }}", inputs=None, outputs=None)

            # Sync Generate button and state monitoring via JS
            gen_btn_clone.click(fn=None, _js=f"""() => {{
                const realGen = document.getElementById('{target_gen_id}');
                const realIntr = document.getElementById('{target_intr_id}');
                const cloneGen = document.getElementById('{prefix}_multi_prompt_gen_clone');
                const cloneIntr = document.getElementById('{prefix}_multi_prompt_interrupt_clone');

                if (!realGen || !cloneGen) return;

                realGen.click();

                if (window.{prefix}MultiPromptSyncTimer) clearInterval(window.{prefix}MultiPromptSyncTimer);

                window.{prefix}MultiPromptSyncTimer = setInterval(() => {{
                    const m = document.getElementById('{target_gen_id}');
                    const i = document.getElementById('{target_intr_id}');
                    const cg = document.getElementById('{prefix}_multi_prompt_gen_clone');
                    const ci = document.getElementById('{prefix}_multi_prompt_interrupt_clone');

                    if (!m || !cg) return;

                    const isBusy = (m.offsetParent === null) || m.disabled || (i && i.offsetParent !== null);

                    cg.disabled = isBusy;
                    if (ci) ci.disabled = !isBusy;
                }}, 400);
            }}""", inputs=None, outputs=None)

            # Serialization logic (Save to JSON)
            def save_to_file_json(mp, mn, pm, nm, sm, flt, monly, xyz, sc, *prompts):
                try:
                    base_save_path = Path(data_path).joinpath("outputs", "multi_prompt_configs").resolve()
                    base_save_path.mkdir(parents=True, exist_ok=True)

                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"multi_prompts_{timestamp}.json"
                    filepath = base_save_path.joinpath(filename).resolve()

                    if not filepath.is_relative_to(base_save_path):
                        return gr.update(visible=True, label="Error: Safety Directory Violation")

                    config = {
                        "main_prompt": str(mp), "negative_prompt": str(mn), 
                        "positive_mode": "Append" if pm == get_text("mode_append") else "Overwrite",
                        "negative_mode": "Append" if nm == get_text("mode_append") else "Overwrite",
                        "seed_mode": sm, "filter": flt, "main_only": monly, 
                        "inline_xyz": xyz, "size_control": sc, "sets": []
                    }
                    for i in range(0, len(prompts), 2):
                        config["sets"].append({"pos": str(prompts[i]).strip(), "neg": str(prompts[i+1]).strip()})
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(config, f, ensure_ascii=False, indent=2)
                    
                    return gr.update(value=str(filepath), visible=True, label=f"{get_text('save_complete')}{filename}")
                except Exception as e:
                    return gr.update(visible=True, label=f"Error: {str(e)}")

            # Deserialization logic (Load from JSON)
            def load_from_file_json(file):
                if file is None: return [gr.update() for _ in range(69)]
                try:
                    with open(file.name, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    pairs = []
                    raw_sets = config.get("sets", [])
                    if isinstance(raw_sets, list):
                        for s in raw_sets:
                            if isinstance(s, dict): pairs.extend([str(s.get("pos", "")), str(s.get("neg", ""))])
                    while len(pairs) < 60: pairs.append("")
                    pm_val = get_text("mode_append") if config.get("positive_mode") == "Append" else get_text("mode_overwrite")
                    nm_val = get_text("mode_append") if config.get("negative_mode") == "Append" else get_text("mode_overwrite")
                    return [str(config.get("main_prompt", "")), str(config.get("negative_prompt", "")), pm_val, nm_val, 
                            str(config.get("seed_mode", get_text("seed_rand_img"))), str(config.get("filter", "")), 
                            bool(config.get("main_only", False)), bool(config.get("inline_xyz", True)), bool(config.get("size_control", True))] + [gr.update(value=v) for v in pairs[:60]]
                except Exception: return [gr.update() for _ in range(69)]

            # --- Backend: Logic to calculate the number of pure prompt combinations ---
            def calculate_pure_prompt_images(raw_base_pos, raw_base_neg, gen_filter_text, main_only, inline_xyz_enabled, size_control_enabled, *prompts):
                filter_indices = set() if main_only else self.parse_filter(gen_filter_text, max_val=30)
                logic_base_pos = "\n".join([l.split('#')[0] for l in str(raw_base_pos).splitlines()])
                logic_base_neg = "\n".join([l.split('#')[0] for l in str(raw_base_neg).splitlines()])
                
                # Count the number of size specifications on the main side
                main_sizes_count = 1
                m_match = None
                if size_control_enabled:
                    m_match = re.search(r"\$\$(.*?)\$\$", logic_base_pos, flags=re.DOTALL)
                    if m_match:
                        valid_pairs = 0
                        for pair in m_match.group(1).split(';'):
                            try:
                                parts = pair.split(',')
                                if len(parts) >= 2: int(parts[0]), int(parts[1]); valid_pairs += 1
                            except: continue
                        if valid_pairs > 0: main_sizes_count = valid_pairs

                # Number of XYZ expansions for the main prompt
                base_pos_variants = len(self.parse_inline_xyz(logic_base_pos)) if inline_xyz_enabled else 1
                base_neg_variants = len(self.parse_inline_xyz(logic_base_neg)) if inline_xyz_enabled else 1
                main_loop_multiplier = base_pos_variants * base_neg_variants

                # Process each slot data
                active_slots = []
                for i in range(0, len(prompts), 2):
                    slot_num = (i // 2) + 1
                    if slot_num not in filter_indices: continue
                    pos, neg = str(prompts[i]).strip(), str(prompts[i+1]).strip()
                    logic_pos = "\n".join([l.split('#')[0] for l in pos.splitlines()])
                    logic_neg = "\n".join([l.split('#')[0] for l in neg.splitlines()])
                    if not logic_pos and not logic_neg: continue
                    
                    slot_sizes_count = 1
                    s_match = re.search(r"\$\$(.*?)\$\$", logic_pos, flags=re.DOTALL)
                    if size_control_enabled and m_match is None and s_match:
                        valid_pairs = 0
                        for pair in s_match.group(1).split(';'):
                            try:
                                parts = pair.split(',')
                                if len(parts) >= 2: int(parts[0]), int(parts[1]); valid_pairs += 1
                            except: continue
                        if valid_pairs > 0: slot_sizes_count = valid_pairs
                    
                    active_slots.append({"raw_p": logic_pos, "raw_n": logic_neg, "sizes_count": slot_sizes_count})

                if not active_slots:
                    active_slots = [{"raw_p": "", "raw_n": "", "sizes_count": 1}]

                # Calculate the total number of loops (per batch loop) based on pure prompt combinations
                base_tasks_count = 0
                for s_item in active_slots:
                    sizes_mult = main_sizes_count if m_match is not None else s_item["sizes_count"]
                    p_vars = len(self.parse_inline_xyz(s_item["raw_p"])) if inline_xyz_enabled else 1
                    n_vars = len(self.parse_inline_xyz(s_item["raw_n"])) if inline_xyz_enabled else 1
                    base_tasks_count += sizes_mult * p_vars * n_vars

                pure_images_per_batch = main_loop_multiplier * base_tasks_count

                # Return HTML with the raw value embedded in a custom attribute (data-pure) for easy parsing on the JS side
                return f"<span id='{prefix}_mp_calc_result' data-pure='{pure_images_per_batch}' style='color: #2ed573; font-weight: bold; font-size: 1.1em;'>{pure_images_per_batch} images</span>"

            # UI Event Bindings
            save_btn.click(fn=lambda p, n: (p, n), inputs=[self.main_p_ref, self.main_n_ref], outputs=[main_p_state, main_n_state]).then(
                fn=save_to_file_json, inputs=[main_p_state, main_n_state, p_mode, n_mode, seed_mode, gen_filter, main_only, inline_xyz, size_control] + prompt_data, outputs=[download_output])
            
            upload_file.change(fn=load_from_file_json, inputs=[upload_file], outputs=[self.main_p_ref, self.main_n_ref, p_mode, n_mode, seed_mode, gen_filter, main_only, inline_xyz, size_control] + prompt_data)
            
            clear_all_btn.click(fn=lambda: ["", ""] + [get_text("mode_append"), get_text("mode_append"), get_text("seed_rand_img"), "", False, True, True] + [""] * 60, inputs=None, outputs=[self.main_p_ref, self.main_n_ref, p_mode, n_mode, seed_mode, gen_filter, main_only, inline_xyz, size_control] + prompt_data)
            clear_slot_btn.click(fn=lambda: [get_text("mode_append"), get_text("mode_append"), get_text("seed_rand_img"), "", False, True, True] + [""] * 60, inputs=None, outputs=[p_mode, n_mode, seed_mode, gen_filter, main_only, inline_xyz, size_control] + prompt_data)

            def toggle_visibility(current_state):
                new_state = not current_state
                return [gr.update(visible=(i < 6 or new_state)) for i in range(60)] + [new_state, gr.update(value=get_text("toggle_less") if new_state else get_text("toggle_more"))]
            
            toggle_btn.click(fn=toggle_visibility, inputs=[is_expanded], outputs=prompt_data + [is_expanded, toggle_btn])

            # --- Image count check button and result row ---
            check_count_btn.click(
                fn=calculate_pure_prompt_images,
                inputs=[self.main_p_ref, self.main_n_ref, gen_filter, main_only, inline_xyz, size_control] + prompt_data,
                outputs=[count_display]
            ).then(
                fn=None,
                _js=f"""() => {{
                    // Utility function to safely retrieve values from the main WebUI sliders
                    const getSliderVal = (id) => {{
                        const container = document.getElementById(id);
                        if (!container) return 1;
                        const input = container.querySelector('input[type="number"]');
                        if (input && input.value) {{
                            const val = parseInt(input.value, 10);
                            return isNaN(val) || val <= 0 ? 1 : val;
                        }}
                        return 1;
                    }};

                    const batchCount = getSliderVal('{prefix}_batch_count');
                    const batchSize = getSliderVal('{prefix}_batch_size');

                    // Get the base image count from the HTML generated by the Python side
                    const resultSpan = document.getElementById('{prefix}_mp_calc_result');
                    if (!resultSpan) return;

                    const pureImages = parseInt(resultSpan.getAttribute('data-pure'), 10) || 0;
                    const totalImages = pureImages * batchCount;

                    // Color determination based on the upper limits
                    let color = "#2ed573"; // Normal (Green)
                    if (totalImages > {TASK_LIMIT_MAX}) {{
                        color = "#ff4d4d"; // Limit exceeded (Red)
                    }} else if (totalImages > {TASK_LIMIT_WARNING}) {{
                        color = "#ffcc00"; // Warning (Yellow)
                    }}

                    // Update the display text
                    resultSpan.style.color = color;
                    resultSpan.innerText = `${{totalImages}} images (Prompts: ${{pureImages}} × Batch Count: ${{batchCount}})`;
                }}""",
                inputs=None,
                outputs=None
            )

        return [p_mode, n_mode, seed_mode, gen_filter, main_only, inline_xyz, size_control] + prompt_data

    def after_component(self, component, **kwargs):
        """Captures references to main UI prompt components."""
        eid = kwargs.get("elem_id")
        if eid in ["txt2img_prompt", "img2img_prompt"]: self.main_p_ref = component
        elif eid in ["txt2img_neg_prompt", "img2img_neg_prompt"]: self.main_n_ref = component

    def parse_filter(self, text, max_val=30):
        """Parses range strings like '1,3-5,9-' into a set of indices."""
        t = str(text).lower().strip()
        if t in ["main", "-1"]: return set()
        if not t or t == "0": return set(range(1, max_val + 1))
        indices = set()
        for part in t.split(','):
            if '-' in part:
                parts = (part + " ").split('-', 1)
                try:
                    start = int(parts[0].strip()) if parts[0].strip() else 1
                    end = int(parts[1].strip()) if parts[1].strip() else max_val
                    indices.update(range(min(start, end), min(max(start, end), max_val) + 1))
                except: continue
            else:
                try:
                    val = int(part.strip())
                    if 0 < val <= max_val: indices.add(val)
                except: continue
        return indices

    def parse_inline_xyz(self, text):
        """Expands @@A;B;C@@ syntax into multiple prompt variants."""
        pattern = re.compile(r"@@(.*?)($|@@)")
        results = [text]
        for i in range(100):
            new_results, found_any = [], False
            for t in results:
                match = pattern.search(t)
                if match:
                    found_any = True
                    prefix, suffix, content = t[:match.start()], t[match.end():], match.group(1)
                    variants = [v.strip() for v in content.split(';') if v.strip()]
                    if not variants: new_results.append(prefix + suffix)
                    else:
                        for v in variants: new_results.append(prefix + v + suffix)
                else: new_results.append(t)
            results = new_results
            if not found_any: break
        if len(results) > 100:
            print(f"\033[33m[Multi Prompt Slots] WARNING: Inline XYZ expansion limit (100) reached. Check for deep nesting.\033[0m")
        return results

    def cleanup_tags(self, text):
        """Cleans up internal syntax and formatting for final generation."""
        if not text: return ""
        t = str(text)
        t = "\n".join([line.split('#')[0] for line in t.splitlines()])
        t = re.sub(r"@@(.*?)@@", lambda m: m.group(1).split(';')[0].strip(), t, flags=re.DOTALL)
        t = re.sub(r"\$\$(.*?)\$\$", "", t, flags=re.DOTALL)
        t = t.strip().replace("\n", " ")
        t = re.sub(r'\s*,\s*', ', ', t); t = re.sub(r',+', ',', t)
        return t.strip().strip(',')

    def strip_size_tag(self, text):
        """Removes resolution control tags ($$W,H$$) from text."""
        return re.sub(r"\$\$(.*?)\$\$", "", str(text or ""), flags=re.DOTALL).strip()

    def run(self, p, p_mode, n_mode, seed_mode, gen_filter_text, main_only, inline_xyz_enabled, size_control_enabled, *args):
        """Main execution logic for batch image generation."""
        if state.job_count > 0:
            return Processed(p, [], p.seed, "Generation already in progress.")

        raw_base_pos, raw_base_neg = p.prompt, p.negative_prompt
        logic_base_pos = "\n".join([l.split('#')[0] for l in str(raw_base_pos).splitlines()])
        logic_base_neg = "\n".join([l.split('#')[0] for l in str(raw_base_neg).splitlines()])
        filter_indices = set() if main_only else self.parse_filter(gen_filter_text, max_val=30)
        
        # Extract main resolution variants if available
        main_sizes = []
        m_match = None
        if size_control_enabled:
            m_match = re.search(r"\$\$(.*?)\$\$", logic_base_pos, flags=re.DOTALL)
        if m_match:
            for pair in m_match.group(1).split(';'):
                try:
                    parts = pair.split(',')
                    if len(parts) >= 2:
                        w = min(MAX_RESOLUTION, max(64, int(parts[0])))
                        h = min(MAX_RESOLUTION, max(64, int(parts[1])))
                        main_sizes.append((w, h))
                except:
                    continue

        # Handle inline expansion for base prompts
        base_pos_variants = [self.cleanup_tags(v) for v in self.parse_inline_xyz(logic_base_pos)] if inline_xyz_enabled else [self.cleanup_tags(logic_base_pos)]
        base_neg_variants = [self.cleanup_tags(v) for v in self.parse_inline_xyz(logic_base_neg)] if inline_xyz_enabled else [self.cleanup_tags(logic_base_neg)]

        # Collect data from active prompt slots
        active_slots = []
        for i in range(0, len(args), 2):
            slot_num = (i // 2) + 1
            if slot_num not in filter_indices: continue
            pos, neg = str(args[i]).strip(), str(args[i+1]).strip()
            logic_pos = "\n".join([l.split('#')[0] for l in pos.splitlines()])
            logic_neg = "\n".join([l.split('#')[0] for l in neg.splitlines()])
            if not logic_pos and not logic_neg: continue
            slot_sizes = []
            s_match = re.search(r"\$\$(.*?)\$\$", logic_pos, flags=re.DOTALL)
            if size_control_enabled and not main_sizes and s_match:
                for pair in s_match.group(1).split(';'):
                    try:
                        parts = pair.split(',')
                        if len(parts) >= 2:
                            w = min(MAX_RESOLUTION, max(64, int(parts[0])))
                            h = min(MAX_RESOLUTION, max(64, int(parts[1])))
                            slot_sizes.append((w, h))
                    except:
                        continue
            if not slot_sizes: slot_sizes = [(p.width, p.height)]
            active_slots.append({"raw_p": self.strip_size_tag(logic_pos), "raw_n": self.strip_size_tag(logic_neg), "idx": slot_num, "sizes": slot_sizes})

        if not active_slots:
            active_slots = [{"raw_p": "", "raw_n": "", "idx": 0, "sizes": [(p.width, p.height)]}]

        # Build task queue
        tasks = []
        original_n_iter, append_label, original_batch_size, original_seed = p.n_iter, get_text("mode_append"), p.batch_size, p.seed
        for b in range(original_n_iter):
            for m_pos in base_pos_variants:
                for m_neg in base_neg_variants:
                    sizes_to_use = main_sizes if main_sizes else None
                    for s_item in active_slots:
                        current_sizes = sizes_to_use if sizes_to_use else s_item["sizes"]
                        for sw, sh in current_sizes:
                            self._add_slot_tasks(tasks, b, m_pos, m_neg, s_item, sw, sh, p_mode, n_mode, append_label, inline_xyz_enabled)

        total_tasks = len(tasks)
        if total_tasks == 0: return Processed(p, [], p.seed, "No tasks.")
        
        # Safety limit check
        if total_tasks > TASK_LIMIT_MAX:
            msg = get_text("task_limit_max").format(count=total_tasks, max=TASK_LIMIT_MAX)
            print(f"\033[31m[Multi Prompt Slots] {msg}\033[0m"); state.textinfo = msg
            return Processed(p, [], p.seed, msg)
        if total_tasks > TASK_LIMIT_WARNING:
            msg = get_text("task_warning").format(count=total_tasks)
            print(f"\033[33m[Multi Prompt Slots] WARNING: {msg}\033[0m"); state.textinfo = msg

        print(f"\n\033[32m[Multi Prompt Slots] Total Tasks: {total_tasks}\033[0m")
        state.job_count = total_tasks
        p.n_iter, p.batch_size, p.do_not_save_grid = 1, 1, True
        all_images, infotexts = [], []
        
        # Seed preparation
        base_random_seed = random.getrandbits(32)
        batch_seeds = [(base_random_seed + b * 999) & MAX_SEED for b in range(original_n_iter)]
        fixed_label, rand_set_label = get_text("seed_fixed"), get_text("seed_rand_set")

        # Process task queue
        for count, t in enumerate(tasks):
            if state.interrupted or state.skipped: break
            state.job_no = count
            state.textinfo = f"({count+1}/{total_tasks}) | Slot #{t['idx']} | {t['w']}x{t['h']} | Batch {t['b']+1}"
            p.prompt, p.negative_prompt, p.width, p.height = t["p"], t["n"], t["w"], t["h"]
            
            # Type-safe seed calculation
            raw_seed = p.seed
            if seed_mode == fixed_label:
                try:
                    parsed_seed = int(float(raw_seed))
                    curr_seed = parsed_seed if parsed_seed != -1 else batch_seeds[0]
                except (ValueError, TypeError):
                    curr_seed = batch_seeds[0]
            elif seed_mode == rand_set_label:
                curr_seed = batch_seeds[t['b']]
            else:
                curr_seed = random.getrandbits(32)
            
            p.seed = int(curr_seed) & MAX_SEED
            p.all_seeds = [p.seed]

            try:
                proc = process_images(p)
                if proc and proc.images:
                    all_images.append(proc.images[0]); infotexts.append(proc.infotexts[0])
            except Exception: continue

        # Restore original settings
        p.n_iter, p.prompt, p.negative_prompt, p.batch_size, p.seed = original_n_iter, raw_base_pos, raw_base_neg, original_batch_size, original_seed
        return Processed(p, all_images, p.seed, "", infotexts=infotexts)

    def _add_slot_tasks(self, tasks, b, m_pos, m_neg, s_item, sw, sh, p_mode, n_mode, append_label, inline_xyz_enabled):
        """Appends specific slot configurations to the task list, handling prompt combinations."""
        m_pos_clean, m_neg_clean = self.cleanup_tags(m_pos), self.cleanup_tags(m_neg)
        p_vars = self.parse_inline_xyz(s_item["raw_p"]) if inline_xyz_enabled else [s_item["raw_p"]]
        n_vars = self.parse_inline_xyz(s_item["raw_n"]) if inline_xyz_enabled else [s_item["raw_n"]]
        for sp in p_vars:
            for sn in n_vars:
                fp, fn = self.cleanup_tags(sp), self.cleanup_tags(sn)
                tasks.append({
                    "b": b, "idx": s_item["idx"], "w": sw, "h": sh,
                    "p": (f"{m_pos_clean}, {fp}" if p_mode == append_label and m_pos_clean and fp else (fp or m_pos_clean)),
                    "n": (f"{m_neg_clean}, {fn}" if n_mode == append_label and m_neg_clean and fn else (fn or m_neg_clean))
                })