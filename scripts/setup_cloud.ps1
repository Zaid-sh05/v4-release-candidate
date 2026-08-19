$ErrorActionPreference = "Stop"
Write-Host "Qanoni V3.6 cloud setup"
Write-Host "========================"

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  Write-Host "Created .env. Fill OPENAI_API_KEY, SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY, then run this script again."
  exit 1
}

Write-Host "1/4 Uploading legal corpus to Supabase..."
python scripts\push_to_supabase.py
Write-Host "2/4 Creating missing embeddings..."
python scripts\embed_supabase.py
Write-Host "3/4 Checking integrations..."
python scripts\check_integrations.py
Write-Host "4/4 Running local QA..."
python doctor.py
Write-Host "Qanoni cloud data layer is ready."
