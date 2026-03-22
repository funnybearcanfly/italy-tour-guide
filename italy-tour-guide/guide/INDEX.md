# 意大利旅游解说系统 - 完整索引

## 快速导航

### 按日期浏览

| 日期 | 文件 | 城市 | 核心景点 |
|------|------|------|----------|
| Day 1 (3/28) | [day1-milan.md](days/day1-milan.md) | 米兰 | 斯福尔扎古堡、《最后的晚餐》、米兰大教堂 |
| Day 2 (3/29) | [day2-verona-venice.md](days/day2-verona-venice.md) | 维罗纳/威尼斯 | 圣马可大教堂、总督宫、歌剧 |
| Day 3 (3/30) | [day3-pisa-florence.md](days/day3-pisa-florence.md) | 比萨/佛罗伦萨 | 斜塔、老桥 |
| Day 4 (3/31) | [day4-florence-deep.md](days/day4-florence-deep.md) | 佛罗伦萨 | 百花大教堂、《大卫》、皮蒂宫 |
| Day 5 (4/1) | [day5-florence-siena.md](days/day5-florence-siena.md) | 佛罗伦萨/锡耶纳 | 乌菲兹美术馆、锡耶纳广场 |
| Day 6 (4/2) | [day6-val-dorcia.md](days/day6-val-dorcia.md) | 托斯卡纳 | 奥尔恰谷、酒庄、丝柏树 |
| Day 7 (4/3) | [day7-vatican-rome.md](days/day7-vatican-rome.md) | 罗马 | 梵蒂冈博物馆、圣彼得大教堂 |
| Day 8 (4/4) | [day8-rome-baroque.md](days/day8-rome-baroque.md) | 罗马 | 博尔盖塞美术馆、万神庙 |
| Day 9 (4/5) | [day9-rome-ancient.md](days/day9-rome-ancient.md) | 罗马 | 斗兽场、古罗马广场 |
| Day 10 (4/6) | [day10-departure.md](days/day10-departure.md) | 返程 | - |

### 按城市浏览

| 城市 | 出现天数 | 主要景点 |
|------|----------|----------|
| **米兰** | Day 1 | 斯福尔扎古堡、《最后的晚餐》、米兰大教堂、运河 |
| **维罗纳** | Day 2 (可选) | 圆形竞技场、朱丽叶故居 |
| **威尼斯** | Day 2 | 圣马可大教堂、总督宫、叹息桥、DFS观景台 |
| **比萨** | Day 3 | 斜塔、奇迹广场 |
| **佛罗伦萨** | Day 3-5 | 百花大教堂、学术美术馆、皮蒂宫、乌菲兹美术馆 |
| **锡耶纳** | Day 5 | 田野广场、公共宫、大教堂 |
| **托斯卡纳乡村** | Day 6-7 | 奥尔恰谷、酒庄、Pienza、丝柏树 |
| **罗马** | Day 7-9 | 梵蒂冈、博尔盖塞美术馆、斗兽场、古罗马广场 |

### 按艺术时期浏览

| 时期 | 年代 | 相关景点 | 代表艺术家 |
|------|------|----------|------------|
| **古罗马** | 753 BC-476 AD | 斗兽场、万神庙、古罗马广场 | - |
| **中世纪** | 5-14世纪 | 圣马可大教堂、锡耶纳 | 乔托 |
| **文艺复兴早期** | 15世纪 | 佛罗伦萨大教堂 | 布鲁内莱斯基、多纳泰罗 |
| **文艺复兴盛期** | 1490-1530 | 乌菲兹、学术美术馆 | 达·芬奇、米开朗基罗、拉斐尔 |
| **巴洛克** | 1600-1750 | 博尔盖塞、圣彼得大教堂 | 贝尔尼尼、卡拉瓦乔 |

### 按艺术家浏览

| 艺术家 | 年代 | 主要作品 | 所在地点 |
|--------|------|----------|----------|
| **达·芬奇** | 1452-1519 | 《最后的晚餐》 | 米兰 |
| **米开朗基罗** | 1475-1564 | 《大卫》、西斯廷天花板、《哀悼基督》 | 佛罗伦萨、罗马 |
| **拉斐尔** | 1483-1520 | 《雅典学院》 | 梵蒂冈 |
| **波提切利** | 1445-1510 | 《维纳斯的诞生》《春》 | 佛罗伦萨 |
| **贝尔尼尼** | 1598-1680 | 《阿波罗与达芙妮》、四河喷泉 | 罗马 |
| **卡拉瓦乔** | 1571-1610 | 各类画作 | 罗马 |
| **布鲁内莱斯基** | 1377-1446 | 百花大教堂穹顶 | 佛罗伦萨 |
| **乔托** | 1267-1337 | 斯克罗维尼礼拜堂 | 帕多瓦（不在行程中） |

---

## 数据结构说明

### 景点信息格式

每个景点包含以下YAML结构化信息：

```yaml
---
location:
  name: 景点名称
  coordinates: [纬度, 经度]
  address: 详细地址
  city: 城市
  region: 大区
practical:
  opening_hours: 开放时间
  ticket_price: 门票价格
  duration: 建议游览时长
  booking_url: 预约链接
  important: 重要提示
images:
  suggested:
    - description: 图片描述
      keywords: [搜索关键词]
      source: 建议图片来源
---
```

### 艺术品信息格式

重要艺术品包含：

```yaml
---
artwork:
  name: 作品名称
  artist: 艺术家
  date: 创作年代
  medium: 材质
  size: 尺寸
  location: 所在地
---
```

---

## 图片资源建议

### 推荐图片来源

1. **Wikipedia Commons** (https://commons.wikimedia.org/)
   - 免费、高质量
   - 大部分艺术品和建筑都有

2. **Google Arts & Culture** (https://artsandculture.google.com/)
   - 高分辨率艺术品图像
   - 博物馆虚拟参观

3. **各博物馆官网**
   - 米兰大教堂: https://www.duomomilano.it/
   - 乌菲兹美术馆: https://www.uffizi.it/
   - 梵蒂冈博物馆: https://www.museivaticani.va/
   - 博尔盖塞美术馆: https://www.galleriaborghese.beniculturali.it/

### 图片命名建议

```
[城市]_[景点]_[描述]_[摄影师/来源].jpg

示例：
milan_duomo_facade_sunset_wikipedia.jpg
florence_david_fullview_accademia.jpg
rome_colosseum_interior_aerial_unsplash.jpg
```

---

## 网页开发建议

### 简略模式

- 显示景点名称、位置、开放时间
- 1-2句话介绍
- 快速浏览

### 详细模式

- 完整历史背景
- 艺术解析
- 奇闻轶事
- 游览建议

### 语音导览模式

- 提取关键段落
- 适合现场播放
- 每个景点2-3分钟

### 交互功能

- 地图显示（使用coordinates）
- 图片画廊
- 艺术品高亮
- 艺术家/风格标签

---

## 版本信息

- **创建日期**: 2026年3月
- **行程日期**: 2026年3月28日-4月6日
- **总字数**: 约50,000字
- **涵盖景点**: 60+个
- **涵盖艺术家**: 15+位

---

*本解说系统基于权威来源编写，包括UNESCO世界遗产中心、各博物馆官网、Britannica百科全书等。*
