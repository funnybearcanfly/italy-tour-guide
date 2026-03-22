# 意大利旅游解说系统

一个专为艺术与历史爱好者设计的意大利旅游解说系统，包含10天9晚的详细行程解说。

## 功能特点

- **详细解说**：每天超过1000字的详细解说，涵盖历史背景、艺术解析、建筑看点、奇闻轶事
- **艺术启蒙**：从中世纪到巴洛克，完整介绍西方艺术史演变
- **位置信息**：每个景点都有详细的位置信息和实用提示
- **响应式设计**：支持电脑、平板、手机浏览

## 技术栈

- Python 3.11
- Flask 3.1
- Markdown2
- Bootstrap 5
- Jinja2

## 项目结构

```
italy-tour-guide/
├── app.py                 # Flask主应用
├── venv/                  # Python虚拟环境
├── app/
│   ├── templates/         # HTML模板
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── day.html
│   │   ├── city.html
│   │   ├── page.html
│   │   └── about.html
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── main.js
└── guide/                 # 解说内容
    ├── README.md
    ├── INDEX.md
    ├── PRACTICAL.md
    ├── IMAGES.md
    └── days/
        ├── day1-milan.md
        ├── day2-verona-venice.md
        ├── day3-pisa-florence.md
        ├── day4-florence-deep.md
        ├── day5-florence-siena.md
        ├── day6-val-dorcia.md
        ├── day7-vatican-rome.md
        ├── day8-rome-baroque.md
        ├── day9-rome-ancient.md
        └── day10-departure.md
```

## 快速开始

### 1. 激活虚拟环境

```bash
source venv/bin/activate
```

### 2. 启动服务

```bash
python app.py
```

或使用启动脚本：

```bash
./run.sh
```

### 3. 访问网站

打开浏览器访问：http://localhost:8686

## 页面路由

| 路由 | 说明 |
|------|------|
| `/` | 首页 |
| `/day/<num>` | 第N天详情 |
| `/city/<name>` | 城市页面 |
| `/practical` | 实用信息 |
| `/about` | 关于 |
| `/api/search?q=关键词` | 搜索API |

## 内容概览

### 行程概览

| 日期 | 城市 | 主要景点 |
|------|------|----------|
| Day 1 | 米兰 | 斯福尔扎古堡、《最后的晚餐》、米兰大教堂 |
| Day 2 | 维罗纳/威尼斯 | 圣马可大教堂、总督宫、歌剧 |
| Day 3 | 比萨/佛罗伦萨 | 斜塔、老桥 |
| Day 4 | 佛罗伦萨 | 百花大教堂、《大卫》、皮蒂宫 |
| Day 5 | 佛罗伦萨/锡耶纳 | 乌菲兹美术馆、锡耶纳广场 |
| Day 6 | 托斯卡纳 | 奥尔恰谷、酒庄、丝柏树 |
| Day 7 | 梵蒂冈/罗马 | 梵蒂冈博物馆、圣彼得大教堂 |
| Day 8 | 罗马 | 博尔盖塞美术馆、万神庙 |
| Day 9 | 罗马 | 斗兽场、古罗马广场 |
| Day 10 | 返程 | - |

### 艺术家

- 达·芬奇
- 米开朗基罗
- 拉斐尔
- 波提切利
- 贝尔尼尼
- 卡拉瓦乔

### 艺术时期

- 古罗马 (753 BC - 476 AD)
- 中世纪 (5-14世纪)
- 文艺复兴 (14-16世纪)
- 巴洛克 (17-18世纪)

## 开发说明

### 添加新内容

1. 在 `guide/days/` 目录下创建新的markdown文件
2. 更新 `app.py` 中的文件名映射
3. 重启服务

### 修改样式

- 主样式：`app/static/css/style.css`
- 模板内联样式：各模板文件的 `{% block extra_css %}`

### 添加新功能

1. 在 `app.py` 中添加新路由
2. 在 `app/templates/` 中创建对应模板
3. 更新导航菜单（`base.html`）

## 注意事项

- 服务默认运行在 8686 端口
- 虚拟环境需要在使用前激活
- 解说内容基于权威来源编写，包括UNESCO世界遗产中心、各博物馆官网等

## 许可证

本项目仅供个人学习和旅行参考使用。

---

*Made with ❤️ for Art & History Lovers*
