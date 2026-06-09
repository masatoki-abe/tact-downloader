# tact-downloader

名古屋大学 TACT (Tokai Academic Combination Tools) から講義リソースを自動ダウンロードする CLI ツール。

## セットアップ

### 1. 依存ライブラリのインストール

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 2. 環境設定

`.env.example` を `.env` にコピーして編集。

```bash
cp .env.example .env
```

| 変数             | 説明                                                        |
| ---------------- | ----------------------------------------------------------- |
| `TACT_BASE_URL`  | TACTのベースURL（既定値: `https://tact.ac.thers.ac.jp`）    |
| `VAULT_ROOT`     | Obsidian vault のルートパス                                 |
| `DOWNLOAD_BASE`  | vault内のダウンロード基点ディレクトリ（既定値: `大学`）     |

認証はブラウザ経由で行います。初回実行時に Chromium が起動するので、TACT に手動でログインしてください。Cookie は自動保存され、次回以降は再利用されます。

### 3. ネットワーク確認

TACTに学内ネットワークまたはVPN経由でアクセスできることを確認。

## 使い方

```bash
# 講義サイト一覧表示
venv/bin/python main.py --list

# 全サイト一括ダウンロード
venv/bin/python main.py --all

# 特定サイトのみダウンロード
venv/bin/python main.py --site 2025_XXXXXXX

# ダウンロードせず内容表示のみ
venv/bin/python main.py --all --dry-run

# ダウンロード済みでも再取得
venv/bin/python main.py --all --force

# 対話的にサイト選択
venv/bin/python main.py
```

## ダウンロード先

vault内の `大学/{年度}/{学期n期}/{授業名}/TACTリソース/` に保存。

```
大学/
├── 2025年度/
│   ├── 春1期/
│   │   └── 認知科学演習/
│   │       └── TACTリソース/
│   │           ├── 講義資料1.pdf
│   │           └── 課題説明.pptx
│   └── 秋1期/
│       └── メディア制度論/
│           └── TACTリソース/
│               └── ...
```

## 自動実行 (systemd timer)

```bash
# ユーザー service としてインストール
mkdir -p ~/.config/systemd/user
cp tact-downloader.service ~/.config/systemd/user/
cp tact-downloader.timer ~/.config/systemd/user/

# タイマー有効化
systemctl --user daemon-reload
systemctl --user enable --now tact-downloader.timer

# 状態確認
systemctl --user status tact-downloader.timer

# ログ確認
journalctl --user -u tact-downloader.service -f
```

既定では毎日 06:00 に実行（ランダム遅延最大10分）。TACTメンテナンス時間帯（03:00-06:00）の直後に設定。

## LiveSync 設定

LiveSyncで `.env` を同期対象から除外するには、Obsidianの `LiveSync` プラグイン設定で「除外ファイル」に `.env` を追加。

## 差分管理

ダウンロード済みファイルのURLは `{VAULT_ROOT}/.tact_history.json` に記録され、同一URLのファイルは再ダウンロードされない。`--force` で強制再ダウンロード可能。

## 学期情報の自動分類

講義サイトのタイトルに含まれる学期表記を正規表現で自動検出。対応パターン:

- `春1期`, `春2期`, `秋1期`, `秋2期`, `春3期`, `秋3期`
- `春学期`, `秋学期`, `前期`, `後期`, `通年`
- `第1ターム`〜`第4ターム`
- `春A`〜`秋B` (クォーター制)
- `【春1期】科目名` のような括弧付き表記

自動検出できなかった場合は学期欄が空欄になる。その場合は手動でサイトタイトルに学期情報を付与するか、`classifier.py` の `SEMESTER_PATTERNS` にパターンを追加。
