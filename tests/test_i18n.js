"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {translate, resolveLanguage} = require("../web/i18n.js");

test("language choice prefers a supported query, then saved preference, then English", () => {
  assert.equal(resolveLanguage("zh-CN", "en"), "zh-CN");
  assert.equal(resolveLanguage("unsupported", "zh-CN"), "zh-CN");
  assert.equal(resolveLanguage(null, null), "en");
});

test("static interface text and accessible labels have English translations", () => {
  const html = fs.readFileSync(path.join(__dirname, "../web/index.html"), "utf8");
  const texts = html.split(/<[^>]+>/).map(text => text.trim());
  const attributes = [...html.matchAll(/(?:title|aria-label|placeholder|alt)="([^"]+)"/g)].map(match => match[1]);
  const missing = [...texts, ...attributes].filter(text => /\p{Script=Han}/u.test(text)
    && text !== "简体中文" && translate(text, "en") === text);
  assert.deepEqual(missing, []);
});

test("dynamic scores, progress, evidence and transfer errors are localized", () => {
  for (const source of [
    "详情",
    "勾选可疑 · ≥ 35 分", "已分析 3/5 · 可疑 2 · 最高 95 · 失败 1 · 分析中",
    "分析完成 · 已处理 3 / 3 · 失败 0。结果已标在文件树上，点击「详情」查看依据。",
    "已显示 3 首曲目 · 全曲分析 · 拖动图表旋转视角", "曲目 2",
    "约 16.11 kHz 出现持续高频截止；截止特征强度 100%。",
    "100.00% 的非零样本落在 16-bit 网格上，疑似高位深补零。",
    "目标已存在，未执行任何文件操作：D:\\Review\\a.flac",
    "无法分析 a.flac：文件在分析过程中发生变化，请重试。",
    "已复制：D:\\Music\\a.flac → D:\\Review\\a.flac"
  ]) {
    assert.equal(/\p{Script=Han}/u.test(translate(source, "en")), false, source);
    assert.equal(translate(source, "zh-CN"), source);
  }
});

test("localization preserves filenames, dollar signs and numeric values", () => {
  assert.equal(translate("目标已存在，未执行任何文件操作：D:\\音楽\\test$&.flac", "en"),
    "Destination already exists; no transfers were performed: D:\\音楽\\test$&.flac");
  assert.equal(translate("  设置  ", "en"), "  Settings  ");
  assert.equal(translate("01 - Broadband.flac", "en"), "01 - Broadband.flac");
  for (const name of ["constructor", "toString", "__proto__"]) assert.equal(translate(name, "en"), name);
});

test("scope confirmation, lifecycle counts and recovery paths localize in both languages", () => {
  for (const source of [
    "取消选择", "反选", "分析进度详情", "确认并执行",
    "分析中 · 已处理 2 / 6 · 成功 1 · 失败 1 · 未启动 2",
    "停止中（等待在途请求） · 已处理 2 / 6 · 成功 1 · 失败 1 · 未启动 2",
    "操作单元 1 · 文件 6 · 目录 2 · 354744 B",
    "影响音频 3 · 文件 6 · 目录 2 · 354744 B",
    "移动完成 0 项 · 未完成 1 项。详细结果见操作弹窗。",
    "已复制，部分源残留：D:/albumA → D:/review/albumA；PermissionError: injected；恢复清单：D:/review/journal.json",
    "源残留：D:/albumA/one.flac", "目标残留：D:/review/albumA",
    "已复制，源文件未删除：D:/albumA → D:/review/albumA；PermissionError: injected；恢复清单：D:/review/journal.json",
    "范围或目标已变化，请重新预览：目标已存在或重复：D:/review/albumA"
  ]) {
    assert.equal(/\p{Script=Han}/u.test(translate(source, "en")), false, source);
    assert.equal(translate(source, "zh-CN"), source);
  }
});
