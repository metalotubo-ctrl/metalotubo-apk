# Como criar os 2 Secrets no GitHub

Secrets são variáveis privadas que o GitHub Actions usa sem ficarem visíveis no código.

---

## SECRET 1 — `GOOGLE_SHEET_ID` (fácil, 30 segundos)

1. Abre a tua Google Sheet no browser.
2. Olha para o URL:
   ```
   https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789/edit
                                          └──────── ID ─────────────────────┘
   ```
3. Copia apenas essa parte (entre `/d/` e `/edit`).
4. No GitHub:
   - Settings → Secrets and variables → Actions → **New repository secret**
   - **Name**: `GOOGLE_SHEET_ID`
   - **Secret**: cola o ID copiado
   - **Add secret**

---

## SECRET 2 — `GOOGLE_CREDENTIALS_B64` (2 minutos)

Precisamos de converter o `credentials.json` em texto base64.

### Se tens Windows:

1. Pressiona **Tecla Windows + R** → escreve `powershell` → Enter.
2. No PowerShell, cola o comando abaixo **a substituir o caminho pelo teu**:
   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\MetaloTubo\credentials.json")) | Set-Clipboard
   ```
   (o texto base64 é copiado AUTOMATICAMENTE para a área de transferência)
3. Volta ao GitHub:
   - Settings → Secrets and variables → Actions → **New repository secret**
   - **Name**: `GOOGLE_CREDENTIALS_B64`
   - **Secret**: **Ctrl+V** (cola o texto base64 — é muito longo, normal)
   - **Add secret**

### Se tens Mac:

1. Abre **Terminal**.
2. Cola (substitui caminho):
   ```bash
   base64 -i /Users/tu/credentials.json | pbcopy
   ```
3. Volta ao GitHub → **New repository secret**:
   - **Name**: `GOOGLE_CREDENTIALS_B64`
   - **Secret**: **Cmd+V**
   - **Add secret**

### Alternativa gráfica (qualquer SO):

1. Vai a https://www.base64encode.org/
2. Clica em **"Upload File"** → escolhe o `credentials.json`
3. Clica **"ENCODE"**
4. Copia o texto que aparece em baixo (é muito longo, normal)
5. Cola no campo **Secret** no GitHub

---

## ✅ Verificar

Depois de criar os 2, na página **Settings → Secrets** deves ver:
- 🔒 `GOOGLE_CREDENTIALS_B64`
- 🔒 `GOOGLE_SHEET_ID`

Se sim, avança para correr o workflow.
