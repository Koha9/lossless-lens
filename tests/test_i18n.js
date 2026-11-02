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
