Como criar os 2 Secrets no GitHub
Secrets são variáveis privadas que o GitHub Actions usa sem ficarem visíveis no código.
---
SECRET 1 — `GOOGLE\_SHEET\_ID` (fácil, 30 segundos)
Abre a tua Google Sheet no browser.
Olha para o URL:
```
   https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789/edit
                                          └──────── ID ─────────────────────┘
   ```
Copia apenas essa parte (entre `/d/` e `/edit`).
No GitHub:
Settings → Secrets and variables → Actions → New repository secret
Name: `GOOGLE\_SHEET\_ID`
Secret: cola o ID copiado
Add secret
---
SECRET 2 — `GOOGLE\_CREDENTIALS\_B64` (2 minutos)
Precisamos de converter o `credentials.json` em texto base64.
Se tens Windows:
Pressiona Tecla Windows + R → escreve `powershell` → Enter.
No PowerShell, cola o comando abaixo a substituir o caminho pelo teu:
```powershell
   \[Convert]::ToBase64String(\[IO.File]::ReadAllBytes("C:\\MetaloTubo\\credentials.json")) | Set-Clipboard
   ```
(o texto base64 é copiado AUTOMATICAMENTE para a área de transferência)
Volta ao GitHub:
Settings → Secrets and variables → Actions → New repository secret
Name: `GOOGLE\_CREDENTIALS\_B64`
Secret: Ctrl+V (cola o texto base64 — é muito longo, normal)
Add secret
Se tens Mac:
Abre Terminal.
Cola (substitui caminho):
```bash
   base64 -i /Users/tu/credentials.json | pbcopy
   ```
Volta ao GitHub → New repository secret:
Name: `GOOGLE\_CREDENTIALS\_B64`
Secret: Cmd+V
Add secret
Alternativa gráfica (qualquer SO):
Vai a https://www.base64encode.org/
Clica em "Upload File" → escolhe o `credentials.json`
Clica "ENCODE"
Copia o texto que aparece em baixo (é muito longo, normal)
Cola no campo Secret no GitHub
---
✅ Verificar
Depois de criar os 2, na página Settings → Secrets deves ver:
🔒 `GOOGLE\_CREDENTIALS\_B64`
🔒 `GOOGLE\_SHEET\_ID`
Se sim, avança para correr o workflow.
