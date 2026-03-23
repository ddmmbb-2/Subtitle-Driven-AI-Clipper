import os
import sys

# 保留這個路徑破解，以防萬一
current_dir = os.path.dirname(os.path.abspath(__file__))
if hasattr(os, 'add_dll_directory'):
    try:
        os.add_dll_directory(current_dir)
    except Exception:
        pass
os.environ['PATH'] = current_dir + os.pathsep + os.environ.get('PATH', '')

import subprocess
import srt
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from datetime import timedelta
import requests
import re
import json
import threading
import traceback
import torch
import whisperx  

# --- 引入繁簡轉換套件 ---
try:
    import opencc
    cc = opencc.OpenCC('s2twp') 
except ImportError:
    cc = None
    print("⚠️ 警告: 未安裝 opencc，將略過繁體轉換。建議執行 `pip install opencc`")

# --- Configuration Handling ---
CONFIG_FILE = "config.json"

DEFAULT_AI_PROMPT_TEMPLATE = """你是一位專業的短影音剪輯助理。
以下是標有編號的字幕段落：
{subtitle_content}
請根據這些內容，挑選出最精華、最連貫的段落來保留。
請**只回傳你想要保留的字幕編號**，數字之間用半形逗號分隔，例如：1, 3, 4, 8, 9, 10
(請列出所有要保留的數字，不要使用「3-5」這種連字號縮寫)

請不要提供任何解釋或額外文字，只能回傳數字和逗號。"""

DEFAULT_CONFIG = {
    "llm_type": "gpt",
    "gpt_api_key": "",
    "gpt_model_name": "gpt-4o-mini",
    "ollama_api_base": "http://localhost:11434/v1",
    "ollama_model_name": "llama3",
    "ffmpeg_path": "./ffmpeg/bin/ffmpeg.exe" if sys.platform == "win32" else "/usr/local/bin/ffmpeg",
    "output_dir": "out",
    "buffer_time": 0.5,
    "min_duration": 2.0,
    "whisper_model": "small",
    "ai_prompt_template": DEFAULT_AI_PROMPT_TEMPLATE
}

app_config = DEFAULT_CONFIG.copy()

def load_config():
    global app_config
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            try:
                loaded_config = json.load(f)
                if "ai_prompt_template" in loaded_config and isinstance(loaded_config["ai_prompt_template"], str):
                     loaded_config["ai_prompt_template"] = loaded_config["ai_prompt_template"].replace('\\n', '\n')
                for key, value in DEFAULT_CONFIG.items():
                     if key not in loaded_config or loaded_config[key] is None:
                         loaded_config[key] = value
                app_config.update(loaded_config)
                print("✅ 配置載入成功")
            except Exception as e:
                print(f"⚠️ 載入配置時發生錯誤: {e}，載入預設配置")
                app_config = DEFAULT_CONFIG.copy()
    else:
        app_config = DEFAULT_CONFIG.copy()

def save_config():
    global app_config
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(app_config, f, indent=4, ensure_ascii=False)
        print("✅ 配置儲存成功")
    except Exception as e:
         messagebox.showerror("儲存錯誤", f"儲存配置時發生錯誤: {e}")

# --- 進度視窗與日誌重導向 ---
class LogWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("執行進度與日誌 (關閉此視窗會隱藏，不會中斷)")
        self.geometry("700x500")
        self.protocol("WM_DELETE_WINDOW", self.hide_window)
        
        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, state=tk.DISABLED, bg="black", fg="lightgreen", font=("Consolas", 10))
        self.text_area.pack(expand=True, fill=tk.BOTH, padx=5, pady=5)
        
    def hide_window(self):
        self.withdraw()
        
    def add_log(self, message):
        self.text_area.config(state=tk.NORMAL)
        self.text_area.insert(tk.END, message + "\n")
        self.text_area.see(tk.END)
        self.text_area.config(state=tk.DISABLED)

class StreamRedirector:
    """攔截 print 輸出，導向至 Tkinter 視窗，防止包裝成 EXE 後崩潰"""
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.buffer = ""
        
    def write(self, text):
        if not text: return
        self.buffer += text
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            for line in lines[:-1]:
                if line.strip() or True: # Keep empty lines for formatting
                    self.log_callback(line)
            self.buffer = lines[-1]
            
    def flush(self):
        if self.buffer:
            self.log_callback(self.buffer)
            self.buffer = ""

# --- GUI Elements ---
class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定")
        self.geometry("600x700")
        self.transient(parent)
        self.grab_set()

        main_frame = tk.Frame(self)
        main_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        self.llm_type_var = tk.StringVar(value=app_config.get("llm_type", "gpt"))
        self.gpt_key_var = tk.StringVar(value=app_config.get("gpt_api_key", ""))
        self.gpt_model_var = tk.StringVar(value=app_config.get("gpt_model_name", "gpt-4o-mini"))
        self.ollama_base_var = tk.StringVar(value=app_config.get("ollama_api_base", "http://localhost:11434/v1"))
        self.ollama_model_var = tk.StringVar(value=app_config.get("ollama_model_name", "llama3"))
        self.ffmpeg_path_var = tk.StringVar(value=app_config.get("ffmpeg_path", DEFAULT_CONFIG["ffmpeg_path"]))
        self.whisper_model_var = tk.StringVar(value=app_config.get("whisper_model", "small"))
        self.buffer_time_var = tk.DoubleVar(value=app_config.get("buffer_time", 0.5))
        self.min_duration_var = tk.DoubleVar(value=app_config.get("min_duration", 2.0))

        llm_frame = tk.LabelFrame(main_frame, text="大型語言模型 (LLM) 設定")
        llm_frame.pack(pady=5, fill=tk.X)
        tk.Label(llm_frame, text="選擇 LLM:").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(llm_frame, text="OpenAI GPT", variable=self.llm_type_var, value="gpt", command=self._update_fields).pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(llm_frame, text="Ollama", variable=self.llm_type_var, value="ollama", command=self._update_fields).pack(side=tk.LEFT, padx=5)

        self.gpt_frame = tk.LabelFrame(main_frame, text="OpenAI GPT 設定")
        self.gpt_frame.pack(pady=5, fill=tk.X)
        tk.Label(self.gpt_frame, text="API Key:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.gpt_frame, textvariable=self.gpt_key_var, width=30, show='*').pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Label(self.gpt_frame, text="Model:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.gpt_frame, textvariable=self.gpt_model_var, width=15).pack(side=tk.LEFT, padx=5)

        self.ollama_frame = tk.LabelFrame(main_frame, text="Ollama 設定")
        self.ollama_frame.pack(pady=5, fill=tk.X)
        tk.Label(self.ollama_frame, text="API Base URL:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.ollama_frame, textvariable=self.ollama_base_var, width=30).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Label(self.ollama_frame, text="Model:").pack(side=tk.LEFT, padx=5)
        tk.Entry(self.ollama_frame, textvariable=self.ollama_model_var, width=15).pack(side=tk.LEFT, padx=5)

        other_frame = tk.LabelFrame(main_frame, text="其他設定")
        other_frame.pack(pady=5, fill=tk.X)
        tk.Label(other_frame, text="FFmpeg 路徑:").pack(side=tk.LEFT, padx=5)
        tk.Entry(other_frame, textvariable=self.ffmpeg_path_var, width=30).pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        tk.Button(other_frame, text="瀏覽", command=self._select_ffmpeg).pack(side=tk.LEFT, padx=5)
        tk.Label(other_frame, text="Whisper Model:").pack(side=tk.LEFT, padx=(15,5))
        tk.Entry(other_frame, textvariable=self.whisper_model_var, width=10).pack(side=tk.LEFT, padx=5)

        timing_frame = tk.Frame(other_frame)
        timing_frame.pack(pady=5, fill=tk.X)
        tk.Label(timing_frame, text="緩衝時間 (秒):").pack(side=tk.LEFT, padx=5)
        tk.Entry(timing_frame, textvariable=self.buffer_time_var, width=8).pack(side=tk.LEFT, padx=5)
        tk.Label(timing_frame, text="最小片段時長 (秒):").pack(side=tk.LEFT, padx=5)
        tk.Entry(timing_frame, textvariable=self.min_duration_var, width=8).pack(side=tk.LEFT, padx=5)

        prompt_frame = tk.LabelFrame(main_frame, text="AI 提示詞模板設定 (使用 {subtitle_content} 插入字幕)")
        prompt_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap=tk.WORD, width=70, height=10)
        self.prompt_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)
        self.prompt_text.insert(tk.END, app_config.get("ai_prompt_template", DEFAULT_AI_PROMPT_TEMPLATE))

        tk.Button(main_frame, text="儲存設定", command=self._save_and_close).pack(pady=10)
        self._update_fields()

    def _update_fields(self):
        llm_type = self.llm_type_var.get()
        state_gpt = tk.NORMAL if llm_type == "gpt" else tk.DISABLED
        state_ollama = tk.NORMAL if llm_type == "ollama" else tk.DISABLED
        for child in self.gpt_frame.winfo_children(): child.config(state=state_gpt)
        for child in self.ollama_frame.winfo_children(): child.config(state=state_ollama)

    def _select_ffmpeg(self):
        path = filedialog.askopenfilename(title="選擇 FFmpeg 執行檔", filetypes=[("Executables", "*.exe;*"), ("All files", "*.*")])
        if path: self.ffmpeg_path_var.set(path)

    def _save_and_close(self):
        global app_config
        try:
            app_config["llm_type"] = self.llm_type_var.get()
            app_config["gpt_api_key"] = self.gpt_key_var.get()
            app_config["gpt_model_name"] = self.gpt_model_var.get()
            app_config["ollama_api_base"] = self.ollama_base_var.get()
            app_config["ollama_model_name"] = self.ollama_model_var.get()
            app_config["ffmpeg_path"] = self.ffmpeg_path_var.get()
            app_config["whisper_model"] = self.whisper_model_var.get()
            app_config["buffer_time"] = self.buffer_time_var.get()
            app_config["min_duration"] = self.min_duration_var.get()
            app_config["ai_prompt_template"] = self.prompt_text.get("1.0", tk.END).strip()
            save_config()
            self.destroy()
        except Exception as e:
             messagebox.showerror("儲存錯誤", f"儲存設定時發生錯誤: {e}")

class SubtitleEditorWindow(tk.Toplevel):
    def __init__(self, parent, subtitles_text, save_callback):
        super().__init__(parent)
        self.title("編輯字幕 (這將是最終精華影片的字幕)")
        self.geometry("700x500")
        self.transient(parent)
        self.grab_set()
        self.save_callback = save_callback

        tk.Label(self, text="請確認/編輯最終精華影片的字幕內容：").pack(pady=5)
        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, width=80, height=25)
        self.text_area.insert(tk.END, subtitles_text)
        self.text_area.pack(pady=10, padx=10, expand=True, fill=tk.BOTH)
        tk.Button(self, text="儲存並繼續嵌入影片", command=self._save_and_close).pack(pady=10)

    def _save_and_close(self):
        self.save_callback(self.text_area.get("1.0", tk.END).strip())
        self.destroy()

# --- LLM Abstraction ---
def call_llm(prompt):
    from openai import OpenAI
    llm_type = app_config.get("llm_type", "gpt")
    model_name = app_config.get("gpt_model_name") if llm_type == "gpt" else app_config.get("ollama_model_name")
    print(f"🤖 呼叫 {llm_type.upper()} 模型：{model_name}")

    try:
        if llm_type == "gpt":
            client = OpenAI(api_key=app_config.get("gpt_api_key"))
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": "你是一位影片剪輯助手。"}, {"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content
        elif llm_type == "ollama":
            client = OpenAI(base_url=app_config.get("ollama_api_base"), api_key="not-needed")
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": "你是一位影片剪輯助手。"}, {"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content
    except Exception as e:
        print(f"❌ LLM 呼叫失敗: {e}")
        return None

def format_timedelta_srt(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = td.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def hms_to_sec(hms: str) -> float:
    try:
        if '.' not in hms: hms += '.000'
        h, m, s_m = hms.split(":")
        s, mmm = s_m.split(".")
        return float(h) * 3600 + float(m) * 60 + float(s) + float(mmm) / 1000.0
    except ValueError:
        return 0.0

def write_aligned_srt(aligned_result, srt_path, pause_threshold=0.4, max_chars=35):
    with open(srt_path, "w", encoding="utf-8") as f:
        valid_index = 1
        for segment in aligned_result["segments"]:
            if "words" in segment and len(segment["words"]) > 0:
                current_text = ""
                line_start = None
                line_end = None
                
                for word_obj in segment["words"]:
                    w_text = word_obj.get("word", "")
                    if not w_text.strip(): continue
                    
                    w_start = word_obj.get("start")
                    w_end = word_obj.get("end")
                    
                    # 停頓計算
                    if line_end is not None and w_start is not None:
                        gap = w_start - line_end
                        if gap >= pause_threshold or len(current_text.strip()) >= max_chars:
                            start_td = timedelta(seconds=line_start)
                            end_td = timedelta(seconds=line_end)
                            text_to_write = current_text.strip()
                            if cc:
                                text_to_write = cc.convert(text_to_write)
                                
                            f.write(f"{valid_index}\n{format_timedelta_srt(start_td)} --> {format_timedelta_srt(end_td)}\n{text_to_write}\n\n")
                            valid_index += 1
                            
                            current_text = ""
                            line_start = None
                            line_end = None
                            
                    if line_start is None and w_start is not None:
                        line_start = w_start
                    if w_end is not None:
                        line_end = w_end
                        
                    current_text += w_text
                
                if current_text.strip() and line_start is not None and line_end is not None:
                    start_td = timedelta(seconds=line_start)
                    end_td = timedelta(seconds=line_end)
                    text_to_write = current_text.strip()
                    if cc:
                        text_to_write = cc.convert(text_to_write)
                    f.write(f"{valid_index}\n{format_timedelta_srt(start_td)} --> {format_timedelta_srt(end_td)}\n{text_to_write}\n\n")
                    valid_index += 1
                    
            else:
                if 'start' in segment and 'end' in segment:
                    start_td = timedelta(seconds=segment['start'])
                    end_td = timedelta(seconds=segment['end'])
                    text_to_write = segment['text'].strip()
                    if cc:
                        text_to_write = cc.convert(text_to_write)
                    f.write(f"{valid_index}\n{format_timedelta_srt(start_td)} --> {format_timedelta_srt(end_td)}\n{text_to_write}\n\n")
                    valid_index += 1

# --- Main Application Logic ---
class VideoEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 智慧剪輯 (模組化聽打版)")
        self.root.geometry("350x150")
        self.root.resizable(False, False)

        self.video_paths = [] 
        self.temp_files_to_delete = [] 
        self.temp_clips = []
        
        # GPU/CPU 運行參數
        self.ai_device = "cpu"
        self.ai_compute_type = "int8"
        
        load_config()

        # 建立進度視窗並重導向 print
        self.log_window = LogWindow(self.root)
        self.log_window.withdraw() # 初始隱藏
        
        redirector = StreamRedirector(self._gui_log)
        sys.stdout = redirector
        sys.stderr = redirector

        tk.Button(self.root, text="設定", command=self.open_settings).pack(pady=10)
        tk.Button(self.root, text="選擇多段影片並開始處理", command=self.start_processing_workflow).pack(pady=10)
        tk.Button(self.root, text="離開", command=self.root.quit).pack(pady=10)

    def _gui_log(self, message):
        """將日誌拋回主執行緒更新 UI"""
        self.root.after(0, self.log_window.add_log, message)

    def open_settings(self):
        SettingsWindow(self.root)

    def check_configuration(self):
        load_config()
        self.ffmpeg_path = app_config.get("ffmpeg_path")
        if not self.ffmpeg_path or not os.path.exists(self.ffmpeg_path):
            self.root.after(0, messagebox.showerror, "配置錯誤", "FFmpeg 路徑無效。")
            return False
        self.output_dir = app_config.get("output_dir", "out")
        os.makedirs(self.output_dir, exist_ok=True)
        return True

    def start_processing_workflow(self):
        if not self.check_configuration(): return
        
        filenames = filedialog.askopenfilenames(title="選擇影片 (將依檔名順序合併後再統一剪輯)", filetypes=[("Video Files", "*.mp4;*.mkv;*.mov")])
        if not filenames: return
        self.video_paths = sorted(list(filenames))
        
        # 顯示日誌視窗
        self.log_window.deiconify()
        
        # 開啟獨立 Thread 防止主視窗卡死
        threading.Thread(target=self._processing_workflow_thread, daemon=True).start()

    def _processing_workflow_thread(self):
        # 1. 環境檢測 (自動判斷 GPU / CPU)
        self.test_environment()
        
        # 2. 準備路徑
        self.master_video_path = os.path.join(self.output_dir, "00_Master_Input.mp4") 
        self.master_srt_path = os.path.join(self.output_dir, "00_Master_Input.srt")   
        self.merged_video_path = os.path.join(self.output_dir, "final_merged_highlights.mp4") 
        self.final_srt_path = os.path.join(self.output_dir, "final_merged_highlights.srt") 

        self.temp_files_to_delete = []
        self.temp_clips = []

        self._prepare_and_process_master_video()

    def test_environment(self):
        print("\n" + "="*50)
        print("🔍 [硬體檢測] 測試 WhisperX 硬體加速支援度...")
        try:
            if torch.cuda.is_available():
                print("✨ 偵測到 CUDA，測試 GPU 記憶體分配...")
                _ = torch.zeros(1).cuda() # 實際拋到 GPU 測試
                self.ai_device = "cuda"
                self.ai_compute_type = "float16"
                print(f"✅ 測試成功！將使用硬體加速: {self.ai_device} ({self.ai_compute_type})")
            else:
                print("⚠️ 未偵測到 CUDA (或未安裝 PyTorch CUDA 版本)。")
                self.ai_device = "cpu"
                self.ai_compute_type = "int8"
                print(f"✅ 將降級使用安全模式: {self.ai_device} ({self.ai_compute_type})")
        except Exception as e:
            print(f"❌ GPU 測試發生錯誤: {e}")
            self.ai_device = "cpu"
            self.ai_compute_type = "int8"
            print(f"✅ 強制降級使用安全模式: {self.ai_device} ({self.ai_compute_type})")
        print("="*50 + "\n")

    def run_whisperx(self, input_video, output_srt):
        if os.path.exists(output_srt):
            print(f"✅ 已找到現有字幕檔案：{output_srt}")
            return True

        print(f"\n🔍 開始使用 WhisperX 處理影片：{os.path.basename(input_video)}")
        try:
            whisper_model_name = app_config.get("whisper_model", "small")
            
            print(f"✨ 載入模型 {whisper_model_name} (這可能需要一段時間)...")
            model = whisperx.load_model(whisper_model_name, self.ai_device, compute_type=self.ai_compute_type)
            audio = whisperx.load_audio(input_video)
            
            print("✨ 進行初步轉錄...")
            result = model.transcribe(audio, batch_size=1)
            
            print("✨ 進行字級時間軸強制對齊 (Forced Alignment)...")
            language_code = result["language"] 
            model_a, metadata = whisperx.load_align_model(language_code=language_code, device=self.ai_device)
            aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, self.ai_device, return_char_alignments=False)
            
            print("✨ 根據語音停頓進行智慧斷句並轉換繁體...")
            write_aligned_srt(aligned_result, output_srt)
            
            print(f"✅ 字幕產生完成：{output_srt}")
            return True
        except Exception as e:
            print(f"❌ WhisperX 處理失敗: {e}")
            traceback.print_exc()
            return False

    def _prepare_and_process_master_video(self):
        print("🎬 [階段一] 將所有素材標準化並合併為「單一超大影片」")

        raw_concat_list_path = os.path.join(self.output_dir, "raw_concat_list.txt")
        self.temp_files_to_delete.append(raw_concat_list_path)

        with open(raw_concat_list_path, "w", encoding="utf-8") as f:
            for idx, vp in enumerate(self.video_paths):
                print(f"⚙️ 正在標準化第 {idx+1}/{len(self.video_paths)} 支影片...")
                temp_cfr_path = os.path.join(self.output_dir, f"temp_raw_{idx:03d}.mp4")
                self.temp_files_to_delete.append(temp_cfr_path)

                if not os.path.exists(temp_cfr_path):
                    cmd = [
                        self.ffmpeg_path, "-i", vp,
                        "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-c:a", "aac", "-ar", "44100", "-y", temp_cfr_path
                    ]
                    process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    if process.returncode != 0:
                        print(f"❌ 標準化失敗: {vp}\n{process.stderr}")
                        continue

                f.write(f"file '{os.path.basename(temp_cfr_path)}'\n")

        print("\n🚀 正在將所有標準化素材無縫合併成 Master Video...")
        if not os.path.exists(self.master_video_path):
            cmd_concat = [
                self.ffmpeg_path, "-f", "concat", "-safe", "0",
                "-i", raw_concat_list_path,
                "-c:v", "copy", "-c:a", "copy", "-y", self.master_video_path
            ]
            process = subprocess.run(cmd_concat, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if process.returncode != 0:
                print(f"❌ Master 合併失敗:\n{process.stderr}")
                return
        print(f"✅ Master Video 建立完成！存放於：{self.master_video_path}")

        self.video_path = self.master_video_path
        self.original_srt_path = self.master_srt_path

        print("\n" + "="*50)
        print("🎬 [階段二] 開始對 Master Video 進行 AI 聽打與精華剪輯")
        print("="*50)

        if not self.run_whisperx(self.master_video_path, self.master_srt_path):
            return
        
        self.process_with_llm()

    def process_with_llm(self):
        print("🤖 準備呼叫 LLM 分析總字幕 (編號盲選模式)...")
        try:
            with open(self.original_srt_path, "r", encoding="utf-8") as f:
                subs = list(srt.parse(f.read()))
        except Exception as e:
            print(f"❌ 讀取字幕檔案失敗: {e}")
            return

        prompt_template = app_config.get("ai_prompt_template", DEFAULT_AI_PROMPT_TEMPLATE)
        CHUNK_SIZE = 30  
        all_matches = []  

        for i in range(0, len(subs), CHUNK_SIZE):
            chunk_subs = subs[i:i + CHUNK_SIZE]
            字幕內容 = ""
            
            for local_idx, sub in enumerate(chunk_subs):
                字幕內容 += f"[{local_idx + 1}] {sub.content.strip()}\n"

            print(f"⏳ 正在呼叫 LLM 處理第 {i+1} 到 {min(i+CHUNK_SIZE, len(subs))} 句字幕...")
            
            try:
                ai_prompt = prompt_template.format(subtitle_content=字幕內容)
                ai_reply = call_llm(ai_prompt)

                if ai_reply:
                    numbers = re.findall(r'\d+', ai_reply)
                    selected_indices = [int(n) for n in numbers]
                    
                    matches_in_chunk = 0
                    for idx in selected_indices:
                        if 1 <= idx <= len(chunk_subs):
                            sub = chunk_subs[idx - 1] 
                            start_sec = sub.start.total_seconds()
                            end_sec = sub.end.total_seconds()
                            start_str = f"{int(start_sec // 3600):02}:{int((start_sec % 3600) // 60):02}:{start_sec % 60:06.3f}"
                            end_str = f"{int(end_sec // 3600):02}:{int((end_sec % 3600) // 60):02}:{end_sec % 60:06.3f}"
                            all_matches.append((start_str, end_str))
                            matches_in_chunk += 1
                            
                    print(f"  ✅ 此段落 AI 挑選了 {matches_in_chunk} 句話")
                else:
                    print("  ⚠️ 逾時或無效回傳，跳過...")
            except Exception as e:
                print(f"  ❌ 處理此段落時發生錯誤: {e}")
                continue 

        if not all_matches:
            print("⚠️ 處理完畢，無有效片段。")
            self.cleanup_temp_clips()
            return

        print(f"🎉 LLM 解析完成！開始過濾與合併相鄰片段...")
        all_matches = sorted(all_matches, key=lambda x: hms_to_sec(x[0]))

        buffered_ranges = []
        buffer_time = app_config.get("buffer_time", 0.5)
        for start_str, end_str in all_matches:
            start_sec = max(0, hms_to_sec(start_str) - buffer_time)
            end_sec = hms_to_sec(end_str) + buffer_time
            if end_sec > start_sec:
                buffered_ranges.append([start_sec, end_sec])

        merged_ranges = []
        for start, end in buffered_ranges:
            if not merged_ranges or start > merged_ranges[-1][1] + 0.5:
                merged_ranges.append([start, end])
            else:
                merged_ranges[-1][1] = max(merged_ranges[-1][1], end)

        min_duration = app_config.get("min_duration", 2.0)
        final_clip_ranges = [[start, end] for start, end in merged_ranges if end - start >= min_duration]

        if final_clip_ranges:
            print(f"✅ 確認需要剪輯 {len(final_clip_ranges)} 個精華片段。")
            self.clip_videos(final_clip_ranges)
        else:
            print("❌ 過濾後無符合時長的片段。")
            self.cleanup_temp_clips()

    def clip_videos(self, clip_ranges):
        clip_list_path = os.path.join(self.output_dir, "list.txt")
        with open(clip_list_path, "w", encoding="utf-8") as list_file: pass

        print("✂️ 開始從 Master Video 中萃取精華片段...")
        self.temp_clips = []
        successful_clips_count = 0

        for i, (start, end) in enumerate(clip_ranges):
            duration = end - start
            clip_name = f"clip_{i:03d}.mp4"
            output_clip = os.path.join(self.output_dir, clip_name)
            self.temp_clips.append(output_clip)

            cmd = [
                self.ffmpeg_path,
                "-ss", f"{start:.3f}", 
                "-i",  self.video_path,  
                "-t",  f"{duration:.3f}", 
                "-c:v", "libx264",       
                "-preset", "veryfast",   
                "-crf", "22",            
                "-c:a", "aac",           
                "-async", "1",           
                "-avoid_negative_ts", "make_zero",
                output_clip,
                "-y" 
            ]
            print(f"  - 擷取 {clip_name} ({start:.3f}s - {end:.3f}s)")

            try:
                process = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if process.returncode == 0:
                    with open(clip_list_path, "a", encoding="utf-8") as list_file:
                         list_file.write(f"file '{clip_name}'\n")
                    successful_clips_count += 1
                else:
                    print(f"❌ 擷取失敗: {process.stderr}")
            except Exception as e:
                print(f"❌ 擷取異常: {e}")

        if successful_clips_count > 0:
            self.concatenate_clips(clip_list_path)
        else:
            self.cleanup_temp_clips()

    def concatenate_clips(self, clip_list_path):
        print("\n🚀 正在將所有精華片段黏合成最終影片...")
        
        cmd_concat = [
            self.ffmpeg_path, "-f", "concat", "-safe", "0",
            "-i", clip_list_path,
            "-c:v", "copy",
            "-c:a", "copy",
            self.merged_video_path,
            "-y"
        ]
        try:
            subprocess.run(cmd_concat, check=True, capture_output=True, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            print(f"🎉 精華合併完成！輸出於：{self.merged_video_path}")
            
            print("\n" + "="*50)
            print("🎬 [階段三] 為最終精華影片重新製作完美對齊的字幕")
            print("="*50)
            if self.run_whisperx(self.merged_video_path, self.final_srt_path):
                with open(self.final_srt_path, "r", encoding="utf-8") as f:
                    final_srt_content = f.read()
                self.root.after(0, self.show_subtitle_editor, final_srt_content)
                
        except Exception as e:
             print(f"❌ 合併異常: {e}")
        finally:
             self.cleanup_temp_clips()

    def show_subtitle_editor(self, subtitles_text):
        editor_window = SubtitleEditorWindow(self.root, subtitles_text, self.save_edited_subtitles)
        self.root.wait_window(editor_window)

    def save_edited_subtitles(self, edited_text):
        try:
            with open(self.final_srt_path, "w", encoding="utf-8") as f:
                f.write(edited_text)
            self.root.after(0, self.prompt_final_merge)
        except IOError as e:
            print(f"❌ 儲存字幕失敗: {e}")

    def prompt_final_merge(self):
        if messagebox.askyesno("確認燒錄", "是否將最終字幕燒錄（嵌入）到精華影片中？", icon='question'):
            threading.Thread(target=self.embed_subtitles_to_video, daemon=True).start()

    def embed_subtitles_to_video(self):
        final_output_with_subs = os.path.join(self.output_dir, "final_with_subs.mp4")
        print(f"🚀 燒錄字幕中，請稍等...")

        cmd_embed = [
            self.ffmpeg_path,
            "-i", self.merged_video_path,
            "-i", self.final_srt_path,
            "-vf", f"subtitles='{self.final_srt_path.replace(os.sep, '/')}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "copy",
            final_output_with_subs,
            "-y"
        ]
        
        try:
            process = subprocess.Popen(cmd_embed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            stdout, stderr = process.communicate()
            if process.returncode == 0:
                print(f"🎉 完成！帶有字幕的精華輸出於：{final_output_with_subs}")
                self.root.after(0, messagebox.showinfo, "完成", f"處理完成！\n{final_output_with_subs}")
            else:
                print(f"❌ 燒錄報錯: {stderr}")
        except Exception as e:
             print(f"❌ 燒錄異常: {e}")

    def cleanup_temp_clips(self):
        print("🧹 正在清理暫存檔案，釋放硬碟空間...")
        
        for f in self.temp_files_to_delete:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
                
        for clip in self.temp_clips:
            if os.path.exists(clip):
                try: os.remove(clip)
                except: pass
                
        list_path = os.path.join(self.output_dir, "list.txt")
        if os.path.exists(list_path):
             try: os.remove(list_path)
             except: pass

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoEditorApp(root)
    root.mainloop()
