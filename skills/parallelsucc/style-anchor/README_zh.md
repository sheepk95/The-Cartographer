# Style Anchor

<p align="center"><a href="./README.md">English</a> | <a href="./README_zh.md">中文</a></p>

一个用于保持批量生成内容风格一致性的 Codex skill，适用于图片和文本两类生成任务。

![Style Anchor 动态预览](./media/style-anchor-intro.gif)

<p align="center"><sub>动态预览利用 <a href="https://github.com/alchaincyf/huashu-design">huashu-design</a> skill 生成</sub></p>

它特别适合“整批结果必须像同一个家族”的场景，例如：

- 一系列贴图、材质、纹理
- 一系列图标、精灵、插画
- 一系列诗词、歌词、标语、命名
- 一套可复用的风格锁定提示词工作流

## 它解决什么问题

`Style Anchor` 不是靠不断堆叠风格形容词来维持一致性，而是采用一套更稳定的工作流：

1. 先定义 `style contract`
2. 区分固定不变项和允许变化项
3. 按小批次生成
4. 每批做一次风格漂移检查
5. 只修复跑偏项

这样更适合大量生成时的风格控制。

## 仓库内容

- [SKILL.md](./SKILL.md)：主技能定义文件
- [references/style-contract.md](./references/style-contract.md)：风格契约模板
- [references/media-recipes.md](./references/media-recipes.md)：图片与文本生成配方
- [references/texture-imagegen.md](./references/texture-imagegen.md)：面向 `imagegen` 的贴图子模板
- [agents/openai.yaml](./agents/openai.yaml)：Codex 界面元数据

## 适合的使用场景

- 批量生成一组风格统一的贴图
- 连续写多首语气一致的诗词
- 制作具有可控变化的素材组
- 从少量参考图或参考文本中抽取稳定风格，并扩展成更大批次

## 贴图工作流

仓库内置了一个更适合 `imagegen` 的贴图子模板。

它尤其适合以下需求：

- 无缝或近似无缝贴图批量生成
- 保持统一的光照、视距和材质完成度
- 只在磨损、纹理方向、裂纹、污渍、压纹等维度上做受控变化
- 用一个稳定的母提示词驱动整组贴图

## 示例调用

```text
Use $style-anchor to create 12 hand-painted stone wall textures with one consistent style.
```

```text
Use $style-anchor to write 8 short winter poems in one restrained, melancholic voice.
```

```text
Use $style-anchor to build a reusable prompt package for a cohesive icon family.
```

## 仓库说明

- `SKILL.md` 是实际运行时使用的主文件。
- `SKILL_zh.md` 是本地维护用中文说明，已被忽略，不会进入 Git 跟踪。
- `README_zh.md` 是面向 GitHub 展示的中文仓库说明。

## License

本项目采用 [MIT License](./LICENSE)，允许免费使用、修改、分发和商用。
