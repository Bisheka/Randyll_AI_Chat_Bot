# Randyll_AI_Chat_Bot

## Set up on Windows

Install dependencies in a project virtual environment so they do not conflict
with packages used by other Python projects:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

Using the virtual-environment Python directly avoids needing to activate it in
PowerShell. Do not install this project's requirements into the global Python
environment.
