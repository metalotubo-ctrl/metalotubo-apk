/**
 * METALOTUBO — Apps Script webhook
 */

function doGet(e) {
  return _handle(e, "GET");
}

function doPost(e) {
  return _handle(e, "POST");
}

function _handle(e, method) {
  try {
    var params;
    if (method === "POST" && e.postData && e.postData.contents) {
      params = JSON.parse(e.postData.contents);
    } else {
      params = e.parameter || {};
    }

    var action = params.action || "";
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var result;

    switch (action) {
      case "ping":
        result = { ok: true, sheet: ss.getName(), now: new Date().toISOString() };
        break;

      case "get_obras":
        result = _readTab(ss, "obras");
        break;

      case "get_consumiveis":
        result = _readTab(ss, "consumiveis");
        break;

      case "get_maquinas":
        result = _readTab(ss, "maquinas");
        break;

      case "get_users":
        result = _readTab(ss, "users");
        break;

      case "get_historico":
        var user = String(params.user || "");
        var rows = _readTab(ss, "pedidos_mobile");
        rows = rows.filter(function (r) { return String(r.utilizador || "") === user; });
        rows = rows.slice(-20).reverse();
        result = rows;
        break;

      case "post_pedido":
        result = _appendRow(ss, "pedidos_mobile", params.row || {});
        break;

      case "post_rececao":
        result = _appendRow(ss, "receptions_mobile", params.row || {});
        break;

      default:
        result = { error: "Ação desconhecida: " + action };
    }

    return ContentService
      .createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function _readTab(ss, nome) {
  var ws = ss.getSheetByName(nome);
  if (!ws) return [];
  var data = ws.getDataRange().getValues();
  if (data.length < 2) return [];
  var headers = data[0];
  var rows = [];
  for (var i = 1; i < data.length; i++) {
    var obj = {};
    for (var j = 0; j < headers.length; j++) {
      obj[headers[j]] = data[i][j];
    }
    rows.push(obj);
  }
  return rows;
}

function _appendRow(ss, nome, rowObj) {
  var ws = ss.getSheetByName(nome);
  if (!ws) {
    throw new Error("Worksheet '" + nome + "' não existe. Corre 'Enviar dados-mestre' no ERP primeiro.");
  }
  var headers = ws.getRange(1, 1, 1, ws.getLastColumn()).getValues()[0];
  var linha = headers.map(function (h) {
    var v = rowObj[h];
    return v === undefined || v === null ? "" : v;
  });
  ws.appendRow(linha);
  return { ok: true, row: rowObj };
}
