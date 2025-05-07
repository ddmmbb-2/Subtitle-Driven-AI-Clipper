import os
import subprocess
import srt
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, scrolledtext
from datetime import timedelta
import requests
import re
import whisper
from openai import OpenAI
import json
import sys # Import sys to check platform for ffmpeg path
import threading # Import threading for background tasks (optional but good for GUI)
import traceback # Import traceback for detailed error info

# --- Configuration Handling ---
CONFIG_FILE = "config.json"

# 預設的 AI 提示詞模板，包含一個佔位符 {subtitle_content} 用於插入字幕內容
DEFAULT_AI_PROMPT_TEMPLATE = """你是一位專業影片剪輯助理。
以下是字幕段落：
{subtitle_content}
請根據這些字幕內容，思考如何修改錯譯的部分並規劃一個流暢的剪輯方案，以有效地表達影片的主題。
剪輯時請務必保留完整的句子或意義單元，不要截斷完整的段落 僅做決定每段字幕的留存
請**只回傳時間範圍清單**，每行一段時間，格式如下：
適當的預留語音與結尾的緩衝時間!
00:00:03.000 - 00:00:08.000
00:01:15.500 - 00:01:22.000

請不要提供任何解釋、摘要、評論或說明。只能回傳時間段。"""


DEFAULT_CONFIG = {
    "llm_type": "gpt", # 'gpt' or 'ollama'
    "gpt_api_key": "",
    "gpt_model_name": "gpt-4o-mini",
    "ollama_api_base": "http://localhost:11434/v1", # Default Ollama API base URL (OpenAI compatible)
    "ollama_model_name": "llama3", # Default Ollama model
    "ffmpeg_path": "./ffmpeg/bin/ffmpeg.exe" if sys.platform == "win32" else "/usr/local/bin/ffmpeg", # Default path based on OS
    "output_dir": "out",
    "buffer_time": 0.5, # Seconds buffer before and after LLM suggested times
    "min_duration": 2.0, # Minimum duration for a clip in seconds
    "whisper_model": "small", # Whisper model size (tiny, base, small, medium, large)
    "ai_prompt_template": DEFAULT_AI_PROMPT_TEMPLATE # Add prompt template to config
}

app_config = DEFAULT_CONFIG.copy() # Global config dictionary

def load_config():
    """Loads configuration from config.json."""
    global app_config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                loaded_config = json.load(f)
                # Update default config with loaded values, keeping new default keys if they exist
                # Special handling for prompt template to ensure newline characters are loaded correctly
                if "ai_prompt_template" in loaded_config and isinstance(loaded_config["ai_prompt_template"], str):
                     # Replace escaped newlines if necessary (json might escape them)
                     loaded_config["ai_prompt_template"] = loaded_config["ai_prompt_template"].replace('\\n', '\n')

                for key, value in DEFAULT_CONFIG.items():
                     if key not in loaded_config or loaded_config[key] is None: # Also handle None values
                         loaded_config[key] = value
                app_config.update(loaded_config)
                print("✅ 配置載入成功")
            except json.JSONDecodeError:
                print("⚠️ 無效的配置檔案，載入預設配置")
                app_config = DEFAULT_CONFIG.copy()
            except Exception as e:
                 print(f"⚠️ 載入配置時發生錯誤: {e}，載入預設配置")
                 traceback.print_exc()
                 app_config = DEFAULT_CONFIG.copy()
    else:
        print("ℹ️ 未找到配置檔案，載入預設配置")
        app_config = DEFAULT_CONFIG.copy()

def save_config():
    """Saves current configuration to config.json."""
    global app_config
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            # Json dump will handle escaping newlines
            json.dump(app_config, f, indent=4, ensure_ascii=False) # ensure_ascii=False keeps non-ASCII chars readable
        print("✅ 配置儲存成功")
    except IOError as e:
        messagebox.showerror("儲存錯誤", f"無法儲存配置檔案: {e}")
    except Exception as e:
         messagebox.showerror("儲存錯誤", f"儲存配置時發生錯誤: {e}")
         traceback.print_exc()


# --- GUI Elements ---
class SettingsWindow(tk.Toplevel):
    """GUI window for application settings."""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定")
        # Adjust geometry to accommodate prompt text area
        self.geometry("600x700")
        self.transient(parent) # Keep window on top of the parent
        self.grab_set() # Modal window - blocks interaction with parent window

        # Create a main frame for padding and organization
        main_frame = tk.Frame(self)
        main_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        # --- Variables ---
        self.llm_type_var = tk.StringVar(value=app_config.get("llm_type", "gpt"))
        self.gpt_key_var = tk.StringVar(value=app_config.get("gpt_api_key", ""))
        self.gpt_model_var = tk.StringVar(value=app_config.get("gpt_model_name", "gpt-4o-mini"))
        self.ollama_base_var = tk.StringVar(value=app_config.get("ollama_api_base", "http://localhost:11434/v1"))
        self.ollama_model_var = tk.StringVar(value=app_config.get("ollama_model_name", "llama3"))
        self.ffmpeg_path_var = tk.StringVar(value=app_config.get("ffmpeg_path", DEFAULT_CONFIG["ffmpeg_path"])) # Use default from config for OS awareness
        self.whisper_model_var = tk.StringVar(value=app_config.get("whisper_model", "small"))
        self.buffer_time_var = tk.DoubleVar(value=app_config.get("buffer_time", 0.5))
        self.min_duration_var = tk.DoubleVar(value=app_config.get("min_duration", 2.0))
        # Prompt template will be handled directly with the text widget


        # --- LLM Selection ---
        llm_frame = tk.LabelFrame(main_frame, text="大型語言模型 (LLM) 設定")
        llm_frame.pack(pady=5, fill=tk.X)

        tk.Label(llm_frame, text="選擇 LLM:").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(llm_frame, text="OpenAI GPT", variable=self.llm_type_var, value="gpt", command=self._update_fields).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(llm_frame, text="Ollama", variable=self.llm_type_var, value="ollama", command=self._update_fields).pack(side=tk.LEFT, padx=5)


        # --- GPT Settings ---
        self.gpt_frame = tk.LabelFrame(main_frame, text="OpenAI GPT 設定")
        self.gpt_frame.pack(pady=5, fill=tk.X)

        tk.Label(self.gpt_frame, text="API Key:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.gpt_frame, textvariable=self.gpt_key_var, width=30, show='*').pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Label(self.gpt_frame, text="Model:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.gpt_frame, textvariable=self.gpt_model_var, width=15).pack(side=tk.LEFT, padx=5)

        # --- Ollama Settings ---
        self.ollama_frame = tk.LabelFrame(main_frame, text="Ollama 設定")
        self.ollama_frame.pack(pady=5, fill=tk.X)

        tk.Label(self.ollama_frame, text="API Base URL:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.ollama_frame, textvariable=self.ollama_base_var, width=30).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Label(self.ollama_frame, text="Model:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.ollama_frame, textvariable=self.ollama_model_var, width=15).pack(side=tk.LEFT, padx=5)


        # --- Other Settings ---
        other_frame = tk.LabelFrame(main_frame, text="其他設定")
        other_frame.pack(pady=5, fill=tk.X)

        tk.Label(other_frame, text="FFmpeg 路徑:").pack(side=tk.LEFT, padx=5)
        tk.Entry(other_frame, textvariable=self.ffmpeg_path_var, width=30).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Button(other_frame, text="瀏覽", command=self._select_ffmpeg).pack(side=tk.LEFT, padx=5)

        tk.Label(other_frame, text="Whisper Model:").pack(side=tk.LEFT, padx=(15,5))
        tk.Entry(other_frame, textvariable=self.whisper_model_var, width=10).pack(side=tk.LEFT, padx=5)

        # Buffer and Duration settings
        timing_frame = tk.Frame(other_frame)
        timing_frame.pack(pady=5, fill=tk.X)
        tk.Label(timing_frame, text="緩衝時間 (秒):").pack(side=tk.LEFT, padx=5)
        tk.Entry(timing_frame, textvariable=self.buffer_time_var, width=8).pack(side=tk.LEFT, padx=5)
        tk.Label(timing_frame, text="最小片段時長 (秒):").pack(side=tk.LEFT, padx=5)
        tk.Entry(timing_frame, textvariable=self.min_duration_var, width=8).pack(side=tk.LEFT, padx=5)

        # --- AI Prompt Template Setting ---
        prompt_frame = tk.LabelFrame(main_frame, text="AI 提示詞模板設定 (使用 {subtitle_content} 插入字幕)")
        prompt_frame.pack(pady=5, fill=tk.BOTH, expand=True) # Allow this frame to expand

        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap=tk.WORD, width=70, height=10)
        self.prompt_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Load current prompt template into the text widget
        current_prompt_template = app_config.get("ai_prompt_template", DEFAULT_AI_PROMPT_TEMPLATE)
        self.prompt_text.insert(tk.END, current_prompt_template)


        # --- Save Button ---
        tk.Button(main_frame, text="儲存設定", command=self._save_and_close).pack(pady=10)

        self._update_fields() # Initialize field states


    def _update_fields(self):
        """Enables/disables LLM specific fields based on selection."""
        llm_type = self.llm_type_var.get()
        if llm_type == "gpt":
            for child in self.gpt_frame.winfo_children():
                 child.config(state=tk.NORMAL)
            for child in self.ollama_frame.winfo_children():
                 child.config(state=tk.DISABLED)
        else: # ollama
            for child in self.gpt_frame.winfo_children():
                 child.config(state=tk.DISABLED)
            for child in self.ollama_frame.winfo_children():
                 child.config(state=tk.NORMAL)

    def _select_ffmpeg(self):
        """Opens file dialog to select FFmpeg executable."""
        path = filedialog.askopenfilename(title="選擇 FFmpeg 執行檔", filetypes=[("Executables", "*.exe;*"), ("All files", "*.*")])
        if path:
            self.ffmpeg_path_var.set(path)

    def _save_and_close(self):
        """Saves settings and closes the window."""
        global app_config
        try:
            # Attempt to get values, will raise ValueError for non-numeric input
            buffer_time = self.buffer_time_var.get()
            min_duration = self.min_duration_var.get()
            prompt_template = self.prompt_text.get("1.0", tk.END).strip() # Get text from ScrolledText

            # Basic validation for prompt template
            if "{subtitle_content}" not in prompt_template:
                 messagebox.showwarning("提示詞警告", "提示詞模板中未包含佔位符 {subtitle_content}，字幕內容將無法插入。")
                 # Decide if we should allow saving or force correction
                 # For now, allow saving but warn.

            app_config["llm_type"] = self.llm_type_var.get()
            app_config["gpt_api_key"] = self.gpt_key_var.get()
            app_config["gpt_model_name"] = self.gpt_model_var.get()
            app_config["ollama_api_base"] = self.ollama_base_var.get()
            app_config["ollama_model_name"] = self.ollama_model_var.get()
            app_config["ffmpeg_path"] = self.ffmpeg_path_var.get()
            app_config["whisper_model"] = self.whisper_model_var.get()
            app_config["buffer_time"] = buffer_time
            app_config["min_duration"] = min_duration
            app_config["ai_prompt_template"] = prompt_template


            save_config()
            self.destroy()
        except ValueError:
             messagebox.showerror("輸入錯誤", "緩衝時間和最小片段時長必須是有效的數字")
        except Exception as e:
             messagebox.showerror("儲存錯誤", f"儲存設定時發生錯誤: {e}")
             traceback.print_exc()


class SubtitleEditorWindow(tk.Toplevel):
    """GUI window for editing subtitles."""
    def __init__(self, parent, subtitles_text, save_callback):
        super().__init__(parent)
        self.title("編輯字幕")
        self.geometry("700x500")
        self.transient(parent)
        self.grab_set()

        self.save_callback = save_callback

        tk.Label(self, text="請編輯字幕內容：").pack(pady=5)
        # Use ScrolledText for better handling of large text
        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, width=80, height=25)
        self.text_area.insert(tk.END, subtitles_text)
        self.text_area.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)

        tk.Button(self, text="儲存並繼續", command=self._save_and_close).pack(pady=10)

    def _save_and_close(self):
        """Gets edited text and calls the save callback."""
        edited_text = self.text_area.get("1.0", tk.END).strip()
        self.save_callback(edited_text)
        self.destroy()

# --- LLM Abstraction ---
def call_llm(prompt):
    """Calls the selected LLM with the given prompt."""
    llm_type = app_config.get("llm_type", "gpt")
    model_name = (app_config.get("gpt_model_name") if llm_type == "gpt"
                  else app_config.get("ollama_model_name"))

    print(f"🤖 呼叫 {llm_type.upper()} 模型：{model_name}")

    try:
        if llm_type == "gpt":
            api_key = app_config.get("gpt_api_key")
            if not api_key:
                # Use root.after for messagebox from thread
                # messagebox.showerror("LLM 設定錯誤", "請在設定中輸入 GPT API Key")
                return None
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "你是一位影片剪輯助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content
        elif llm_type == "ollama":
            api_base = app_config.get("ollama_api_base")
            if not api_base:
                 # Use root.after for messagebox from thread
                 # messagebox.showerror("LLM 設定錯誤", "請在設定中輸入 Ollama API Base URL")
                 return None
            # Use OpenAI compatible API for Ollama
            # Ensure Ollama is running and the model is available
            try:
                client = OpenAI(base_url=api_base, api_key="not-needed") # API key is ignored by Ollama
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "你是一位影片剪輯助手。"},
                        {"role": "user", "content": prompt}
                    ],
                     temperature=0.3 # Ollama might not support all parameters
                     # Ollama might not support all OpenAI parameters, temperature is usually ok
                )
                return response.choices[0].message.content
            except Exception as ollama_e:
                # Use root.after for messagebox from thread
                # messagebox.showerror("Ollama 錯誤", f"呼叫 Ollama 失敗，請檢查 Ollama 是否正在運行以及 API Base URL 和模型名稱是否正確。\n錯誤: {ollama_e}")
                print(f"❌ Ollama 呼叫失敗: {ollama_e}")
                traceback.print_exc()
                return None
        else:
            # Use root.after for messagebox from thread
            # messagebox.showerror("LLM 設定錯誤", f"未知的 LLM 類型: {llm_type}")
            return None

    except Exception as e:
        # Use root.after for messagebox from thread
        # messagebox.showerror("LLM 呼叫錯誤", f"呼叫 {llm_type.upper()} 失敗: {e}")
        print(f"❌ LLM 呼叫失敗: {e}")
        traceback.print_exc()
        return None

# --- Helper function for time formatting ---
def format_timedelta_srt(td: timedelta) -> str:
    """Formats a timedelta object into an SRT time string (HH:MM:SS,ms)."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    # Ensure milliseconds are exactly 3 digits
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

# Helper function to convert HH:MM:SS.ms string to total seconds
def hms_to_sec(hms: str) -> float:
    """Converts HH:MM:SS.ms string to total seconds."""
    try:
        # Handle potential HH:MM:SS format without milliseconds
        if '.' not in hms:
            hms += '.000'
        h, m, s_m = hms.split(":")
        s, mmm = s_m.split(".")
        return float(h) * 3600 + float(m) * 60 + float(s) + float(mmm) / 1000.0
    except ValueError as e:
        print(f"⚠️ 時間格式轉換錯誤：{hms} -> {e}")
        traceback.print_exc()
        return 0.0 # Return 0 or handle error appropriately


# --- Main Application Logic ---
class VideoEditorApp:
    """Main application class to manage workflow and GUI."""
    def __init__(self, root):
        self.root = root
        self.root.title("AI 影片剪輯助手")
        self.root.geometry("300x150")
        self.root.resizable(False, False) # Prevent resizing the main window

        self.video_path = None
        self.original_srt_path = None
        self.merged_video_path = None
        self.final_srt_path = None
        self.temp_clips = [] # List to store temporary clip paths

        load_config() # Load configuration at startup

        # --- Main Window Buttons ---
        tk.Button(self.root, text="設定", command=self.open_settings).pack(pady=10)
        tk.Button(self.root, text="選擇影片並開始處理", command=self.start_processing_workflow).pack(pady=10)
        tk.Button(self.root, text="離開", command=self.root.quit).pack(pady=10)

        # Status label (optional, can add to show progress)
        # self.status_label = tk.Label(self.root, text="等待操作...")
        # self.status_label.pack(pady=5)


    def open_settings(self):
        """Opens the settings window."""
        SettingsWindow(self.root)
        # Config will be reloaded in check_configuration or start_processing_workflow
        # after the settings window is closed and saved.


    def check_configuration(self):
        """Checks if essential configuration is valid before starting processing."""
        load_config() # Always reload config to get potential changes from settings window

        self.ffmpeg_path = app_config.get("ffmpeg_path")
        if not self.ffmpeg_path or not os.path.exists(self.ffmpeg_path):
            self.root.after(0, messagebox.showerror, "配置錯誤", "FFmpeg 路徑無效，請先進入設定頁面配置正確的路徑。")
            print("❌ FFmpeg 路徑無效")
            return False

        llm_type = app_config.get("llm_type")
        if llm_type == "gpt":
            if not app_config.get("gpt_api_key"):
                 self.root.after(0, messagebox.showerror, "配置錯誤", "已選擇 GPT 作為 LLM，但未配置 API Key。請先進入設定頁面配置。")
                 print("❌ GPT API Key 未配置")
                 return False
        elif llm_type == "ollama":
             if not app_config.get("ollama_api_base") or not app_config.get("ollama_model_name"):
                 self.root.after(0, messagebox.showerror, "配置錯誤", "已選擇 Ollama 作為 LLM，但未配置 API Base URL 或 模型名稱。請先進入設定頁面配置。")
                 print("❌ Ollama 配置不完整")
                 return False
        else:
             self.root.after(0, messagebox.showerror, "配置錯誤", f"未知的 LLM 類型 '{llm_type}'。請檢查設定。")
             print(f"❌ 未知 LLM 類型: {llm_type}")
             return False

        # Check if prompt template placeholder exists
        prompt_template = app_config.get("ai_prompt_template", "")
        if "{subtitle_content}" not in prompt_template:
             self.root.after(0, messagebox.showerror, "配置錯誤", "AI 提示詞模板中未包含必要的佔位符 {subtitle_content}。請修改設定。")
             print("❌ AI 提示詞模板缺少佔位符")
             return False


        self.output_dir = app_config.get("output_dir", "out")
        os.makedirs(self.output_dir, exist_ok=True)

        print("✅ 配置檢查通過")
        return True


    def start_processing_workflow(self):
        """Initiates the video selection and processing workflow."""
        # Check configuration before proceeding
        if not self.check_configuration():
            return # Stop if config is invalid

        # Start the rest of the workflow in a separate thread
        threading.Thread(target=self._processing_workflow_thread).start()


    def _processing_workflow_thread(self):
        """The main processing workflow run in a separate thread."""
        self.select_video() # This will call generate_subtitles_if_needed etc if a video is selected


    def select_video(self):
        """Opens file dialog to select the video."""
        # filedialog must be called from the main thread or a thread that has a Tk context.
        # Since start_processing_workflow is called from the main thread, and then this method
        # is called from the new thread, we need to use root.after to run file dialog in main thread.
        self.root.after(0, self._select_video_in_main_thread)

    def _select_video_in_main_thread(self):
        """Handles video selection in the main GUI thread."""
        self.video_path = filedialog.askopenfilename(title="選擇要剪輯的影片", filetypes=[("MP4 Files", "*.mp4")])
        if not self.video_path:
            self.root.after(0, messagebox.showinfo, "取消", "未選擇影片，處理流程結束")
            print("❌ 未選擇影片")
            return

        video_basename = os.path.splitext(os.path.basename(self.video_path))[0]
        # Assume original SRT is in the same directory as the video
        self.original_srt_path = os.path.join(os.path.dirname(self.video_path), video_basename + ".srt")
        self.merged_video_path = os.path.join(self.output_dir, "final_merged.mp4") # Changed name to avoid overwriting potential final output
        self.final_srt_path = os.path.join(self.output_dir, "final_merged.srt") # SRT for the merged video

        # Resume the processing workflow in the background thread
        threading.Thread(target=self._resume_processing_after_select).start()

    def _resume_processing_after_select(self):
         """Continues the workflow after video selection."""
         # Ensure necessary paths are set
         if not self.video_path:
              print("❌ 未選擇影片，無法繼續處理。")
              return

         self.generate_subtitles_if_needed()


    # --- The following methods are the core processing steps ---
    # They will be called sequentially (or triggered by user action like saving subtitles)

    def generate_subtitles_if_needed(self):
        """Generates initial SRT using Whisper if it doesn't exist."""
        # Use print statements for console feedback, maybe update a status label in GUI
        print("🔍 檢查原始影片字幕...")
        if not os.path.exists(self.original_srt_path):
            print("🔍 未找到原始影片字幕，使用 Whisper 產生中...")
            try:
                whisper_model_name = app_config.get("whisper_model", "small")
                print(f"✨ 使用 Whisper 模型：{whisper_model_name}")
                model = whisper.load_model(whisper_model_name)
                print("轉錄中，這可能需要一段時間...")
                # Pass video_path directly to transcribe
                # Use root.after for any messagebox calls from this thread
                result = model.transcribe(self.video_path, fp16=False, language="zh")

                with open(self.original_srt_path, "w", encoding="utf-8") as f:
                    for i, segment in enumerate(result["segments"]):
                        start_td = timedelta(seconds=segment['start'])
                        end_td = timedelta(seconds=segment['end'])
                        f.write(f"{i+1}\n{format_timedelta_srt(start_td)} --> {format_timedelta_srt(end_td)}\n{segment['text'].strip()}\n\n")
                print(f"✅ 原始影片字幕產生完成：{self.original_srt_path}")
            except Exception as e:
                # Use self.root.after to show error message from thread in main GUI thread
                self.root.after(0, messagebox.showerror, "Whisper 錯誤", f"原始影片字幕產生失敗: {e}")
                print(f"❌ 原始影片字幕產生失敗: {e}")
                traceback.print_exc() # Print detailed error info
                # Decide how to handle fatal errors - maybe go back to main window or quit
                return

        # Proceed after ensuring original SRT exists
        self.process_with_llm()

    def process_with_llm(self):
        """Reads subtitles, creates prompt, calls LLM, and initiates clipping."""
        print("🤖 準備呼叫 LLM 分析字幕...")
        try:
            with open(self.original_srt_path, "r", encoding="utf-8") as f:
                subs = list(srt.parse(f.read()))
        except FileNotFoundError:
            self.root.after(0, messagebox.showerror, "檔案錯誤", f"原始字幕檔案未找到: {self.original_srt_path}")
            print(f"❌ 原始字幕檔案未找到: {self.original_srt_path}")
            return
        except Exception as e:
            self.root.after(0, messagebox.showerror, "讀取錯誤", f"讀取原始字幕檔案失敗: {e}")
            print(f"❌ 讀取原始字幕檔案失敗: {e}")
            return


        字幕內容 = ""
        for sub in subs:
            # Format timedelta to match expected prompt format (HH:MM:SS.ms)
            start_td = sub.start
            end_td = sub.end
            # Use total_seconds for accurate floating point representation
            start_sec = start_td.total_seconds()
            end_sec = end_td.total_seconds()
            start_str = f"{int(start_sec // 3600):02}:{int((start_sec % 3600) // 60):02}:{start_sec % 60:06.3f}"
            end_str = f"{int(end_sec // 3600):02}:{int((end_sec % 3600) // 60):02}:{end_sec % 60:06.3f}"
            字幕內容 += f"[{start_str} - {end_str}] {sub.content.strip()}\n"

        # --- Use the configurable AI Prompt Template ---
        prompt_template = app_config.get("ai_prompt_template", DEFAULT_AI_PROMPT_TEMPLATE)

        # Basic check for placeholder (should be done in config check, but double check)
        if "{subtitle_content}" not in prompt_template:
             self.root.after(0, messagebox.showerror, "提示詞錯誤", "配置中的 AI 提示詞模板缺少必要的佔位符 {subtitle_content}。請檢查設定。")
             print("❌ AI 提示詞模板缺少佔位符，無法生成有效提示。")
             return

        try:
            # Format the final prompt by inserting the subtitle content
            ai_prompt = prompt_template.format(subtitle_content=字幕內容)
        except Exception as e:
            self.root.after(0, messagebox.showerror, "提示詞格式錯誤", f"格式化 AI 提示詞失敗: {e}。請檢查提示詞模板語法。")
            print(f"❌ 格式化 AI 提示詞失敗: {e}")
            traceback.print_exc()
            return


        ai_reply = call_llm(ai_prompt) # This call might block the thread

        if not ai_reply:
            # call_llm already shows error message
            print("❌ 從 LLM 獲得無效回覆")
            return

        print("🤖 AI 回應如下：\n", ai_reply)

        # --- START: Integrate time range processing from 4o.py ---
        print("⏳ 處理 AI 回應時間段，合併重疊/相近區段...")
        matches = re.findall(r'(\d{2}:\d{2}:\d{2}\.\d{3})\s*-\s*(\d{2}:\d{2}:\d{2}\.\d{3})', ai_reply)

        if not matches:
            self.root.after(0, messagebox.showwarning, "AI 警告", "AI 沒有回傳任何有效片段時間範圍。請檢查 LLM 回應格式是否正確。")
            print("⚠️ AI 沒有回傳任何有效片段")
            return

        # Sort matches by start time
        matches = sorted(matches, key=lambda x: hms_to_sec(x[0]))

        buffered_ranges = []
        buffer_time = app_config.get("buffer_time", 0.5)
        for start_str, end_str in matches:
            start_sec = max(0, hms_to_sec(start_str) - buffer_time)
            end_sec = hms_to_sec(end_str) + buffer_time
            if end_sec > start_sec: # Ensure end is after start after buffering
                buffered_ranges.append([start_sec, end_sec])

        # Sort buffered ranges by start time (redundant if matches were sorted, but safe)
        buffered_ranges = sorted(buffered_ranges, key=lambda x: x[0])

        merged_ranges = []
        merge_gap = 0.5 # Gap for merging adjacent clips (can be added to config later)
        for start, end in buffered_ranges:
            # Merge overlapping or adjacent (gap <= merge_gap) segments
            if not merged_ranges or start > merged_ranges[-1][1] + merge_gap:
                merged_ranges.append([start, end])
            else:
                # Extend the end time of the last merged range
                merged_ranges[-1][1] = max(merged_ranges[-1][1], end)

        # Filter merged ranges by minimum duration
        min_duration = app_config.get("min_duration", 2.0)
        final_clip_ranges = [[start, end] for start, end in merged_ranges if end - start >= min_duration]

        if not final_clip_ranges:
            self.root.after(0, messagebox.showwarning, "剪輯警告", "經過處理與合併後，沒有符合最小時長條件的剪輯片段。請檢查 AI 回應或調整設定 (緩衝時間/最小時長)。")
            print("❌ 經過處理後，沒有符合條件的剪輯片段")
            return

        print(f"✅ 處理後得到 {len(final_clip_ranges)} 個不重疊的剪輯時間段。")

        # --- END: Integrate time range processing from 4o.py ---


        self.clip_videos(final_clip_ranges) # Pass the final processed ranges


    def clip_videos(self, clip_ranges):
        """Clips video segments based on the processed ranges."""
        clip_list_path = os.path.join(self.output_dir, "list.txt")
        # Clear or create list.txt before clipping
        with open(clip_list_path, "w", encoding="utf-8") as list_file:
            pass

        print("✂️ 開始剪輯片段...")
        self.temp_clips = [] # Reset temp clips list for the new batch of clips
        successful_clips_count = 0

        # Iterate over the final_clip_ranges (merged and filtered)
        for i, (start, end) in enumerate(clip_ranges):
            duration = end - start
            clip_name = f"clip_{i:03d}.mp4"
            output_clip = os.path.join(self.output_dir, clip_name)
            # temp_clips will track all intended clip paths for cleanup
            self.temp_clips.append(output_clip)

            # FFmpeg command to clip - Using parameters from 4o.py
            # -ss and -t BEFORE -i, plus timestamp reset flags
            cmd = [
                self.ffmpeg_path,
                "-ss", f"{start:.3f}", # Start time (seconds, .ms)
                "-t",  f"{duration:.3f}", # Duration (seconds, .ms)
                "-i",  self.video_path,  # Input original video
                "-reset_timestamps", "1", # Reset timestamps to start from 0
                "-avoid_negative_ts", "make_zero", # Handle potential negative timestamps
                "-c:v", "copy", # Copy video stream (no re-encoding)
                "-c:a", "copy", # Copy audio stream (no re-encoding)
                output_clip,
                "-y" # Overwrite output file without asking
            ]
            print(f"  - 剪輯 {clip_name} (時間段: {start:.3f}s - {end:.3f}s, 時長: {duration:.3f}s)")

            try:
                # Adding creationflags=subprocess.CREATE_NO_WINDOW hides console window on Windows
                # Use capture_output=True and text=True with encoding="utf-8" for better error handling
                # Need to ensure this doesn't block the main thread if run directly
                # This method is called from a background thread, so subprocess.run is OK here.
                process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

                if process.returncode != 0:
                    print(f"❌ FFmpeg 剪輯 {clip_name} 失敗 (返回碼: {process.returncode}):")
                    print(process.stderr) # stderr is already text=True and decoded as utf-8
                    self.root.after(0, messagebox.showwarning, "剪輯失敗", f"剪輯片段 {clip_name} 失敗，請檢查控制台輸出。\n錯誤碼: {process.returncode}")
                    # Do NOT write to list.txt if failed
                else:
                    # Clip succeeded, append to list.txt
                    with open(clip_list_path, "a", encoding="utf-8") as list_file:
                         list_file.write(f"file '{os.path.basename(output_clip)}'\n") # Write just the filename
                    successful_clips_count += 1


            except Exception as e:
                print(f"❌ 剪輯片段 {i+1} 過程中發生錯誤: {e}")
                traceback.print_exc() # Print detailed error info
                self.root.after(0, messagebox.showwarning, "剪輯錯誤", f"剪輯片段 {clip_name} 過程中發生錯誤: {e}")
                # Continue to the next clip

        # After the loop, check if any clips were successfully added to the list
        if successful_clips_count == 0 or not os.path.exists(clip_list_path) or os.stat(clip_list_path).st_size == 0:
            self.root.after(0, messagebox.showwarning, "剪輯警告", "沒有成功生成任何剪輯片段，無法合併。請檢查控制台輸出的錯誤訊息。")
            print("⚠️ 沒有成功生成任何剪輯片段，無法合併。")
            self.cleanup_temp_clips() # Clean up any partially created files
        else:
            print(f"✅ 成功生成 {successful_clips_count} 個剪輯片段。")
            self.concatenate_clips(clip_list_path) # Proceed to concatenate


    def concatenate_clips(self, clip_list_path):
        """Concatenates the clipped video segments."""
        print("🚀 合併剪輯片段中...")
        # Ensure clip_list_path exists and is not empty before trying to concat
        if not os.path.exists(clip_list_path) or os.stat(clip_list_path).st_size == 0:
            print("❌ 合併列表檔案不存在或為空，跳過合併。")
            # Need to decide what to do if concat list is unexpectedly empty here
            # Probably just stop the process flow for this video.
            self.cleanup_temp_clips() # Clean up any partial clips
            return

        self.merged_video_path = os.path.join(self.output_dir, "final_merged.mp4") # Ensure path is set

        cmd_concat = [
            self.ffmpeg_path, "-f", "concat", "-safe", "0",
            "-i", clip_list_path,
            "-c:v", "copy", "-c:a", "copy",
            self.merged_video_path,
            "-y" # Overwrite output file without asking
        ]
        try:
            # Adding creationflags=subprocess.CREATE_NO_WINDOW hides console window on Windows
            # Use capture_output=True and text=True with encoding="utf-8" for better error handling
            # This is called from a background thread, subprocess.run is OK.
            process_concat = subprocess.run(cmd_concat, check=True, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            print(f"🎉 合併完成！輸出影片：{self.merged_video_path}")

            # Only cleanup temp clips if concatenation was successful
            self.cleanup_temp_clips()

            # Proceed to generate subtitles for the merged video
            self.generate_final_subtitles()

        except subprocess.CalledProcessError as e:
             self.root.after(0, messagebox.showerror, "FFmpeg 合併錯誤", f"合併失敗 (返回碼: {e.returncode}):\n{e.stderr}")
             print(f"❌ 合併失敗 (返回碼: {e.returncode}):\n{e.stderr}")
             traceback.print_exc() # Print detailed error info
             self.cleanup_temp_clips() # Clean up temp clips even if concat failed
        except Exception as e:
             self.root.after(0, messagebox.showerror, "合併錯誤", f"合併過程中發生錯誤: {e}")
             print(f"❌ 合併過程中發生錯誤: {e}")
             traceback.print_exc() # Print detailed error info
             self.cleanup_temp_clips() # Clean up temp clips

    # --- The rest of the methods (generate_final_subtitles, show_subtitle_editor,
    # save_edited_subtitles, prompt_final_merge, embed_subtitles_to_video, cleanup_temp_clips)
    # remain largely the same ---


    def generate_final_subtitles(self):
        """Generates new subtitles for the merged video."""
        print("🔍 為合併後的影片產生新字幕...")
        if not os.path.exists(self.merged_video_path):
             self.root.after(0, messagebox.showerror, "檔案錯誤", f"合併後的影片未找到: {self.merged_video_path}")
             print(f"❌ 合併後的影片未找到: {self.merged_video_path}")
             return

        try:
            whisper_model_name = app_config.get("whisper_model", "small")
            print(f"✨ 使用 Whisper 模型：{whisper_model_name}")
            model = whisper.load_model(whisper_model_name)
            print("轉錄合併後影片中，這可能需要一段時間...")
            # Transcribe the merged video
            # Use root.after for any messagebox calls from this thread
            result = model.transcribe(self.merged_video_path, fp16=False, language="zh")

            final_srt_content = ""
            for i, segment in enumerate(result["segments"]):
                start_td = timedelta(seconds=segment['start'])
                end_td = timedelta(seconds=segment['end'])
                final_srt_content += f"{i+1}\n{format_timedelta_srt(start_td)} --> {format_timedelta_srt(end_td)}\n{segment['text'].strip()}\n\n"

            print("✅ 新字幕產生完成，準備編輯")
            # Show the subtitle editor window (needs to run in the main GUI thread)
            self.root.after(0, self.show_subtitle_editor, final_srt_content)

        except Exception as e:
             self.root.after(0, messagebox.showerror, "Whisper 錯誤", f"為合併後影片產生新字幕失敗: {e}")
             print(f"❌ 為合併後影片產生新字幕失敗: {e}")
             traceback.print_exc() # Print detailed error info


    def show_subtitle_editor(self, subtitles_text):
        """Opens the subtitle editor window."""
        # This method is called via root.after, so it runs in the main thread
        editor_window = SubtitleEditorWindow(self.root, subtitles_text, self.save_edited_subtitles)
        self.root.wait_window(editor_window) # Pause main thread execution until editor closes

    def save_edited_subtitles(self, edited_text):
        """Saves the edited subtitles and prompts for final merge."""
        self.final_srt_path = os.path.join(self.output_dir, "final_merged.srt") # Ensure path is set
        try:
            with open(self.final_srt_path, "w", encoding="utf-8") as f:
                f.write(edited_text)
            print(f"✅ 字幕已儲存至：{self.final_srt_path}")
            # Now prompt the user for the final merge (needs to run in the main GUI thread)
            self.root.after(0, self.prompt_final_merge)
        except IOError as e:
             self.root.after(0, messagebox.showerror, "儲存錯誤", f"儲存編輯後的字幕失敗: {e}")
             print(f"❌ 儲存編輯後的字幕失敗: {e}")
             traceback.print_exc() # Print detailed error info

    def prompt_final_merge(self):
        """Asks the user for confirmation before embedding subtitles."""
        if messagebox.askyesno("確認合併", "字幕編輯完成，是否將編輯後的字幕嵌入到影片中？\n\n這將需要一段時間來重新編碼影片。", icon='question'):
            # Start embedding in a separate thread
            threading.Thread(target=self.embed_subtitles_to_video).start()
        else:
            messagebox.showinfo("取消", "最終合併已取消。處理完成，但字幕未嵌入。")
            # Decide if we should quit or just go back to main window
            # For now, let the main window stay open


    def embed_subtitles_to_video(self):
        """Embeds the edited subtitles into the merged video."""
        final_output_with_subs = os.path.join(self.output_dir, "final_with_subs.mp4")
        print(f"🚀 嵌入字幕中 ({self.final_srt_path})...")

        if not os.path.exists(self.merged_video_path):
             self.root.after(0, messagebox.showerror, "檔案錯誤", f"合併後的影片未找到: {self.merged_video_path}")
             print(f"❌ 合併後的影片未找到: {self.merged_video_path}")
             return
        if not os.path.exists(self.final_srt_path):
             self.root.after(0, messagebox.showerror, "檔案錯誤", f"編輯後的字幕檔案未找到: {self.final_srt_path}")
             print(f"❌ 編輯後的字幕檔案未找到: {self.final_srt_path}")
             return


        # FFmpeg command to embed subtitles (requires re-encoding video)
        # Using -c:v libx264 and -preset medium is a common choice.
        # Using forward slashes in the subtitles filter path is important for FFmpeg compatibility.
        video_codec_flags = ["-c:v", "libx264", "-preset", "medium", "-crf", "23"] # Hardcoded, could be in config
        audio_codec_flags = ["-c:a", "copy"]


        cmd_embed = [
            self.ffmpeg_path,
            "-i", self.merged_video_path,
            "-i", self.final_srt_path, # Input the new SRT file
            "-vf", f"subtitles='{self.final_srt_path.replace(os.sep, '/')}'", # subtitles filter with correct path syntax
            *video_codec_flags, # Video re-encoding flags
            *audio_codec_flags, # Audio copy flag
            final_output_with_subs,
            "-y" # Overwrite output file without asking
        ]
        print("FFmpeg command:", subprocess.list2cmdline(cmd_embed)) # Print command for debugging

        try:
            self.root.after(0, messagebox.showinfo, "開始嵌入", "即將開始嵌入字幕，這可能需要一些時間。請稍候...")
            # Capture stdout and stderr for better error reporting
            # Adding creationflags=subprocess.CREATE_NO_WINDOW hides console window on Windows
            # Use capture_output=True/PIPE, text=True, and encoding="utf-8"
            # This is called from a background thread, Popen is OK.
            process = subprocess.Popen(cmd_embed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)

            # Monitor progress (more advanced GUI needed for progress bar)
            # For now, just wait for it to finish
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                 error_output = stderr # stderr is already text=True and decoded as utf-8
                 self.root.after(0, messagebox.showerror, "FFmpeg 嵌入錯誤", f"嵌入字幕失敗 (返回碼: {process.returncode}).\nFFmpeg 輸出:\n{error_output[:1000]}...") # Show first 1000 chars
                 print(f"❌ 嵌入字幕失敗 (返回碼: {process.returncode}).\nFFmpeg 輸出:\n{error_output}")
                 traceback.print_exc() # Print detailed error info
            else:
                print(f"🎉 完成！帶字幕影片輸出：{final_output_with_subs}")
                self.root.after(0, messagebox.showinfo, "完成", f"影片處理完成！帶字幕影片輸出：\n{final_output_with_subs}")


        except Exception as e:
             self.root.after(0, messagebox.showerror, "嵌入錯誤", f"嵌入字幕過程中發生錯誤: {e}")
             print(f"❌ 嵌入字幕過程中發生錯誤: {e}")
             traceback.print_exc() # Print detailed error info
        finally:
             # Decide whether to automatically quit or stay open
             # self.root.quit() # Option to quit after final step
             pass


    def cleanup_temp_clips(self):
        """Cleans up temporary clipped video files."""
        print("🧹 清理臨時檔案中...")
        # Ensure temp_clips list is populated correctly during clipping
        for clip in self.temp_clips:
             if os.path.exists(clip):
                 try:
                     os.remove(clip)
                 except OSError as e:
                     print(f"⚠️ 無法刪除臨時檔案 {clip}: {e}")
        # Also remove the concat list file
        list_path = os.path.join(self.output_dir, "list.txt")
        if os.path.exists(list_path):
             try:
                 os.remove(list_path)
             except OSError as e:
                 print(f"⚠️ 無法刪除臨時檔案 {list_path}: {e}")
        print("🧹 清理臨時檔案完成")


# --- Entry Point ---
if __name__ == "__main__":
    root = tk.Tk()
    # Create the main application instance, which will set up the main window
    app = VideoEditorApp(root)
    # The main window is now visible and handles user interaction

    root.mainloop() # Start the Tkinter event loop