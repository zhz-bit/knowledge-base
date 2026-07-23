/* eslint-disable no-undef */
/* litpipe · Zotero bootstrap
 *
 * 严格照 Zotero 官方 Make It Red 范式(与本机可用插件 ccfinfo 写法一致):
 *   · loadSubScript 必须传第二个参数 ctx —— 否则子脚本里的 var 落到不确定作用域,
 *     后续拿不到对象且报错难查(踩过:连一行日志都看不到)
 *   · 子脚本把自己挂到 Zotero.LitPipe,bootstrap 通过 Zotero.LitPipe 访问,不依赖裸全局
 *   · 日志用 dump() 兜底,即便 Zotero.debug 不可用也能在终端看到
 */

var chromeHandle;

function log(msg) {
  const line = "[litpipe/bootstrap] " + msg;
  try { Zotero.debug(line); } catch (e) { /* noop */ }
  try { dump(line + "\n"); } catch (e) { /* noop */ }
}

function logErr(where, e) {
  const m = `[litpipe/bootstrap] ${where} 失败: ${e && (e.stack || e.message || e)}`;
  try { Zotero.debug(m); } catch (_) {}
  try { Zotero.logError(new Error(m)); } catch (_) {}
  try { dump(m + "\n"); } catch (_) {}
}

function install() {}
function uninstall() {}

async function startup({ id, version, resourceURI, rootURI }, reason) {
  try {
    await Zotero.initializationPromise;
    if (!rootURI) rootURI = resourceURI.spec;
    log("starting " + version + " @ " + rootURI);

    // 子脚本的执行上下文(关键:必须显式传给 loadSubScript)
    const ctx = { rootURI, Zotero };
    ctx._globalThis = ctx;
    Services.scriptloader.loadSubScript(rootURI + "content/litpipe.js", ctx);
    log("litpipe.js 已载入");

    if (!Zotero.LitPipe) throw new Error("子脚本未挂载 Zotero.LitPipe");
    await Zotero.LitPipe.init({ id, rootURI });
    log("started ✓");
  } catch (e) {
    logErr("startup", e);
  }
}

function shutdown({ id, version, resourceURI, rootURI }, reason) {
  try {
    if (typeof APP_SHUTDOWN !== "undefined" && reason === APP_SHUTDOWN) return;
    log("shutting down");
    if (Zotero.LitPipe) Zotero.LitPipe.shutdown();
    delete Zotero.LitPipe;
    if (chromeHandle) { chromeHandle.destruct(); chromeHandle = undefined; }
  } catch (e) {
    logErr("shutdown", e);
  }
}

function onMainWindowLoad({ window }, reason) {}
function onMainWindowUnload({ window }, reason) {}
