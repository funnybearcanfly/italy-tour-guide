# 意大利10天9晚深度文化解说系统

## 项目说明

本解说系统专为艺术与历史爱好者设计，涵盖米兰、威尼斯、佛罗伦萨、锡耶纳、托斯卡纳乡村、罗马六大区域。

## 文件结构

```
guide/
├── README.md           # 本文件 - 索引和说明
├── days/               # 每日行程详细解说
│   ├── day1-milan.md
│   ├── day2-verona-venice.md
│   ├── day3-pisa-florence.md
│   ├── day4-florence-deep.md
│   ├── day5-florence-siena.md
│   ├── day6-val-dorcia.md
│   ├── day7-vatican-rome.md
│   ├── day8-rome-baroque.md
│   ├── day9-rome-ancient.md
│   └── day10-departure.md
├── images/             # 图片资源（按城市分类）
│   ├── milan/
│   ├── venice/
│   ├── florence/
│   ├── tuscany/
│   └── rome/
└── assets/             # 地图、时间线等资源
```

## 数据格式说明

每个景点包含以下结构化信息，便于后续网页开发：

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
images:
  suggested:
    - description: 图片描述
      keywords: [搜索关键词]
      source: 建议图片来源
---
```

## 使用方式

1. **简略模式**: 仅显示景点名称、位置、实用信息
2. **详细模式**: 完整的历史背景、艺术解析、奇闻轶事
3. **语音导览**: 可转为TTS音频，现场播放

## 图片获取建议

- Wikipedia Commons (免费商用)
- Wikimedia Commons
- Google Arts & Culture
- 各博物馆官网媒体资源

---

*本解说系统基于权威来源（博物馆官网、Britannica、UNESCO、学术资料）编写*
