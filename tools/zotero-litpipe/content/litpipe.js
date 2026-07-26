/* litpipe · 文献元数据即时校正(Zotero 7/9 插件,A 部分)
 *
 * 作用:往「自动驾驶综述」树里加论文时,当场做两件确定性的事:
 *   1) 会议/期刊名规范化 —— 统一成规范全称,否则 easyScholar「期刊标签」按名字匹配不上
 *   2) 按内置官方 CCF 库(575 条)打 CCF-A/B/C 标签 —— 离线查表,不依赖在线 DBLP
 * 这两件事与 tools/litpipe/maintain.py 逻辑一致;夜里的管线仍会兜底跑一遍。
 *
 * 幂等:已经规范、已经打过标签的条目不会再改 —— 这也是防止 "保存又触发 modify" 死循环的关键。
 */

var LitPipe = {
  id: null,
  rootURI: null,
  ccf: {},
  surveyCollections: new Set(),   // 综述树下所有分类的 key
  notifierID: null,
  recently: new Set(),            // 刚被本插件改过的 itemID,短时内跳过(双保险)

  // ---- 规范会议/期刊全称 ----
  CANON: {
    CVPR: "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
    ICCV: "IEEE/CVF International Conference on Computer Vision",
    ECCV: "European Conference on Computer Vision",
    NeurIPS: "Advances in Neural Information Processing Systems",
    ICLR: "International Conference on Learning Representations",
    ICML: "International Conference on Machine Learning",
    AAAI: "Proceedings of the AAAI Conference on Artificial Intelligence",
    IJCAI: "International Joint Conference on Artificial Intelligence",
    ICRA: "IEEE International Conference on Robotics and Automation",
    IROS: "IEEE/RSJ International Conference on Intelligent Robots and Systems",
    CoRL: "Conference on Robot Learning",
    RSS: "Robotics: Science and Systems",
    WACV: "IEEE/CVF Winter Conference on Applications of Computer Vision",
    ACMMM: "ACM International Conference on Multimedia",
    TPAMI: "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    "RA-L": "IEEE Robotics and Automation Letters",
    "T-RO": "IEEE Transactions on Robotics",
    "T-ITS": "IEEE Transactions on Intelligent Transportation Systems",
    "T-IV": "IEEE Transactions on Intelligent Vehicles",
    IJCV: "International Journal of Computer Vision",
    TMLR: "Transactions on Machine Learning Research",
    Nature: "Nature",
  },
  // 顺序敏感:具体的放前面(CVPR 含 "pattern recognition",要先于泛的 computer vision)
  DETECT: [
    ["winter conference on applications", "WACV"], ["wacv", "WACV"],
    ["pattern analysis and machine intel", "TPAMI"],
    ["robotics and automation letters", "RA-L"],
    ["transactions on robotics", "T-RO"],
    ["transactions on intelligent transportation", "T-ITS"],
    ["transactions on intelligent vehicles", "T-IV"],
    ["international journal of computer vision", "IJCV"],
    ["machine learning research", "TMLR"],
    ["pattern recognition", "CVPR"], ["cvpr", "CVPR"],
    ["eccv", "ECCV"], ["european conference on computer vision", "ECCV"],
    ["international conference on computer vision", "ICCV"], ["iccv", "ICCV"],
    ["neural information processing", "NeurIPS"], ["neurips", "NeurIPS"], ["nips", "NeurIPS"],
    ["learning representations", "ICLR"], ["iclr", "ICLR"],
    ["robot learning", "CoRL"], ["corl", "CoRL"],
    ["international conference on robotics and automation", "ICRA"], ["icra", "ICRA"],
    ["intelligent robots and systems", "IROS"], ["iros", "IROS"],
    ["aaai", "AAAI"],
    ["international conference on machine learning", "ICML"],
    ["robotics: science and systems", "RSS"], ["robotics science and systems", "RSS"],
    ["multimedia", "ACMMM"], ["nature", "Nature"],
  ],
  ALIAS: { "T-ITS": "TITS", "T-RO": "TR", ACMMM: "ACM MM" },
  VENUE_FIELD: { conferencePaper: "proceedingsTitle", journalArticle: "publicationTitle" },
  SURVEY_ROOT_KEY: "I7T4VTBG",   // 「自动驾驶综述」根分类

  log(msg) {
    const line = "[litpipe] " + msg;
    try { Zotero.debug(line); } catch (e) {}
    try { dump(line + "\n"); } catch (e) {}
  },

  logErr(where, e) {
    const m = `[litpipe] ${where} 失败: ${e && (e.stack || e.message || e)}`;
    try { Zotero.debug(m); } catch (_) {}
    try { Zotero.logError(new Error(m)); } catch (_) {}
    try { dump(m + "\n"); } catch (_) {}
  },

  async init({ id, rootURI }) {
    this.id = id;
    this.rootURI = rootURI;
    // CCF 库由 bootstrap 通过 loadSubScript 载入到同一 ctx(见 ccf_data.js)
    try {
      this.ccf = (typeof LITPIPE_CCF !== "undefined" && LITPIPE_CCF) ? LITPIPE_CCF : {};
      this.log(`CCF 库载入 ${Object.keys(this.ccf).length} 条`);
    } catch (e) {
      this.logErr("载入 CCF 库", e);
    }
    try {
      await this.refreshSurveyCollections();
    } catch (e) {
      this.logErr("收集综述分类", e);
    }
    try {
      this.registerColumn();
    } catch (e) {
      this.logErr("注册开源列", e);
    }
    try {
      this.notifierID = Zotero.Notifier.registerObserver(this.observer, ["item", "collection"], "litpipe");
      this.log("已注册监听 (id=" + this.notifierID + ")");
    } catch (e) {
      this.logErr("注册监听", e);
    }
  },

  shutdown() {
    this.unregisterColumn();
    if (this.notifierID) Zotero.Notifier.unregisterObserver(this.notifierID);
    this.notifierID = null;
  },

  /** 递归收集综述树下所有分类的 key(用于判断某条目是否属于本树) */
  async refreshSurveyCollections() {
    this.surveyCollections = new Set();
    try {
      const lib = Zotero.Libraries.userLibraryID;
      const root = Zotero.Collections.getByLibraryAndKey(lib, this.SURVEY_ROOT_KEY);
      if (!root) { this.log("找不到综述根分类,插件将不处理任何条目"); return; }
      const walk = (col) => {
        this.surveyCollections.add(col.key);
        for (const child of col.getChildCollections()) walk(child);
      };
      walk(root);
      this.log(`综述树分类 ${this.surveyCollections.size} 个`);
    } catch (e) {
      this.log("收集综述分类失败:" + e);
    }
  },

  inSurvey(item) {
    try {
      for (const cid of item.getCollections()) {
        const col = Zotero.Collections.get(cid);
        if (col && this.surveyCollections.has(col.key)) return true;
      }
    } catch (e) { /* ignore */ }
    return false;
  },

  detect(venue) {
    const v = (venue || "").toLowerCase();
    if (!v) return null;
    if (v.includes("workshop")) return null;      // 工作坊不强改(通常无 CCF)
    for (const [kw, ab] of this.DETECT) if (v.includes(kw)) return ab;
    return null;
  },

  rankOf(ab) {
    if (!ab) return null;
    const key = this.ALIAS[ab] || ab;
    return (this.ccf[key] || {}).rank || null;
  },

  /** 对单个条目做校正。返回改了什么(用于日志),没改返回 null。 */
  async process(item) {
    if (!item || !item.isRegularItem || !item.isRegularItem()) return null;
    const type = Zotero.ItemTypes.getName(item.itemTypeID);
    const field = this.VENUE_FIELD[type];
    if (!field) return null;                       // 只管会议/期刊
    if (!this.inSurvey(item)) return null;         // 只管综述树内的

    const venue = item.getField(field) || "";
    const ab = this.detect(venue);
    if (!ab) return null;

    const changes = [];
    // 1) 规范会议名
    const canon = this.CANON[ab];
    if (canon && venue.trim() !== canon) {
      item.setField(field, canon);
      if (type === "conferencePaper") item.setField("conferenceName", canon);
      changes.push(`venue→${ab}`);
    }
    // 2) CCF 标签
    const rank = this.rankOf(ab);
    if (rank) {
      const want = "CCF-" + rank;
      const tags = item.getTags().map(t => t.tag);
      if (!tags.includes(want)) {
        for (const t of tags) if (/^CCF-[ABC]$/.test(t)) item.removeTag(t);
        item.addTag(want);
        changes.push(want);
      }
    }
    if (!changes.length) return null;              // 幂等:没变化就不保存(也就不会再触发 modify)

    this.recently.add(item.id);
    setTimeout(() => this.recently.delete(item.id), 5000);
    await item.saveTx();
    return changes;
  },

  // ==================== B/C 部分:工具菜单 ====================
  // B 手动触发管线(②③④步,python 端做真正的活);C 配置 S2 API Key 与仓库路径。
  // 没做偏好面板:那要 chrome.manifest + chromeHandle 注册 chrome:// URL,
  // 机械多、Zotero 9 上易踩坑;菜单 + 对话框同样能填,风险低得多。

  MENU_ID: "litpipe-tools-menu",
  PREF_REPO: "extensions.litpipe.repo",
  DEFAULT_REPO: "/Users/zhaozhihua/knowledge-base",

  repoPath() {
    try {
      const v = Zotero.Prefs.get(this.PREF_REPO, true);
      if (v) return v;
    } catch (e) {}
    return this.DEFAULT_REPO;
  },

  envPath() {
    const home = Services.dirsvc.get("Home", Components.interfaces.nsIFile).path;
    return PathUtils.join(home, ".config", "zotkit", "env");
  },

  addMenu(win) {
    try {
      const doc = win.document;
      if (doc.getElementById(this.MENU_ID)) return;      // 幂等,重复调用不叠加
      const popup = doc.getElementById("menu_ToolsPopup");
      if (!popup) { this.log("找不到工具菜单,跳过挂载"); return; }
      const menu = doc.createXULElement("menu");
      menu.id = this.MENU_ID;
      menu.setAttribute("label", "litpipe 文献管线");
      const sub = doc.createXULElement("menupopup");
      const mk = (label, fn) => {
        const mi = doc.createXULElement("menuitem");
        mi.setAttribute("label", label);
        mi.addEventListener("command", () => fn.call(this, win));
        sub.appendChild(mi);
      };
      mk("立即更新(抓引用 → 评级 → 归类 → 重建页面)", this.runPipeline);
      mk("查看上次运行日志", this.showLog);
      sub.appendChild(doc.createXULElement("menuseparator"));
      mk("打开选中条目的代码仓库", this.openRepo);
      sub.appendChild(doc.createXULElement("menuseparator"));
      mk("设置 Semantic Scholar API Key…", this.setS2Key);
      mk("设置知识库仓库路径…", this.setRepo);
      menu.appendChild(sub);
      popup.appendChild(menu);
      this.log("工具菜单已挂载");
    } catch (e) {
      this.logErr("挂载菜单", e);
    }
  },

  removeMenu(win) {
    try {
      const el = win.document.getElementById(this.MENU_ID);
      if (el) el.remove();
    } catch (e) { /* 窗口已销毁,忽略 */ }
  },

  logFile() { return PathUtils.join(this.repoPath(), "tools", "litpipe", "state", "run.log"); },

  /** B:跑管线。python 端已有文件锁,这里只负责启动 + 把进度回显到 Zotero。 */
  async runPipeline(win) {
    if (this.running) {
      this.toast(win, "litpipe", "管线正在运行中,请等它结束");
      return;
    }
    const repo = this.repoPath();
    const log = this.logFile();
    const pw = new Zotero.ProgressWindow({ closeOnClick: false });
    pw.changeHeadline("litpipe 管线");
    // 注意:ItemProgress 首参是**条目类型名**,不是图标 URL —— 传 chrome:// 路径
    // 不会报错但图标为空(它只把值塞进 data-itemType 再拼 CSS 类名)
    const line = new pw.ItemProgress("journalArticle", "正在启动…");
    pw.show();

    // 通过登录 shell 启动,才能拿到 conda 的 python 与 PATH 里的 claude
    const cmd = `cd ${JSON.stringify(repo)}/tools/litpipe && `
      + `exec python pipeline.py --apply > ${JSON.stringify(log)} 2>&1`;
    this.running = true;
    let timer = null;
    const poll = async () => {
      try {
        const txt = await IOUtils.readUTF8(log);
        const lines = txt.split("\n").filter(l => l.trim());
        if (lines.length) line.setText(lines[lines.length - 1].slice(0, 90));
      } catch (e) { /* 日志还没写出来 */ }
    };
    timer = win.setInterval(poll, 2500);

    try {
      await Zotero.Utilities.Internal.exec("/bin/bash", ["-lc", cmd]);
      await poll();
      line.setProgress(100);
      pw.addDescription("完成。菜单里「查看上次运行日志」可看全文。");
    } catch (e) {
      await poll();
      line.setError();
      pw.addDescription("失败:" + (e && (e.message || e)) + "(详见运行日志)");
      this.logErr("跑管线", e);
    } finally {
      this.running = false;
      win.clearInterval(timer);
      pw.startCloseTimer(9000);
    }
  },

  async showLog(win) {
    let txt = "";
    try {
      txt = await IOUtils.readUTF8(this.logFile());
    } catch (e) {
      txt = "还没有运行日志(先执行一次「立即更新」)。";
    }
    const tail = txt.split("\n").slice(-40).join("\n");
    Services.prompt.alert(win, "litpipe 运行日志(末 40 行)", tail);
  },

  /** C:把 key 写进 ~/.config/zotkit/env —— build_edges.py 从这里读。 */
  async setS2Key(win) {
    const file = this.envPath();
    let txt = "";
    try { txt = await IOUtils.readUTF8(file); } catch (e) { /* 还没有这个文件 */ }
    const cur = (txt.match(/^S2_API_KEY\s*=\s*(.*)$/m) || [])[1] || "";
    const val = { value: cur.trim().replace(/^["']|["']$/g, "") };
    const ok = Services.prompt.prompt(
      win, "Semantic Scholar API Key",
      "填入后抓引用从 3.2 秒/篇提速到 1.1 秒/篇。留空则清除。\n写入:" + file,
      val, null, {});
    if (!ok) return;
    const key = (val.value || "").trim();
    let out = txt.replace(/^S2_API_KEY\s*=.*$/m, "").replace(/\n{3,}/g, "\n\n");
    if (key) out = (out.trimEnd() + "\nS2_API_KEY=" + key + "\n").replace(/^\n+/, "");
    try {
      await IOUtils.writeUTF8(file, out);
      this.toast(win, "litpipe", key ? "API Key 已保存,下次抓引用自动提速" : "API Key 已清除");
    } catch (e) {
      this.logErr("写 env", e);
      Services.prompt.alert(win, "litpipe", "写入失败:" + e);
    }
  },

  async setRepo(win) {
    const val = { value: this.repoPath() };
    const ok = Services.prompt.prompt(win, "知识库仓库路径",
      "litpipe 脚本所在仓库的根目录(内含 tools/litpipe/)。", val, null, {});
    if (!ok) return;
    Zotero.Prefs.set(this.PREF_REPO, (val.value || "").trim(), true);
    this.toast(win, "litpipe", "仓库路径已保存");
  },

  toast(win, head, body) {
    const pw = new Zotero.ProgressWindow();
    pw.changeHeadline(head);
    pw.addDescription(body);
    pw.show();
    pw.startCloseTimer(4000);
  },

  // ==================== D 部分:开源列 ====================
  // 在条目列表里加一列显示代码开源状态。数据来自 detect_oss.py 写回的:
  //   · 标签 `开源` / `未见开源`
  //   · extra 里的 `Code: <url>` 行(仓库地址)
  // 这样插件不用自己联网,读的是已经核对过的结果。

  COL_KEY: "litpipeOSS",

  /** 读一个条目的开源状态 → {state, url, stars, pushed, archived}
   *  extra 里的格式:`Code: <url> | ★123 | 更新 2026-01-02 | 已归档` */
  ossOf(item) {
    try {
      if (!item || !item.isRegularItem || !item.isRegularItem()) return null;
      const tags = item.getTags().map(t => t.tag);
      const line = (/^Code:\s*(.+)$/m.exec(item.getField("extra") || "") || [])[1] || "";
      const url = (line.match(/^(\S+)/) || [])[1] || "";
      const st = line.match(/★\s*(\d+)/);
      const pu = line.match(/更新\s*([\d-]+)/);
      const base = {
        url,
        stars: st ? parseInt(st[1], 10) : null,
        pushed: pu ? pu[1] : "",
        archived: /已归档/.test(line),
      };
      if (tags.includes("开源") || url) return { ...base, state: "open" };
      if (tags.includes("开源:疑似")) return { ...base, state: "maybe" };
      if (tags.includes("未见开源")) return { ...base, state: "closed" };
      return { ...base, state: "unknown" };     // 还没查过
    } catch (e) {
      return null;
    }
  },

  /** star 数缩写:1345 → 1.3k */
  fmtStars(n) {
    if (n === null || n === undefined) return "";
    return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k"
                     : String(n);
  },

  registerColumn() {
    try {
      if (!Zotero.ItemTreeManager || !Zotero.ItemTreeManager.registerColumn) {
        this.log("此 Zotero 版本没有 ItemTreeManager,跳过开源列");
        return;
      }
      this.colKey = Zotero.ItemTreeManager.registerColumn({
        dataKey: this.COL_KEY,
        label: "代码",
        pluginID: this.id,
        enabledTreeIDs: ["main"],
        // ⚠ width 的类型定义是 **string**(minWidth 才是 number)。
        // 传数字会让校验静默失败:registerColumn **返回 false 而不抛异常**,
        // 列压根不注册,而日志还打印"已注册"。Zotero 自己的文档示例写的是
        // width: 100(数字),文档与实现不一致。
        width: "92",
        minWidth: 60,
        showInColumnPicker: true,
        // dataProvider 的返回值同时用于**排序**。列表排序是字符串比较,
        // 所以 star 数要**左补零到 7 位**,否则 "9" 会排在 "1345" 前面。
        // 顺序:开源(star 多→少) > 疑似 > 未见 > 未查
        dataProvider: (item) => {
          const o = Zotero.LitPipe.ossOf(item);
          if (!o) return "";
          if (o.state === "open") {
            const inv = 9999999 - (o.stars || 0);        // 倒序:star 越多值越小,排越前
            return "1" + String(inv).padStart(7, "0") + " " + Zotero.LitPipe.fmtStars(o.stars)
                   + (o.archived ? " 归档" : "");
          }
          return { maybe: "2 疑似", closed: "3 未见", unknown: "" }[o.state] || "";
        },
        renderCell: (index, data, column, isFirstColumn, doc) => {
          const cell = doc.createElement("span");
          cell.className = `cell ${column.className}`;
          cell.style.whiteSpace = "nowrap";
          const d = data || "";
          if (d.startsWith("1")) {                        // 开源
            const rest = d.slice(9);                      // 跳过 "1"+7位排序键+空格
            cell.textContent = rest ? `✓ ★${rest}` : "✓";
            cell.style.color = /归档/.test(rest) ? "#8b8f5a" : "#3aa76d";
          } else if (d.startsWith("2")) {
            cell.textContent = "~ 疑似"; cell.style.color = "#c9922e";
          } else if (d.startsWith("3")) {
            cell.textContent = "—"; cell.style.color = "#8b95a5";
          }
          return cell;
        },
      });
      // 必须检查返回值:校验不过时它返回 false,不抛异常
      if (!this.colKey) {
        this.logErr("注册开源列", new Error("registerColumn 返回 " + this.colKey
          + " —— 参数校验未通过,查 width 是否为 string、pluginID 是否有值"));
        return;
      }
      this.log("开源列已注册 (" + this.colKey + ")");
    } catch (e) {
      this.logErr("注册开源列", e);
    }
  },

  unregisterColumn() {
    try {
      if (this.colKey && Zotero.ItemTreeManager) {
        Zotero.ItemTreeManager.unregisterColumn(this.colKey);
        this.colKey = null;
      }
    } catch (e) { /* 关闭时忽略 */ }
  },

  /** 菜单项:选中条目 → 打开其代码仓库 */
  openRepo(win) {
    try {
      const items = win.ZoteroPane.getSelectedItems();
      const urls = items.map(i => (this.ossOf(i) || {}).url).filter(Boolean);
      if (!urls.length) {
        this.toast(win, "litpipe", "选中的条目没有记录代码仓库");
        return;
      }
      for (const u of urls.slice(0, 8)) Zotero.launchURL(u);
    } catch (e) {
      this.logErr("打开仓库", e);
    }
  },

  observer: {
    async notify(event, type, ids/*, extraData */) {
      try {
        if (type === "collection") {              // 分类增删时刷新树
          if (["add", "delete", "modify"].includes(event)) await LitPipe.refreshSurveyCollections();
          return;
        }
        if (type !== "item" || !["add", "modify"].includes(event)) return;
        for (const id of ids) {
          if (LitPipe.recently.has(id)) continue;  // 跳过自己刚改的,防循环
          const item = await Zotero.Items.getAsync(id);
          const ch = await LitPipe.process(item);
          if (ch) LitPipe.log(`${item.getField("title").slice(0, 40)} → ${ch.join(", ")}`);
        }
      } catch (e) {
        LitPipe.log("处理出错:" + e);
      }
    },
  },
};

// 挂到 Zotero,供 bootstrap 访问(不依赖裸全局)
Zotero.LitPipe = LitPipe;
