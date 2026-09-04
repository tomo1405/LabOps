param(
    [switch]$Run
)

# ローカル開発環境のセットアップ（PowerShell）
# 使い方: .\dev-setup.ps1        ... 環境構築 + デモデータ投入
#         .\dev-setup.ps1 -Run   ... 続けて開発サーバーも起動する

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    Write-Host "== 仮想環境を作成 =="
    python -m venv .venv
}

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

Write-Host "== 依存パッケージをインストール =="
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements-dev.txt

if (-not (Test-Path ".env")) {
    Write-Host "== .env を作成（ローカルは SQLite） =="
    Copy-Item ".env.example" ".env"
    (Get-Content ".env") -replace "^USE_SQLITE=0$", "USE_SQLITE=1" -replace "^POSTGRES_HOST=db$", "POSTGRES_HOST=127.0.0.1" |
        Set-Content ".env" -Encoding utf8
}

Write-Host "== マイグレーション =="
& $py manage.py migrate --noinput

Write-Host "== デモデータ投入 =="
& $py manage.py seed_demo

if ($Run) {
    Write-Host "== 開発サーバー起動 (http://127.0.0.1:8000/) =="
    & $py manage.py runserver
} else {
    Write-Host ""
    Write-Host "セットアップ完了。次のコマンドで起動できます:"
    Write-Host "  .\.venv\Scripts\python.exe manage.py runserver"
}
