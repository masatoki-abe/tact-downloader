# tact-downloader

名古屋大学 TACT (Tokai Academic Combination Tools) から講義リソースを自動ダウンロードする CLI ツール。

## セットアップ

### 1. 依存ライブラリのインストール

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install -r requirements-dev.txt  # 開発・テスト時
venv/bin/playwright install chromium
```

### 2. 環境設定

`.env.example` を `.env` にコピーして編集。

```bash
cp .env.example .env
```

| 変数                | 説明                                                     |
| ------------------- | -------------------------------------------------------- |
| `TACT_BASE_URL`     | TACTのベースURL（既定値: `https://tact.ac.thers.ac.jp`） |
| `VAULT_ROOT`        | Obsidian vault のルートパス                              |
| `DOWNLOAD_BASE`     | vault内のダウンロード基点ディレクトリ（既定値: `大学`）  |
| `THERS_EMAIL`       | 自動ログイン用のTHERSアカウントUPN（省略時は手動）       |
| `THERS_PASSWORD`    | THERSアカウントのパスワード                              |
| `THERS_TOTP_SECRET` | TOTPシークレット（pyotpでコード自動生成。省略時は手動）  |

認証は Chromium ブラウザ経由で行います。`THERS_EMAIL` / `THERS_PASSWORD` / `THERS_TOTP_SECRET` を `.env` に設定すると、メール・パスワード・TOTP・サインイン維持・機構同意画面まで自動で操作し、ログインを完結します。設定しない場合は従来通りブラウザが開くので手動でログインしてください。Cookie は自動保存され、次回以降は再利用されます。

認証情報の取り扱い:

- 保存Cookieは `~/.tact_cookies.json` に保存されます。ログイン状態を再現できる機密情報として扱い、他人へ共有したりリポジトリへ追加したりしないでください。
- Cookieファイルは所有者だけが読み書きできる権限で保存されます。不要になった場合は `rm ~/.tact_cookies.json` で削除してください。削除後は次回実行時に再認証が必要です。
- `.env` にはパスワードとTOTP secretが含まれるため、共有、コミット、公開バックアップへの保存を避けてください。必要に応じて `chmod 600 .env` を実行してください。
- `THERS_PASSWORD` と `THERS_TOTP_SECRET` は、Cookieと同様に認証情報として安全に管理してください。

### 3. ネットワーク確認

TACTに学内ネットワークまたはVPN経由でアクセスできることを確認。

### 4. テストと品質確認

```bash
venv/bin/python -m pytest
venv/bin/python -m pytest --cov=tact_downloader --cov=main --cov-branch
venv/bin/python -m ruff check .
venv/bin/python -m ruff format --check .
```

classifierの期待値を更新する場合は、内容を確認したうえで次を実行します。

```bash
venv/bin/python tests/generate_ans.py
```

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

## 差分管理

ダウンロード先にファイルが既に存在する場合はスキップされる（パスベースの重複回避）。`--force` で強制再ダウンロード可能。

## 学期情報の自動分類

講義サイトのタイトルに含まれる学期表記を正規表現で自動検出。対応パターン:

- `春1期`, `春2期`, `秋1期`, `秋2期`, `春3期`, `秋3期`
- `春学期`, `秋学期`, `前期`, `後期`, `通年`
- `第1ターム`〜`第4ターム`
- `春A`〜`秋B` (クォーター制)
- `【春1期】科目名` のような括弧付き表記

自動検出できなかった場合は学期欄が空欄になる。その場合は手動でサイトタイトルに学期情報を付与するか、`classifier.py` の `SEMESTER_PATTERNS` にパターンを追加。
