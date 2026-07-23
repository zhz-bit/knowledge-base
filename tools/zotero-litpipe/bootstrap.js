/* litpipe · Zotero bootstrap(适配 Zotero 9)
 * 生命周期:install / startup / shutdown / uninstall
 * 真正的逻辑在 content/litpipe.js
 *
 * 防御性要点(踩过的坑):
 *  · Zotero 9 里 startup 抛异常会变成 "uncaught exception: undefined",完全看不出原因
 *    → 全程 try/catch,并同时用 Zotero.debug + Zotero.logError 打出来
 *  · Services 不保证已注入,自己 import 兜底
 */

var LitPipe;

function log(msg) {
  try { Zotero.debug("[litpipe/bootstrap] " + msg); } catch (e) { /* noop */ }
}

function logErr(where, e) {
  const m = `[litpipe/bootstrap] ${where} 失败: ${e && (e.stack || e.message || e)}`;
  try { Zotero.debug(m); } catch (_) {}
  try { Zotero.logError(new Error(m)); } catch (_) {}
}

function install() { log("installed"); }
function uninstall() { log("uninstalled"); }

async function startup({ id, version, rootURI }) {
  try {
    log("starting " + version + " @ " + rootURI);

    // Services 兜底(某些 Zotero 版本不自动注入)
    if (typeof Services === "undefined") {
      // eslint-disable-next-line no-global-assign
      globalThis.Services = ChromeUtils.importESModule(
        "resource://gre/modules/Services.sys.mjs").Services;
      log("已自行 import Services");
    }

    if (Zotero.initializationPromise) await Zotero.initializationPromise;
    log("Zotero 就绪");

    Services.scriptloader.loadSubScript(rootURI + "content/litpipe.js");
    if (typeof LitPipe === "undefined" || !LitPipe) {
      throw new Error("loadSubScript 后仍拿不到 LitPipe(作用域问题)");
    }
    log("litpipe.js 已载入");

    Zotero.LitPipe = LitPipe;      // 挂到 Zotero 上,便于在调试台手动调用
    await LitPipe.init({ id, rootURI });
    log("started ✓");
  } catch (e) {
    logErr("startup", e);
  }
}

function shutdown() {
  try {
    log("shutting down");
    if (LitPipe) LitPipe.shutdown();
  } catch (e) {
    logErr("shutdown", e);
  }
  LitPipe = undefined;
  try { delete Zotero.LitPipe; } catch (e) { /* noop */ }
}
