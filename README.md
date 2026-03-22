

***

# 🎬 Subtitle-Driven-AI-Clipper (V2 終極升級版)

Subtitle-Driven-AI-Clipper 是一個基於 Python 開發的強大自動化影音剪輯工具。它巧妙地結合了 **WhisperX 字級語音辨識** 與 **大型語言模型 (OpenAI GPT / 本地 Ollama)**，透過「閱讀並理解」影片的對話內容，讓 AI 自動為你挑選、萃取出最精華的片段，並無縫合併為一支高質量的短影音。

這款工具特別適合用於：**遊戲實況精華剪輯、Podcast 訪談濃縮、長篇演講摘要**，能為創作者省下數十小時的「肉眼找素材」時間。

---

## 🔥 V2 版本重大突破 (Goodbye, 影音不同步！)

舊版本在處理長影片時，常遇到 FFmpeg `-c copy` 造成的關鍵幀誤差與音畫不同步。**V2 版本進行了底層邏輯的全面重構，徹底解決了這些痛點：**

* **強制固定幀率 (CFR) 預處理：** 導入素材時自動將所有影片洗成標準 30 FPS 與 44100Hz 音軌，徹底消滅手機或 OBS 錄影常見的可變幀率 (VFR) 延遲災難。
* **導入 WhisperX 毫秒級強制對齊：** 捨棄傳統 Whisper，改用精準度極高的 WhisperX。不僅支援「字級 (Word-level)」時間戳記，更能透過「語音停頓」進行完美的智慧斷句。
* **LLM 盲選編號機制 (防呆設計)：** 破解了 AI 時間數學極差的弱點！程式會將字幕轉為 `[1] 句子`、`[2] 句子` 的格式餵給 AI，AI 只需要回答「要保留的編號」，程式會自動去對應精準的毫秒時間，準確率直逼 100%。
* **精準重新編碼剪輯：** 捨棄粗糙的 `-c copy` 剪裁，改用 `libx264` 進行毫秒級精確切割，剪輯點乾淨俐落，畫面絕不卡頓。

---

## 🚀 核心功能

* **🗂️ 多檔無縫大混剪：** 支援一次匯入多支影片素材。程式會依檔名自動排序、合併成一支「超大母片 (Master Video)」後，再讓 AI 統整上下文進行精華萃取。
* **🤖 雙 AI 引擎自由切換：** 內建支援 OpenAI (GPT-4o 等) API，也完美支援本地端完全免費、注重隱私的 Ollama (Llama 3, Qwen 等) 模型。
* **✂️ 智慧分段防崩潰：** 針對超長影片，程式會自動將字幕以「每 30 句」為一組打包發送給 LLM，完美避開 AI 注意力渙散 (Lost in the middle) 或 API 記憶體溢出的問題。
* **🇹🇼 全自動繁體中文轉換：** 內建 `OpenCC` 套件，生成的字幕無論原本模型吐出什麼，最終都會強制轉換為台灣慣用的標準繁體中文。
* **📝 圖形化字幕校對器：** 最終精華影片生成後，會彈出 GUI 編輯器讓使用者進行最後的錯字校對，確認無誤後一鍵自動「燒錄 (Hardsub)」進影片中。

---

## 🎬 核心工作流程 (Workflow)

1.  **[多選匯入]** 使用者透過 GUI 一次選取多支原始影片。
2.  **[標準化合併]** 程式將所有素材轉為 CFR 並無縫合併為一支 `Master_Video.mp4`。
3.  **[精確聽打]** 使用 WhisperX 生成帶有完美斷句的母片字幕。
4.  **[AI 挑選]** 字幕分段送給 LLM，LLM 根據你的「提示詞」回傳該保留的精華句子「編號」。
5.  **[精確切割]** FFmpeg 依據編號還原出精確時間點，使用 `libx264` 精準切下所有精華。
6.  **[精華融合]** 將所有精華片段黏合成最終的 `final_merged_highlights.mp4`。
7.  **[最終聽打]** 對這支精華影片**重新跑一次** WhisperX，確保最終字幕的時間軸 100% 貼合畫面。
8.  **[校對與燒錄]** 彈出編輯器供使用者校對，確認後將字幕永久燒錄至影片。

---

## 🛠️ 安裝與環境建置

### 前提條件

1.  **Python:** 需安裝 Python 3.8 或以上版本。
2.  **FFmpeg:** 需下載 FFmpeg 可執行檔，並將其放置於程式目錄旁的 `ffmpeg/bin/` 資料夾中（或透過 GUI 手動指定路徑）。
3.  **NVIDIA GPU (強烈建議):** WhisperX 依賴強大的顯卡算力，建議配備 NVIDIA 獨立顯卡並安裝適用的 CUDA Toolkit (如 CUDA 12.1)。*(註：若無顯卡，程式將自動降級以 CPU 緩慢運行)*

### 獲取程式碼與安裝依賴

克隆此 GitHub 倉庫到你的本地，並安裝所需的 Python 套件：

```bash
git clone https://github.com/ddmmbb-2/Subtitle-Driven-AI-Clipper.git
cd Subtitle-Driven-AI-Clipper

# 建議安裝支援 GPU 的 PyTorch 版本 (請依據你的 CUDA 版本調整)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 安裝核心套件
pip install whisperx openai srt opencc
```

*(注意：Windows 用戶若在執行 WhisperX 時遇到 `cublas64_12.dll not found` 等錯誤，請確保已正確安裝 CUDA Toolkit 12 或是使用程式內建的 CPU 強制降級模式。)*

---

## ⚙️ 快速上手

1.  在終端機執行 `python newapp.py` (或你的主程式名稱) 啟動應用程式。
2.  點擊 **「設定」**：
    * 選擇你要使用的 LLM (OpenAI 或 Ollama)。
    * 輸入對應的 API Key 或 Base URL。
    * 確認 FFmpeg 路徑正確。
    * 可自定義 **AI 提示詞模板**，教導 AI 你的剪輯喜好（例如：「只保留好笑的段落」、「只保留有講到專有名詞的句子」）。
3.  點擊 **「選擇多段影片並開始處理」**，框選你的素材。
4.  放著讓電腦跑，喝杯咖啡，等著驗收你的精華短影音！

***
