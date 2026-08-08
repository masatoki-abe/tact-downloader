# tact-downloader

名古屋大学 TACT (Tokai Academic Combination Tools) から講義リソースと課題を自動ダウンロードする CLI ツール。

対応Pythonバージョンは **Python 3.10以上** です。TACTへの接続には、学内ネットワークまたはVPNが必要です。

## セットアップ

### 1. uvの導入と依存ライブラリのインストール

Arch Linuxでは次のコマンドで`uv`を導入します。

```bash
paru -S uv
uv sync
uv run playwright install chromium
npm ci
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
uv run pytest
uv run pytest --cov=tact_downloader --cov=main --cov-branch
uv run pyright
uv run pyright --project pyright-tests.json
uv run ruff check .
uv run ruff format --check .
npm exec --no -- prettier --check .
npm exec --no -- taplo format --check
uv run python scripts/check.py
```

コミット前の完全検査を自動化する場合は、初回だけ次を実行します。

```bash
uv sync
npm ci
uv run prek install
```

以後の`git commit`では、`prek`がlockファイルの整合性、Prettier、Taplo、Ruff、全テスト、branch coverageを自動的に確認します。いずれかが失敗した場合、コミットは作成されません。フォーマットの自動修正は行わないため、必要に応じて次を先に実行してください。

```bash
uv run ruff format .
npm exec --no -- prettier --write .
npm exec --no -- taplo format
```

`pyright`はPython 3.10を対象に、`main.py`、`tact_downloader/`、`scripts/`、`tests/`を`strict`モードで検査します。テスト固有の設定は`pyright-tests.json`で管理します。

classifierの期待値を更新する場合は、内容を確認したうえで次を実行します。

```bash
uv run python tests/generate_ans.py
```

## 使い方

```bash
# 講義サイト一覧表示
uv run python main.py --list

# 学期情報を検出できた全サイトを一括ダウンロード
uv run python main.py --all

# 特定サイトのみダウンロード
uv run python main.py --site 2025_XXXXXXX

# ダウンロード予定を表示（vault内は変更しない）
uv run python main.py --all --dry-run

# ダウンロード済みでも再取得
uv run python main.py --all --force

# 対話的にサイト選択
uv run python main.py
```

`--all` は、タイトルから学期情報を検出できたサイトだけを対象にします。学期未検出のサイトはスキップします。`--site` または対話選択では、学期未検出のサイトも指定できます。

リソースと課題は常に両方取得します。`--dry-run` は認証、TACT APIへのサイト・リソース・課題一覧取得、ローカルの既存ファイル確認を行いますが、vault内のファイルやディレクトリは作成・更新しません。保存Cookieの状態によっては、Cookieファイルの権限補正、作成、更新が発生する場合があります。既存の添付ファイルはスキップとして表示され、`--force --dry-run` では再取得予定として表示されます。課題Markdownは通常実行時に毎回更新されます。

## Obsidian連携

Obsidianのファイルエクスプローラからフォルダを右クリックしてダウンロードする場合は、初回だけ次を実行します。

```bash
# .env の VAULT_ROOT を使用
uv run python scripts/setup-obsidian.py

# vaultを明示
uv run python scripts/setup-obsidian.py /path/to/vault
```

この処理はShell Commandsプラグインをダウンロードして配置し、`TACT: 現在のフォルダをダウンロード` コマンドを登録します。既存のShell Commands設定は保持され、変更前の`data.json`と`community-plugins.json`はバックアップされます。セットアップ後、Obsidianを再起動してフォルダの右クリックメニューから実行してください。

| 右クリックするフォルダ         | 対象                                       |
| ------------------------------ | ------------------------------------------ |
| `大学/`                        | 学期情報がある全サイト                     |
| `大学/{年度}/`                 | 指定年度の学期情報がある全サイト           |
| `大学/{年度}/{学期}/`          | 指定年度・学期の全サイト                   |
| `大学/{年度}/{学期}/{授業名}/` | 指定授業のみ                               |
| `TACTリソース/` 以下           | `TACTリソース/` を除いた授業階層として判定 |
| `TACT課題/` 以下               | `TACT課題/` を除いた授業階層として判定     |

## ダウンロード先

vault内の `大学/{年度}/{学期n期}/{授業名}/TACTリソース/` と `TACT課題/` に保存。

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
│           └── TACT課題/
│               └── 課題タイトル/（同名の場合は課題タイトル--課題ID/）
│                   ├── 課題/
│                   │   ├── 本文.md
│                   │   └── 問題.pdf
│                   ├── 自分の提出/
│                   │   ├── 本文.md
│                   │   └── 回答.pdf
│                   └── 返却/
│                       ├── 講評.md
│                       └── 添削済み回答.pdf
```

## 差分管理

添付ファイルが既に存在する場合はスキップされます（パスベースの重複回避）。`--force` で添付を強制再ダウンロードできます。課題Markdownは実行ごとに原子的に更新されます。

## 学期情報の自動分類

講義サイトのタイトルから、次の形式の学期表記を自動検出します。末尾の丸括弧形式では、年度や時限を含めて記載できます。

- `春1期`, `春2期`, `秋1期`, `秋2期`, `春3期`, `秋3期`
- `春学期`, `秋学期`, `前期`, `後期`, `通年`
- `第1ターム`〜`第4ターム`
- `春A`〜`秋B` (クォーター制)
- `集中`, `特別`
- `科目名 (2025年度春1期/月2)` のような末尾括弧付き表記
- `【春1期】科目名`、`［後期］科目名`、`[春A]科目名` のような先頭タグ形式

全角の数字・英字は半角へ正規化して判定します。未対応の文字列を含む括弧は学期として採用しません。

自動検出できなかった場合は学期欄が空欄になります。その場合は手動でサイトタイトルに対応形式の学期情報を付与するか、`classifier.py` の `SEMESTER_PATTERNS` にパターンを追加してください。
