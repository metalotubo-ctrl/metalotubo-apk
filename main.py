"""
MetaloTubo Mobile — APK para encarregados de obra.
Comunicação via Google Apps Script webhook (sem dependências pesadas).
"""

from __future__ import annotations

import os
import json
import uuid
import time
import tempfile
import traceback
import urllib.request
import urllib.error
from datetime import datetime

import flet as ft

APP_TITLE = "MetaloTubo Mobile"
COR_PRIMARIA = "#1A237E"
COR_SECUNDARIA = "#0D47A1"
COR_OK = "#2E7D32"
COR_ERRO = "#C62828"
COR_URG = "#D32F2F"


# ---------------------------------------------------------------------
# Paths — tudo gravado em FLET_APP_STORAGE_DATA (privado da APK)
# ---------------------------------------------------------------------

def _storage_dir() -> str:
    base = os.environ.get("FLET_APP_STORAGE_DATA") or ""
    if not base or not os.path.isdir(os.path.dirname(base) or base):
        home = os.path.expanduser("~")
        if not home or home in ("/", "~") or not os.path.isdir(home):
            home = tempfile.gettempdir()
        base = os.path.join(home, ".metalotubo_mobile")
    try:
        os.makedirs(base, exist_ok=True)
    except PermissionError:
        base = os.path.join(tempfile.gettempdir(), "metalotubo_mobile")
        os.makedirs(base, exist_ok=True)
    return base


def _login_file() -> str:
    return os.path.join(_storage_dir(), "login.json")


def _assets_path(*parts) -> str:
    """Devolve caminho de assets (bundled no APK)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in [
        os.path.join(here, "assets"),
        os.path.join(os.getcwd(), "assets"),
    ]:
        p = os.path.join(base, *parts)
        if os.path.exists(p):
            return p
    return os.path.join(here, "assets", *parts)


def load_login() -> dict:
    p = _login_file()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_login(data: dict) -> None:
    try:
        with open(_login_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_login failed:", e)


def _load_bundled_webhook() -> str:
    try:
        p = _assets_path("webhook_url.txt")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------
# Cliente Apps Script
# ---------------------------------------------------------------------
class WebhookClient:
    def __init__(self):
        self.url: str = ""
        self._cache: dict = {}

    def connect(self, url: str):
        if not url or not url.startswith("https://"):
            raise RuntimeError("URL do Apps Script inválida.")
        self.url = url.rstrip("/")
        # Testa ligação
        r = self.call("ping", {}, ttl=0)
        if not r.get("ok"):
            raise RuntimeError("Resposta inesperada do webhook: " + str(r))

    def call(self, action: str, params: dict = None, ttl: int = 30):
        if not self.url:
            raise RuntimeError("Webhook não configurado.")
        payload = {"action": action}
        payload.update(params or {})

        # Cache só para leituras
        cache_key = None
        if action.startswith("get_") and ttl > 0:
            cache_key = json.dumps(payload, sort_keys=True)
            cached = self._cache.get(cache_key)
            if cached and time.time() - cached[0] < ttl:
                return cached[1]

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
            except Exception:
                raw = str(e)
            raise RuntimeError(f"HTTP {e.code}: {raw[:200]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ligação falhou: {e.reason}")

        try:
            data = json.loads(raw)
        except Exception:
            raise RuntimeError(f"Resposta inválida: {raw[:200]}")

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(data["error"])

        if cache_key:
            self._cache[cache_key] = (time.time(), data)
        return data


# ---------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------
def main(page: ft.Page):
    page.title = APP_TITLE
    page.bgcolor = "#F0F2F5"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.window_min_width = 360

    client = WebhookClient()
    state = {"user": None}

    def snack(msg: str, cor: str = "green"):
        page.snack_bar = ft.SnackBar(ft.Text(msg, color="white"), bgcolor=cor)
        page.snack_bar.open = True
        page.update()

    def top_bar(titulo: str, back=None):
        return ft.AppBar(
            leading=ft.IconButton(ft.icons.ARROW_BACK, on_click=back) if back else None,
            title=ft.Text(titulo, weight="bold"),
            bgcolor=COR_PRIMARIA, color="white",
        )

    # -------- SETUP --------
    def mostrar_setup():
        page.clean()
        login = load_login()
        default_url = login.get("webhook_url") or _load_bundled_webhook()

        tf_url = ft.TextField(
            label="URL do Apps Script",
            value=default_url,
            hint_text="https://script.google.com/macros/s/.../exec",
            multiline=True, min_lines=1, max_lines=3,
        )
        err = ft.Text("", color=COR_ERRO, size=12)

        def continuar(_=None):
            try:
                url = (tf_url.value or "").strip()
                client.connect(url)
                login["webhook_url"] = url
                save_login(login)
                snack("Ligação OK!", COR_OK)
                mostrar_login()
            except Exception as e:
                err.value = f"Falha: {e}"
                page.update()

        page.add(
            top_bar("Configuração inicial"),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("Primeira utilização", size=18, weight="bold"),
                ft.Text("Cola a URL do Apps Script partilhada pelo escritório.",
                        size=12, color="grey"),
                ft.Container(height=10),
                tf_url,
                err,
                ft.Container(height=10),
                ft.ElevatedButton("Continuar", icon=ft.icons.CHECK,
                                  on_click=continuar, bgcolor=COR_PRIMARIA,
                                  color="white", height=55),
            ], spacing=10)),
        )
        page.update()

    # -------- LOGIN --------
    def mostrar_login():
        login = load_login()
        if not login.get("webhook_url"):
            return mostrar_setup()
        if not client.url:
            try:
                client.connect(login["webhook_url"])
            except Exception as e:
                snack(f"Falha: {e}", COR_ERRO)
                return mostrar_setup()

        page.clean()
        tf_user = ft.TextField(label="Utilizador", autofocus=True)
        tf_pass = ft.TextField(label="Password", password=True,
                                can_reveal_password=True)
        err = ft.Text("", color=COR_ERRO)

        def entrar(_=None):
            nome = (tf_user.value or "").strip()
            if not nome:
                err.value = "Preenche o utilizador."
                page.update()
                return
            try:
                users = client.call("get_users", ttl=10)
            except Exception as e:
                err.value = f"Erro: {e}"
                page.update()
                return

            match = None
            for u in users:
                if str(u.get("nome") or "").strip().lower() == nome.lower():
                    match = u
                    break
            if not match:
                err.value = "Utilizador não existe."
                page.update()
                return
            if str(match.get("ativo") or "True") not in ("True", "true", "1"):
                err.value = "Utilizador desativado."
                page.update()
                return
            state["user"] = nome
            mostrar_portal()

        logo_widget = ft.Image(
            src=_assets_path("logo.png"),
            width=220, height=150, fit=ft.ImageFit.CONTAIN,
            error_content=ft.Text("METALOTUBO", size=28, weight="bold",
                                    color=COR_PRIMARIA),
        )

        page.add(
            ft.Container(padding=30, content=ft.Column([
                ft.Container(height=10),
                logo_widget,
                ft.Text("App de Obra", size=14, color="grey"),
                ft.Container(height=25),
                tf_user, tf_pass, err,
                ft.Container(height=10),
                ft.ElevatedButton("ENTRAR", icon=ft.icons.LOGIN,
                                  on_click=entrar, height=55,
                                  bgcolor=COR_PRIMARIA, color="white"),
                ft.TextButton("Reconfigurar", on_click=lambda e: mostrar_setup()),
            ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.CENTER)),
        )
        page.update()

    # -------- PORTAL --------
    def mostrar_portal():
        page.clean()
        page.add(
            top_bar(f"Olá, {state['user']}"),
            ft.Container(padding=20, content=ft.Column([
                ft.Text("O que queres fazer?", size=18, weight="bold"),
                ft.Container(height=10),
                ft.ElevatedButton("NOVO PEDIDO", icon=ft.icons.ADD_SHOPPING_CART,
                                  height=70, bgcolor=COR_SECUNDARIA, color="white",
                                  on_click=lambda e: mostrar_pedido()),
                ft.ElevatedButton("MÁQUINAS", icon=ft.icons.PRECISION_MANUFACTURING,
                                  height=70, bgcolor="#F57C00", color="white",
                                  on_click=lambda e: mostrar_maquinas()),
                ft.ElevatedButton("RECEÇÃO DE GÁS", icon=ft.icons.LOCAL_FIRE_DEPARTMENT,
                                  height=70, bgcolor="#7B1FA2", color="white",
                                  on_click=lambda e: mostrar_gas()),
                ft.ElevatedButton("HISTÓRICO", icon=ft.icons.HISTORY,
                                  height=70, bgcolor=COR_PRIMARIA, color="white",
                                  on_click=lambda e: mostrar_historico()),
                ft.Container(height=10),
                ft.OutlinedButton("Sair", icon=ft.icons.LOGOUT,
                                  on_click=lambda e: (state.update({"user": None}),
                                                       mostrar_login())),
            ], spacing=10)),
        )
        page.update()

    # -------- MÁQUINAS (consultar + confirmar localização) --------
    def mostrar_maquinas():
        page.clean()
        try:
            obras_rows = client.call("get_obras", ttl=60)
            maqs_rows = client.call("get_maquinas", ttl=30)
        except Exception as e:
            snack(f"Erro a ler dados: {e}", COR_ERRO)
            return mostrar_portal()

        obras_ativas = [str(r.get("nome")) for r in obras_rows
                         if str(r.get("estado") or "Ativa") == "Ativa"]

        state.setdefault("maq_obra_sel", obras_ativas[0] if obras_ativas else "")

        dd_obra = ft.Dropdown(
            label="Filtrar por obra (opcional)",
            value=state.get("maq_obra_sel") or None,
            options=[ft.dropdown.Option("(Todas)")]
                     + [ft.dropdown.Option(o) for o in obras_ativas],
        )

        lista_col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO)

        def confirmar(n_interno: str, maq_nome: str, obra_sel: str,
                       acao: str = "rececao", obra_destino: str = ""):
            if acao == "rececao" and not obra_sel:
                snack("Escolhe a obra primeiro.", COR_ERRO); return
            row = {
                "uuid": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "utilizador": state["user"] or "mobile",
                "n_interno": n_interno,
                "maquina": maq_nome,
                "obra": obra_destino if acao == "expedicao" else obra_sel,
                "acao": acao,
                "obra_origem": obra_sel if acao == "expedicao" else "",
                "notas": "",
                "processado": "FALSE",
            }
            try:
                client.call("post_maquina_loc", {"row": row}, ttl=0)
                if acao == "rececao":
                    snack(f"✓ {n_interno} confirmado em {obra_sel}", COR_OK)
                else:
                    snack(f"✓ {n_interno} enviado para {obra_destino}", COR_OK)
                client._cache.pop(json.dumps({"action": "get_maquinas"},
                                              sort_keys=True), None)
                mostrar_maquinas()
            except Exception as e:
                snack(f"Falha: {e}", COR_ERRO)

        def expedir_dialog(n_interno: str, maq_nome: str, obra_origem: str):
            destinos = [o for o in obras_ativas if o != obra_origem] + ["Armazém", "Oficina"]
            destinos = list(dict.fromkeys(destinos))  # unique preservando ordem
            dd_dest = ft.Dropdown(
                label="Destino", width=320,
                options=[ft.dropdown.Option(d) for d in destinos],
                value=destinos[0] if destinos else None,
            )

            def go(_=None):
                if not dd_dest.value:
                    snack("Escolhe o destino.", COR_ERRO); return
                dlg.open = False
                page.update()
                confirmar(n_interno, maq_nome, obra_origem,
                           acao="expedicao", obra_destino=dd_dest.value)

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Enviar {n_interno}"),
                content=ft.Column([
                    ft.Text(maq_nome, italic=True),
                    ft.Text(f"De: {obra_origem}", size=12, color="grey"),
                    dd_dest,
                ], tight=True, spacing=10),
                actions=[
                    ft.TextButton("Cancelar",
                                   on_click=lambda e: (setattr(dlg, "open", False),
                                                         page.update())),
                    ft.ElevatedButton("ENVIAR", on_click=go,
                                       bgcolor=COR_PRIMARIA, color="white"),
                ],
            )
            page.dialog = dlg; dlg.open = True; page.update()

        def renderizar_lista():
            lista_col.controls.clear()
            obra_sel = dd_obra.value or ""

            if obra_sel and obra_sel != "(Todas)":
                filtradas = [r for r in maqs_rows
                              if str(r.get("local") or "") == obra_sel]
                # Mostra também máquinas sem local definido (candidatas)
                sem_local = [r for r in maqs_rows
                              if not str(r.get("local") or "").strip()]
                if not filtradas and not sem_local:
                    lista_col.controls.append(
                        ft.Text(f"Sem máquinas em '{obra_sel}'.", italic=True)
                    )
                else:
                    if filtradas:
                        lista_col.controls.append(ft.Text(
                            f"Já em '{obra_sel}' ({len(filtradas)})",
                            size=13, weight="bold", color=COR_OK))
                        for r in filtradas:
                            lista_col.controls.append(_card_maq(r, obra_sel, True))
                    if sem_local:
                        lista_col.controls.append(ft.Container(height=10))
                        lista_col.controls.append(ft.Text(
                            f"Sem localização ({len(sem_local)})",
                            size=13, weight="bold", color="#F57C00"))
                        for r in sem_local:
                            lista_col.controls.append(_card_maq(r, obra_sel, False))
            else:
                lista_col.controls.append(ft.Text(
                    f"{len(maqs_rows)} máquinas totais",
                    size=13, weight="bold", color=COR_PRIMARIA))
                for r in maqs_rows:
                    lista_col.controls.append(_card_maq(r, "", False))
            page.update()

        def _card_maq(r: dict, obra_atual: str, ja_la: bool):
            n = str(r.get("n_interno") or "")
            nome = str(r.get("maquina") or "")
            estado = str(r.get("estado") or "")
            local = str(r.get("local") or "—")
            resp = str(r.get("responsavel") or "")

            col_estado = {
                "Disponível": COR_OK, "Operacional": COR_OK,
                "Em reparação": COR_URG, "Avariada": COR_URG,
                "Em uso": COR_PRIMARIA, "Ocupada": COR_PRIMARIA,
            }.get(estado, "grey")

            btn = None
            if obra_atual and obra_atual != "(Todas)":
                if ja_la:
                    # Máquina já está nesta obra → botão ENVIAR para outra
                    btn = ft.ElevatedButton(
                        "ENVIAR PARA...",
                        icon=ft.icons.LOCAL_SHIPPING,
                        bgcolor=COR_PRIMARIA,
                        color="white",
                        on_click=lambda e, ni=n, nm=nome, ob=obra_atual:
                            expedir_dialog(ni, nm, ob),
                    )
                else:
                    btn = ft.ElevatedButton(
                        "CONFIRMAR AQUI",
                        icon=ft.icons.PLACE,
                        bgcolor=COR_OK,
                        color="white",
                        on_click=lambda e, ni=n, nm=nome, ob=obra_atual:
                            confirmar(ni, nm, ob),
                    )

            header = ft.Row([
                ft.Text(n, size=14, weight="bold", color=COR_PRIMARIA),
                ft.Container(
                    bgcolor=col_estado, border_radius=10,
                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                    content=ft.Text(estado or "—", size=10, color="white",
                                     weight="bold"),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

            linha2 = ft.Text(nome, size=13)
            linha3_items = [f"📍 {local}"]
            if resp:
                linha3_items.append(f"👤 {resp}")
            linha3 = ft.Text("   ".join(linha3_items), size=11, color="grey")

            col_content = [header, linha2, linha3]
            if btn:
                col_content.append(ft.Container(height=4))
                col_content.append(btn)

            return ft.Container(
                bgcolor="white", border_radius=8, padding=12,
                content=ft.Column(col_content, spacing=4),
            )

        def on_obra_change(_=None):
            state["maq_obra_sel"] = dd_obra.value
            renderizar_lista()
        dd_obra.on_change = on_obra_change

        renderizar_lista()

        page.add(
            top_bar("Máquinas", back=lambda e: mostrar_portal()),
            ft.Container(
                padding=15,
                content=ft.Column([
                    dd_obra,
                    ft.Text(
                        "Escolhe uma obra e confirma as máquinas que estão contigo.",
                        size=11, italic=True, color="grey",
                    ),
                    ft.Divider(),
                    lista_col,
                ], scroll=ft.ScrollMode.AUTO, spacing=10, expand=True),
                expand=True,
            ),
        )
        page.update()

    # -------- NOVO PEDIDO --------
    CATEGORIAS_MATERIAL = [
        "Multicamada (mm)", "PPR (mm)", "Ferro", "Ferro roscado",
        "Latão roscado", "Soldar Ferro", "Parafusos", "Outros",
    ]

    def mostrar_pedido():
        page.clean()
        try:
            obras_rows = client.call("get_obras", ttl=60)
            cons_rows = client.call("get_consumiveis", ttl=60)
        except Exception as e:
            snack(f"Erro a ler dados: {e}", COR_ERRO)
            return mostrar_portal()

        obras_ativas = [str(r.get("nome")) for r in obras_rows
                         if str(r.get("estado") or "Ativa") == "Ativa"]
        dd_obra = ft.Dropdown(
            label="Obra", value=obras_ativas[0] if obras_ativas else None,
            options=[ft.dropdown.Option(o) for o in obras_ativas],
        )

        tipo_state = {"tipo": "Consumíveis"}

        # --- Widgets Consumíveis ---
        subs = sorted({str(r.get("subcategoria") or "")
                       for r in cons_rows if r.get("subcategoria")})
        dd_sub = ft.Dropdown(
            label="Subcategoria",
            options=[ft.dropdown.Option("(Todas)")]
                     + [ft.dropdown.Option(s) for s in subs],
            value="(Todas)",
        )
        dd_item = ft.Dropdown(label="Item", options=[])

        def _items_para_sub(sub_sel: str):
            if sub_sel in (None, "", "(Todas)"):
                rows = cons_rows
            else:
                rows = [r for r in cons_rows if str(r.get("subcategoria")) == sub_sel]
            return [ft.dropdown.Option(str(r.get("item"))) for r in rows
                     if str(r.get("item") or "").strip()]

        dd_item.options = _items_para_sub("(Todas)")

        def on_sub_change(_=None):
            dd_item.options = _items_para_sub(dd_sub.value)
            dd_item.value = None
            page.update()
        dd_sub.on_change = on_sub_change

        bloco_consumiveis = ft.Column([dd_sub, dd_item], spacing=10)

        # --- Widgets Material ---
        dd_cat = ft.Dropdown(
            label="Categoria",
            options=[ft.dropdown.Option(c) for c in CATEGORIAS_MATERIAL],
            value=CATEGORIAS_MATERIAL[0],
        )
        tf_desc_mat = ft.TextField(
            label="Descrição do material",
            hint_text='Ex: Tubo galv. 1" 6m  |  Curva 90° 3/4" MxF',
            multiline=True, min_lines=1, max_lines=3,
        )
        bloco_material = ft.Column([dd_cat, tf_desc_mat], spacing=10, visible=False)

        # --- Radio Tipo ---
        def on_tipo_change(e):
            tipo_state["tipo"] = e.control.value
            bloco_consumiveis.visible = (tipo_state["tipo"] == "Consumíveis")
            bloco_material.visible = (tipo_state["tipo"] == "Material")
            page.update()

        rg_tipo = ft.RadioGroup(
            value="Consumíveis",
            on_change=on_tipo_change,
            content=ft.Row([
                ft.Radio(value="Consumíveis", label="Consumíveis"),
                ft.Radio(value="Material", label="Material"),
            ], spacing=20),
        )

        tf_qtd = ft.TextField(label="Qtd", value="1",
                               keyboard_type=ft.KeyboardType.NUMBER)
        tf_det = ft.TextField(label="Detalhes / notas (opcional)",
                               hint_text="ex: urgente para amanhã")
        sw_urg = ft.Switch(label="URGENTE", active_color=COR_URG)

        def enviar(_=None):
            if not dd_obra.value:
                snack("Escolhe a obra.", COR_ERRO); return

            tipo = tipo_state["tipo"]
            if tipo == "Consumíveis":
                if not dd_item.value:
                    snack("Escolhe o item.", COR_ERRO); return
                item_v = dd_item.value
                subcat_v = dd_sub.value or ""
            else:  # Material
                desc = (tf_desc_mat.value or "").strip()
                if not desc:
                    snack("Escreve a descrição do material.", COR_ERRO); return
                item_v = desc
                subcat_v = dd_cat.value or ""

            qtd = (tf_qtd.value or "1").strip()
            try:
                qtd_i = int(float(qtd.replace(",", ".")))
            except Exception:
                qtd_i = 1

            row = {
                "uuid": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "utilizador": state["user"] or "mobile",
                "obra": dd_obra.value,
                "tipo": tipo,
                "subcategoria": subcat_v,
                "item": item_v,
                "detalhes": tf_det.value or "",
                "qtd": str(qtd_i),
                "urgente": "TRUE" if sw_urg.value else "FALSE",
                "notas": "",
                "processado": "FALSE",
            }
            try:
                client.call("post_pedido", {"row": row}, ttl=0)
                snack("Pedido enviado!", COR_OK)
                mostrar_portal()
            except Exception as e:
                snack(f"Falha a enviar: {e}", COR_ERRO)

        page.add(
            top_bar("Novo Pedido", back=lambda e: mostrar_portal()),
            ft.Container(padding=15, content=ft.Column([
                dd_obra,
                ft.Text("Tipo de pedido", size=12, color="grey"),
                rg_tipo,
                ft.Divider(),
                bloco_consumiveis,
                bloco_material,
                ft.Row([tf_qtd, sw_urg], spacing=10),
                tf_det,
                ft.Container(height=10),
                ft.ElevatedButton("ENVIAR PEDIDO", icon=ft.icons.SEND,
                                  on_click=enviar, height=55,
                                  bgcolor=COR_OK, color="white"),
                ft.Container(height=5),
                ft.Text(f"{len(cons_rows)} consumíveis em {len(subs)} subcategorias",
                         size=11, italic=True, color="grey"),
            ], spacing=12, scroll=ft.ScrollMode.AUTO)),
        )
        page.update()

    # -------- HISTÓRICO --------
    def mostrar_historico():
        page.clean()
        try:
            rows = client.call("get_historico",
                                {"user": state["user"] or ""}, ttl=10)
        except Exception as e:
            snack(f"Erro: {e}", COR_ERRO)
            return mostrar_portal()

        if not rows:
            body = ft.Text("Sem pedidos.", italic=True)
        else:
            body_items = []
            for r in rows:
                proc = str(r.get("processado") or "").lower() in ("true", "1")
                urg = str(r.get("urgente") or "").lower() in ("true", "1")
                ts = str(r.get("timestamp") or "")[:16]
                item = str(r.get("item") or "")
                qtd = r.get("qtd") or ""
                obra = r.get("obra") or ""
                chip_cor = COR_OK if proc else ("grey" if not urg else COR_URG)
                chip_txt = "Recebido" if proc else ("URGENTE" if urg else "Enviado")
                body_items.append(ft.Container(
                    bgcolor="white", border_radius=8, padding=12,
                    content=ft.Column([
                        ft.Row([
                            ft.Text(ts, size=11, color="grey"),
                            ft.Container(
                                bgcolor=chip_cor, border_radius=12,
                                padding=ft.padding.symmetric(horizontal=8, vertical=2),
                                content=ft.Text(chip_txt, size=10, color="white",
                                                 weight="bold"),
                            ),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(f"{item}  (x{qtd})", size=14, weight="bold"),
                        ft.Text(f"{obra}", size=12, color="grey"),
                    ], spacing=3),
                ))
            body = ft.Column(body_items, spacing=8)

        page.add(
            top_bar("Histórico", back=lambda e: mostrar_portal()),
            ft.Container(padding=15, content=body, expand=True),
        )
        page.update()


    # -------- RECEÇÃO DE GÁS --------
    TIPOS_GAS = ["Argon", "Mistura MIG", "CO2"]
    TAMANHOS_GARRAFA = ["F10 P200", "F20 P200", "F50 P200", "F20 P300", "F50 P300"]

    def mostrar_gas():
        page.clean()
        try:
            obras_rows = client.call("get_obras", ttl=60)
        except Exception as e:
            snack(f"Erro a ler obras: {e}", COR_ERRO)
            return mostrar_portal()

        obras_ativas = [str(r.get("nome")) for r in obras_rows
                         if str(r.get("estado") or "Ativa") == "Ativa"]
        dd_obra = ft.Dropdown(
            label="Obra", value=obras_ativas[0] if obras_ativas else None,
            options=[ft.dropdown.Option(o) for o in obras_ativas],
        )
        dd_gas = ft.Dropdown(
            label="Tipo de gás", value=TIPOS_GAS[0],
            options=[ft.dropdown.Option(g) for g in TIPOS_GAS],
        )
        dd_tam = ft.Dropdown(
            label="Tamanho de garrafa", value=TAMANHOS_GARRAFA[0],
            options=[ft.dropdown.Option(t) for t in TAMANHOS_GARRAFA],
        )
        tf_ent = ft.TextField(
            label="Nº garrafas CHEIAS entregues", value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        tf_dev = ft.TextField(
            label="Nº garrafas VAZIAS devolvidas", value="0",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        tf_notas = ft.TextField(label="Notas (opcional)")

        def enviar(_=None):
            if not dd_obra.value:
                snack("Escolhe a obra.", COR_ERRO); return
            try:
                n_ent = int(float((tf_ent.value or "0").replace(",", ".")))
                n_dev = int(float((tf_dev.value or "0").replace(",", ".")))
            except Exception:
                snack("Quantidades têm de ser números.", COR_ERRO); return
            if n_ent <= 0 and n_dev <= 0:
                snack("Indica pelo menos entregas OU devoluções (> 0).", COR_ERRO)
                return

            row = {
                "uuid": str(uuid.uuid4()),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "utilizador": state["user"] or "mobile",
                "obra": dd_obra.value,
                "gas_tipo": dd_gas.value,
                "garrafa_tipo": dd_tam.value,
                "n_entregues": str(n_ent),
                "n_devolvidas": str(n_dev),
                "notas": tf_notas.value or "",
                "processado": "FALSE",
            }
            try:
                client.call("post_gas_rececao", {"row": row}, ttl=0)
                snack(f"✓ Gás registado: +{n_ent} cheias / -{n_dev} vazias", COR_OK)
                mostrar_portal()
            except Exception as e:
                snack(f"Falha a enviar: {e}", COR_ERRO)

        page.add(
            top_bar("Receção de Gás", back=lambda e: mostrar_portal()),
            ft.Container(padding=15, content=ft.Column([
                dd_obra,
                dd_gas,
                dd_tam,
                ft.Divider(),
                ft.Text("Garrafas cheias entregues pelo fornecedor:",
                        size=12, color="grey"),
                tf_ent,
                ft.Text("Garrafas vazias devolvidas ao fornecedor:",
                        size=12, color="grey"),
                tf_dev,
                tf_notas,
                ft.Container(height=10),
                ft.ElevatedButton("ENVIAR REGISTO", icon=ft.icons.SEND,
                                  on_click=enviar, height=55,
                                  bgcolor="#7B1FA2", color="white"),
                ft.Container(height=5),
                ft.Text("💡 Podes registar só entregas, só devoluções, ou ambas.",
                         size=11, italic=True, color="grey"),
            ], spacing=10, scroll=ft.ScrollMode.AUTO)),
        )
        page.update()


    # -------- START --------
    try:
        mostrar_login()
    except Exception as e:
        page.add(ft.Text(f"Erro fatal: {e}", color=COR_ERRO))
        page.add(ft.Text(traceback.format_exc(), size=11))
        page.update()


if __name__ == "__main__":
    try:
        if hasattr(ft, "run"):
            ft.run(main)
        else:
            ft.app(target=main)
    except Exception as e:
        print("App crashed:", e)
        raise
