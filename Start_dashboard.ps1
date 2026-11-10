$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Push-Location (Join-Path $projectRoot 'dashboard')
try {
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
} finally {
    Pop-Location
}
