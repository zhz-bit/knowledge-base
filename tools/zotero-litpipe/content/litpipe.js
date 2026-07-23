/* litpipe · 文献元数据即时校正(Zotero 7 插件,A 部分)
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

  log(msg) { Zotero.debug("[litpipe] " + msg); },

  async init({ id, rootURI }) {
    this.id = id;
    this.rootURI = rootURI;
    // 载入内置 CCF 库
    try {
      const txt = await Zotero.File.getContentsAsync(rootURI + "content/ccf_db.json");
      this.ccf = JSON.parse(txt);
      this.log(`CCF 库载入 ${Object.keys(this.ccf).length} 条`);
    } catch (e) {
      this.log("CCF 库载入失败:" + e);
    }
    await this.refreshSurveyCollections();
    this.notifierID = Zotero.Notifier.registerObserver(this.observer, ["item", "collection"], "litpipe");
    this.log("已注册监听");
  },

  shutdown() {
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
