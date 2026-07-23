/* litpipe · Zotero 7 bootstrap
 * 生命周期:install / startup / shutdown / uninstall
 * 真正的逻辑在 content/litpipe.js
 */

var LitPipe;

function log(msg) {
  Zotero.debug("[litpipe/bootstrap] " + msg);
}

function install() {
  log("installed");
}

async function startup({ id, version, rootURI }) {
  log("starting " + version);
  // 等 Zotero 完全就绪再挂钩子(否则 Collections/Items 可能还没加载好)
  await Zotero.initializationPromise;
  // litpipe.js 里 `var LitPipe = {...}` 会定义到本作用域
  Services.scriptloader.loadSubScript(rootURI + "content/litpipe.js");
  Zotero.LitPipe = LitPipe;          // 挂到 Zotero 上,便于调试台手动调用
  await LitPipe.init({ id, rootURI });
  log("started");
}

function shutdown() {
  log("shutting down");
  try {
    if (LitPipe) LitPipe.shutdown();
  } catch (e) {
    log("shutdown error: " + e);
  }
  LitPipe = undefined;
  if (Zotero) delete Zotero.LitPipe;
}

function uninstall() {
  log("uninstalled");
}
