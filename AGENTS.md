# tact-downloader

名古屋大学 TACT (Sakai LMS) の講義リソースを Obsidian vault へダウンロードする CLI ツール。

## コマンド

```bash
venv/bin/python main.py [-v] [--list | --all | --site SITE_ID] [--dry-run] [--force]
```

- `--list` — サイト一覧表示。`--all` — 学期情報が検出されたサイトのみダウンロード（学期未検出のサイトはスキップ）。`--site` — 特定サイトのみ。省略時は対話的選択。
- テスト実行: `venv/bin/python -m pytest`
- classifierテストは `fixtures/titles_ans.json` とサイトID、タイトル、年度、学期、授業名を完全比較する。classifier 変更時は `generate_ans.py` で更新:
  ```bash
  venv/bin/python tests/generate_ans.py
   ```

- 品質確認:
  ```bash
  venv/bin/python -m ruff check .
  venv/bin/python -m ruff format --check .
  venv/bin/python -m pytest --cov=tact_downloader --cov=main --cov-branch
  ```

## セットアップ

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install -r requirements-dev.txt  # 開発・テスト時
venv/bin/playwright install chromium
cp .env.example .env   # 編集
```

`.env` は `tact_downloader/__init__.py` がプロジェクトルートから自動読み込みする。認証情報を含むため `.gitignore` で除外済み。

## Obsidian 連携

Obsidian のファイルエクスプローラでフォルダを右クリック → 階層に応じた TACT ダウンロードを実行できる。

```bash
venv/bin/python scripts/setup-obsidian.py             # .env の VAULT_ROOT を使用
venv/bin/python scripts/setup-obsidian.py /path/to/vault  # 明示的に指定
```

上記を実行すると以下が自動構成される:
- Shell Commands プラグインのダウンロード・配置
- フォルダ右クリックメニューに「TACT: 現在のフォルダをダウンロード」を追加
- community-plugins.json への登録

### 対応スコープ

| 右クリックするフォルダ         | ダウンロード対象         |
| ------------------------------ | ------------------------ |
| `大学/`                        | 学期情報がある全サイト   |
| `大学/{年度}/`                 | その年度の全サイト       |
| `大学/{年度}/{学期}/`          | その年度・学期の全サイト |
| `大学/{年度}/{学期}/{授業名}/` | その授業のみ             |

`TACTリソース/` 以下のサブフォルダを右クリックしても、自動的に授業フォルダとして認識される。

## モジュール構成

| モジュール                        | 役割                                                                         |
| --------------------------------- | ---------------------------------------------------------------------------- |
| `main.py`                         | エントリポイント。CLI 引数解析と全体制御                                     |
| `tact_downloader/__init__.py`     | 環境変数読み込み、定数定義                                                   |
| `tact_downloader/auth.py`         | ログイン処理（保存Cookie→自動ログイン→手動ログインの順）                     |
| `tact_downloader/classifier.py`   | 正規表現によるタイトル解析→年度/学期/授業名の抽出                            |
| `tact_downloader/client.py`       | Sakai `/direct/` REST API クライアント（ドメイン検証付き）                   |
| `tact_downloader/downloader.py`   | パス構築、ファイル名サニタイズ                                               |
| `tact_downloader/obsidian_cmd.py` | Obsidian Shell Commands 連携用。フォルダパスからスコープ判定してダウンロード |

認証フロー: `~/.tact_cookies.json` の保存 Cookie を優先試行。期限切れ時は Playwright で Chromium を起動し、環境変数に認証情報があれば自動ログイン（メール→パスワード→TOTP→サインイン維持→機構同意を順に操作）、なければ手動ログインを待つ。

## 非自明な点

- `pyproject.toml` にpytest、coverage、Ruffの設定がある。`setup.py`と型チェッカーの設定は存在しない。
- テストは `sys.path.insert(0, ...)` でパッケージを参照しており、正規インストールを必要としない。
- README には `.tact_history.json` による重複回避の記載があるが、実際のスキップ判定は `main.py` の `if not args.force and save_path.exists()` であり、履歴ファイルは書き込まれない。
- 学期パターンの拡張は `classifier.py` の `SEMESTER_PATTERNS` が変更箇所。学期設定を環境変数では変更しない。
- 全 TACT API 呼び出しは `TACTClient._validate_url()` を通過し、許可ドメイン外の URL は拒否される。
- Obsidian 連携は `scripts/setup-obsidian.py` が Shell Commands プラグインの全設定を自動生成する。端末ごとに手動設定は不要。
- `obsidian_cmd.py` のパス解析は `大学/` からの相対パスを3階層まで見る。`TACTリソース/` は自動無視される。
- 自動ログイン用の TOTP secret は `otpauth://...?secret=XXXX` の URL から抽出する。`auth.py` の `_ms_totp()` が `pyotp` でコード生成・入力を行う。
