# Subtitle-Driven-AI-Clipper


Subtitle-Driven-AI-Clipper 是一個基於 Python 的應用程式，它利用先進的 AI 模型（如 OpenAI GPT 或 本地 Ollama）和 Whisper 語音轉文字技術，幫助使用者自動化影片的剪輯過程。本工具的核心理念是**通過分析影片的字幕內容，並結合使用者自定義的 AI 提示詞，智能地決定需要保留的影片片段**。隨後，它使用 FFmpeg 處理影片的剪輯與合併，並提供 GUI 界面供使用者編輯與嵌入最終的字幕。

這款工具特別適合用於從訪談、演講、課程或任何有字幕的影片中快速提取精華片段，節省手動觀看和剪輯的時間。

## 🚀 主要功能

* **字幕自動生成：** 使用強大的 Whisper 模型為原始影片生成精確的字幕 (如果原始影片沒有字幕檔)。
* **AI 智能剪輯決策：** 將字幕內容提供給可配置的 AI 模型，由 AI 根據內建或使用者自定義的提示詞決定要保留的影片片段時間範圍。
* **靈活的提示詞配置：** 透過 GUI 設定界面，使用者可以自由編輯 AI 提示詞模板，以指導 AI 根據特定標準（如剪輯亮點、提取特定主題、控制最終時長等）進行剪輯。
* **影片片段精確剪輯與合併：** 使用 FFmpeg 無損剪輯 AI 選定的影片片段，並將它們合併成一個新的影片。
* **合併後字幕重新生成與編輯：** 對合併後的影片重新生成精確的字幕，並提供 GUI 編輯界面供使用者精校字幕內容。
* **字幕嵌入影片：** 將編輯好的字幕永久燒錄到最終影片中。
* **支援多種 AI 模型：** 可配置使用 OpenAI GPT 系列模型或本地運行的 Ollama 模型。
* **直觀的 GUI 界面：** 提供圖形使用者界面，簡化操作流程。
* **外部依賴管理：** FFmpeg, 配置檔 (`config.json`), 輸出資料夾 (`out/`) 均可放置在應用程式執行檔的相對路徑旁，方便打包和發佈。

## 🎬 工作流程

1.  使用者選擇原始影片。
2.  程式自動生成原始影片字幕 (如果沒有)。
3.  程式將原始字幕內容發送給配置好的 AI 模型。
4.  AI 返回建議保留的影片時間範圍列表。
5.  程式根據 AI 回應，使用 FFmpeg 剪輯出所有建議的片段。
6.  程式將剪輯好的片段合併成一個新影片。
7.  程式對合併後的影片重新生成字幕。
8.  彈出字幕編輯器，供使用者修改字幕內容。
9.  使用者確認後，程式將編輯好的字幕嵌入到影片中。
10. 輸出最終帶有燒錄字幕的影片。

## 🛠️ 安裝步驟

### 前提條件

* **Python:** 確保你安裝了 Python 3.8 或更新版本。
* **FFmpeg:** 下載 FFmpeg 可執行檔。請訪問 [FFmpeg 官網](https://ffmpeg.org/download.html) 下載適用於你作業系統的版本。下載後，請確保 `ffmpeg.exe` (Windows) 或 `ffmpeg` (Linux/macOS) 可執行檔可以被程式訪問到（通常是放在程式執行檔所在目錄旁的 `ffmpeg/bin/` 資料夾中）。
* **OpenAI API Key (如果使用 GPT):** 如果你選擇使用 OpenAI GPT 模型，你需要一個有效的 OpenAI API Key。
* **Ollama (如果使用 Ollama):** 如果你選擇使用本地的 Ollama 模型，你需要先安裝並運行 Ollama 服務，並下載所需的模型。請訪問 [Ollama 官網](https://ollama.com/) 了解安裝方法。

### 獲取程式碼

克隆此 GitHub 倉庫到你的本地：

```bash
git clone [https://github.com/ddmmbb-2/Subtitle-Driven-AI-Clipper.git](https://github.com/ddmmbb-2/Subtitle-Driven-AI-Clipper.git) cd Subtitle-Driven-AI-Clipper
