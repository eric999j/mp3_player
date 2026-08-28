# MP3 Insight Player

Tkinter 桌面播放器：可載入本地 MP3、遠端 MP3 網址、以及 **YouTube 影片網址**（自動下載並顯示畫面），
再以本機 `faster-whisper` 轉錄語音，並可選用 Hugging Face LLM 擷取重點字詞、時間戳與重點句。

## 安裝

需要 Python 3.10+。建議在 Windows PowerShell 執行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

播放功能優先使用 `python-vlc`，並將 VLC 影像輸出繫結到 Tk 視窗，因此電腦已安裝 VLC media player 時可同時播放 **音訊 + 影片畫面**。
若系統找不到 VLC，程式會改用 pygame 備援播放器（僅支援音訊，且僅能播放本地快取檔）。

YouTube 支援由 `yt-dlp` 提供；預設會下載 720p 以下的預混流 mp4，
所以一般情況不需要額外安裝 ffmpeg。若某影片只提供分離視訊 / 音訊軌，
且要合併就需要系統上有 `ffmpeg`。

## 執行

```powershell
python main.py
```

## 使用方式

1. 在「播放器」分頁輸入 MP3 直連網址、YouTube 網址，或按「開啟檔案」選擇本地音訊 / 影片。
2. 按下 Enter 或「載入網址」，程式會自動判斷來源類型並下載到快取。
3. YouTube 或 mp4 等影片來源會在來源列下方的黑色畫面區顯示影像，音訊會一併播放。
4. 到「設定」分頁填入 Hugging Face Token（僅重點分析需要；轉錄在本機執行）。
5. 回「播放器」按「分析音訊」，程式會轉錄、擷取關鍵詞與重點句。
6. 在「逐字稿」與「重點」分頁點擊時間碼，可跳到對應播放位置。
7. 可匯出 Markdown 或 JSON，方便整理筆記。
8. 在播放清單項目上按右鍵，可載入、重新命名、重新分析或刪除快取與分析資料。
9. 在「設定」分頁可切換淺色 / 暗色模式，按「儲存設定」後立即套用。

鍵盤快捷鍵：`Space` 播放 / 暫停、`←` / `→` 微調 5 秒、`Ctrl+F` 聚焦逐字稿搜尋。

## 資料位置

設定、歷史、快取與分析結果會存在 `%APPDATA%\Mp3InsightPlayer\`。

## 備註

- 若雲端 STT 沒有回傳時間戳，程式會用音訊長度與文字比例估算句段時間。
- ASR 預設使用本機 `faster-whisper tiny`；可改為 `base`、`small`、`medium`、`large-v3`（首次使用會下載到 HuggingFace 快取）。
- 若沒有 Hugging Face Token，仍可播放、搜尋、匯出已存在資料；重點分析會退回本地 TF-IDF 備援。
- 若 LLM 分析失敗，程式會使用本地關鍵詞備援，至少提供可用的關鍵詞清單。
- 沒安裝 VLC 時，程式會自動使用 pygame 備援播放（音訊限定）；若播放無聲，請先確認系統音量與音訊輸出裝置。
- YouTube 私人 / 年齡限制影片可能會下載失敗；此時可考慮改用 mp3 直連網址或本地檔。
