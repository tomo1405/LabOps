# 研究室統合プラットフォーム（SELAPO）

研究室運営に関わる業務を1つにまとめた Web アプリケーション。
上位文書は以下の3点で、本リポジトリはその下流工程（実装）にあたる。

- [要件定義書](docs/01_要件定義/要件定義書_研究室統合プラットフォーム.md)
- [基本設計書](docs/02_基本設計/基本設計書_研究室統合プラットフォーム.md)
- [詳細設計書](docs/03_詳細設計/詳細設計書_研究室統合プラットフォーム.md)

起動・構築手順の詳細は **[起動手順書](docs/04_実装/起動手順書_研究室統合プラットフォーム.md)** にまとめてある。
本書には要点のみ記載する。工程ごとの成果物一覧は [docs/README.md](docs/README.md) を参照。

## 技術スタック

| 項目 | 内容 |
|---|---|
| バックエンド | Python 3.11+ / Django 5.2 |
| フロントエンド | Django テンプレート + Bootstrap 5 + htmx |
| データベース | PostgreSQL 16（ローカル開発は SQLite） |
| 配信 | nginx + gunicorn（Docker Compose） |

## クイックスタート（ローカル動作確認）

Windows / PowerShell の場合は次の1コマンドで、仮想環境の作成・依存パッケージの導入・
マイグレーション・デモデータ投入・開発サーバー起動まで一括で行える。

```powershell
.\dev-setup.ps1 -Run
```

`-Run` を付けない場合はセットアップのみ実行する。起動は次のコマンド。

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

起動後 <http://127.0.0.1:8000/> を開いてログインする。

| メールアドレス | パスワード | ロール | 備考 |
|---|---|---|---|
| `student@example.local` | `demo-pass-12345` | 学生 | デモデータの所有者 |
| `teacher@example.local` | `demo-pass-12345` | 教員 | デモ用。`/admin/` 利用可 |

自分用の管理者アカウントは `createsuperuser` で作成する（教員ロール・管理画面利用可）。

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

パスワードを忘れた場合は `changepassword` で再設定する。

```powershell
.\.venv\Scripts\python.exe manage.py changepassword <自分のメールアドレス>
```

> デモユーザーとデモデータは開発専用。`manage.py seed_demo` は `DJANGO_DEBUG=1` のときだけ動作する。
> 画面上のパスワード変更・再設定機能は未実装。変更は `/admin/` か `manage.py changepassword` で行う
> （[起動手順書 3.5](docs/04_実装/起動手順書_研究室統合プラットフォーム.md)）。

### 手順を個別に実行する場合

```powershell
python -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

```powershell
Copy-Item .env.example .env
```

`.env` を開き、ローカルでは `USE_SQLITE=1` / `DJANGO_DEBUG=1` に設定する
（PostgreSQL を立てずに SQLite で動く）。

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

```powershell
.\.venv\Scripts\python.exe manage.py seed_demo
```

デモデータを作り直したいときは `seed_demo --reset` を使う。
自分用のアカウントを作る場合は `manage.py createsuperuser`。

## テスト

```powershell
.\.venv\Scripts\python.exe manage.py test
```

## Lint / フォーマット

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

```powershell
.\.venv\Scripts\python.exe -m ruff format .
```

## 研究室サーバーへのデプロイ（Docker Compose）

ローカル開発用の `.env` とは別に、Docker 用の設定ファイルを用意する。

```bash
cp .env.example .env.docker
```

`.env.docker` で以下を必ず設定する。

- `DJANGO_SECRET_KEY`：ランダムな値に変更
- `DJANGO_DEBUG=0`
- `USE_SQLITE=0`
- `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS`：サーバーのホスト名
- `POSTGRES_PASSWORD`：推測されない値に変更

```bash
docker compose up -d --build
```

`web` コンテナ起動時に `migrate` と `collectstatic` が自動実行される。
初回のみ管理ユーザー（教員ロール）を作成する。

```bash
docker compose exec web python manage.py createsuperuser
```

以降 `http://<サーバーのホスト名>/` でアクセスできる。停止は `docker compose down`。

## 実装状況

| 優先度 | 機能 | モデル | 画面・URL |
|---|---|---|---|
| ① | 研究日記・研究スケジュール・学会準備支援 | 実装済 | 実装済 |
| ② | 在室可視化・学食メニュー・News投稿 | 実装済 | 実装済 |
| ③ | サーバー利用状況・長期利用申請 | 実装済 | 未実装（管理画面のみ） |
| ④ | 出張費申請・チケット・就活体験記・OB訪問 | 実装済 | 未実装（管理画面のみ） |

詳細設計書 2章のテーブル定義は全てモデル化・マイグレーション済み。

## ディレクトリ構成

```
docs/         工程別の成果物（要件定義・基本設計・詳細設計・起動手順書）
config/       Django プロジェクト設定（settings / urls / wsgi）
accounts/     認証・ユーザー管理（詳細設計書 2.1）
research/     優先度① 研究支援系（2.3〜2.5）+ seed_demo コマンド
community/    優先度② 情報共有系（2.2 / 2.9 / 2.10）
servers/      優先度③ サーバー系（2.6〜2.8）
office/       優先度④ 事務系（2.11〜2.13）
templates/    テンプレート（partials/ は htmx 用の部分テンプレート）
static/       独自CSS・favicon
nginx/        リバースプロキシ設定
```

## 運用上のメモ

- **設定ファイルの使い分け**：`.env` はローカル開発（`runserver`）用、`.env.docker` は
  Docker Compose 用。どちらも git 管理外。`.env.example` が雛形。
- **オフライン環境**：`templates/base.html` は Bootstrap と htmx を CDN から読み込んでいる。
  学内ネットワークが外部へ出られない場合は、両ファイルを `static/` 配下に置いて
  `{% static %}` 参照に差し替える。
- **認証**：詳細設計書 3.1 のとおりメールアドレス＋パスワードの Django 標準認証。
  将来 SSO へ移行する場合は `AUTHENTICATION_BACKENDS` の差し替えのみで済む構成にしている。
- **アカウント発行**：サインアップ画面は設けていない。管理画面から教員／開発者が発行する。
  パスワードの変更・再設定画面も未実装で、`/admin/` または `manage.py changepassword` を使う。
- **ロールと管理権限は別**：`is_superuser` は管理画面の権限、`role`（教員／学生）はアプリ内の権限。
  承認操作（優先度③④）は教員ロール限定のため、学生ロールの管理者は承認画面を使えない。
- **参照範囲**：研究日記・学会準備は本人のみ参照可。研究スケジュールは本人の予定に加えて
  担当者未設定の予定を「研究室共通」として全員に表示する。在室状況・学食メニューは全員が参照でき、
  News記事は公開済みが全員、下書きは作成者本人のみ参照できる。
- **在室状況**：手動での切り替えのみ。入退室の自動検知は導入していない。
