# MP3 Insight Player

Tkinter 桌面 MP3 播放器，可載入本地 MP3 或 MP3 網址，並以雲端語音轉文字與 LLM 分析擷取重點字詞、時間戳與重點句。

## 安裝

需要 Python 3.10+。建議在 Windows PowerShell 執行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

播放功能優先使用 `python-vlc`，電腦若已安裝 VLC media player 可取得較完整的播放能力。
若系統找不到 VLC，程式會改用 pygame 備援播放器，仍可播放本地快取 MP3、暫停、停止與跳播，但倍速能力會受限。

## 執行

```powershell
python main.py
```

## 使用方式

1. 在「播放器」分頁輸入 MP3 網址，或選擇本地 MP3。
2. 按「載入網址」或「開啟檔案」後即可播放。
3. 到「設定」分頁填入 Hugging Face Token。
4. 回「播放器」按「分析音訊」，程式會下載快取、轉錄、擷取關鍵詞與重點句。
5. 在「逐字稿」與「重點」分頁點擊時間碼，可跳到對應播放位置。
6. 可匯出 Markdown 或 JSON，方便整理筆記。
7. 在播放清單項目上按右鍵，可載入或刪除檔案快取、逐字稿與分析資料。
8. 在「設定」分頁可切換淺色 / 暗色模式，按「儲存設定」後立即套用。

## 資料位置

設定、歷史、快取與分析結果會存在 `%APPDATA%\Mp3InsightPlayer\`。

## 備註

- 若雲端 STT 沒有回傳時間戳，程式會用音訊長度與文字比例估算句段時間。
- ASR 預設使用 `openai/whisper-small`，這是較適合免費額度的輕量 Whisper 模型；也可改用 `openai/whisper-base` 或 `openai/whisper-tiny`。
- `facebook/wav2vec2-base-960h` 也較輕量，但主要適合英文音訊。
- 若沒有 Token，仍可播放、搜尋、匯出已存在資料，但不能執行雲端轉錄。
- 若 LLM 分析失敗，程式會使用本地關鍵詞備援，至少提供可用的關鍵詞清單。
- 若沒有安裝 VLC，程式會自動使用 pygame 備援播放；若播放無聲，請先確認系統音量與目前音訊輸出裝置。