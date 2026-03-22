#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
意大利旅游解说系统 - Flask应用
"""

import os
import re
import yaml
import random
from flask import Flask, render_template, jsonify, request
import markdown2

# 配置路径 - 使用绝对路径
BASE_DIR = '/root/projects/italy-tour-guide'
GUIDE_DIR = os.path.join(BASE_DIR, 'guide')
DAYS_DIR = os.path.join(GUIDE_DIR, 'days')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'app', 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'app', 'static')

# Google Maps API Key
GOOGLE_MAPS_API_KEY = 'AIzaSyAreYGzqcrCjldrwU0wiAi0s7CAjVM51L0'

app = Flask(__name__,
            template_folder=TEMPLATE_DIR,
            static_folder=STATIC_DIR)

# 测验题库 - 按天分类
QUIZ_DATABASE = {
    1: [  # 米兰
        {
            "question": "米兰大教堂的建造用了多长时间？",
            "options": ["约100年", "约300年", "约500年", "约800年"],
            "answer": 2,
            "explanation": "米兰大教堂从1386年开始建造，到1965年最后一扇大门安装完成，历时近600年（约580年）。"
        },
        {
            "question": "埃马努埃莱二世长廊的设计灵感来自哪里？",
            "options": ["罗马建筑", "巴黎拱廊", "伦敦街道", "佛罗伦萨广场"],
            "answer": 1,
            "explanation": "埃马努埃莱二世长廊的设计灵感来自巴黎的拱廊街，是19世纪欧洲商业建筑的典范。"
        },
        {
            "question": "《最后的晚餐》是谁的作品？",
            "options": ["米开朗基罗", "拉斐尔", "达芬奇", "提香"],
            "answer": 2,
            "explanation": "《最后的晚餐》是列奥纳多·达·芬奇的杰作，绘于1495-1498年，收藏在米兰圣玛利亚感恩教堂。"
        },
        {
            "question": "斯卡拉歌剧院以什么闻名于世？",
            "options": ["建筑规模最大", "世界最著名的歌剧院之一", "历史最悠久", "座位最多"],
            "answer": 1,
            "explanation": "斯卡拉歌剧院是世界最著名的歌剧院之一，许多意大利歌剧都在此首演，是歌剧艺术的圣殿。"
        },
        {
            "question": "米兰在意大利的经济地位如何？",
            "options": ["第三大城市", "经济首都", "旅游中心", "政治中心"],
            "answer": 1,
            "explanation": "米兰是意大利的经济首都，是意大利最大的经济中心和金融中心，也是时尚之都。"
        },
        {
            "question": "布雷拉美术馆主要收藏什么时期的作品？",
            "options": ["古希腊罗马", "中世纪", "文艺复兴到19世纪", "现代艺术"],
            "answer": 2,
            "explanation": "布雷拉美术馆主要收藏意大利文艺复兴到19世纪的绘画作品，包括拉斐尔、曼特尼亚等大师作品。"
        },
        {
            "question": "米兰大教堂是什么建筑风格？",
            "options": ["罗马式", "哥特式", "巴洛克式", "文艺复兴式"],
            "answer": 1,
            "explanation": "米兰大教堂是世界上最大的哥特式教堂之一，以其繁复的尖塔和雕塑装饰著称。"
        },
        {
            "question": "《最后的晚餐》采用了什么绘画技法？",
            "options": ["湿壁画", "油画", "蛋彩画", "水彩画"],
            "answer": 2,
            "explanation": "达芬奇在《最后的晚餐》中实验性地使用了蛋彩画技法在干墙面上绘制，这导致作品容易损坏。"
        },
        {
            "question": "米兰位于意大利的哪个地区？",
            "options": ["托斯卡纳", "威尼托", "伦巴第", "利古里亚"],
            "answer": 2,
            "explanation": "米兰是伦巴第大区的首府，位于意大利北部的波河平原上。"
        },
        {
            "question": "斯福尔扎城堡最初的功能是什么？",
            "options": ["教堂", "城堡和公爵府", "市政厅", "大学"],
            "answer": 1,
            "explanation": "斯福尔扎城堡最初是15世纪米兰公爵斯福尔扎家族的城堡和府邸，后来成为军事要塞。"
        }
    ],
    2: [  # 维罗纳和威尼斯
        {
            "question": "威尼斯共和国存在了多长时间？",
            "options": ["约500年", "约800年", "约1100年", "约1500年"],
            "answer": 2,
            "explanation": "威尼斯共和国从697年建立到1797年被拿破仑灭亡，存在了整整1100年，是人类历史上最长寿的共和国之一。"
        },
        {
            "question": "圣马可大教堂为什么被称为'金色大教堂'？",
            "options": ["外墙镀金", "内部金色马赛克", "金色圆顶", "金色祭坛"],
            "answer": 1,
            "explanation": "圣马可大教堂内部覆盖着约8000平方米的金色马赛克，在光线下金光闪闪，因此被称为'金色大教堂'。"
        },
        {
            "question": "叹息桥连接的是哪两座建筑？",
            "options": ["教堂和钟楼", "总督宫和监狱", "两个广场", "码头和宫殿"],
            "answer": 1,
            "explanation": "叹息桥连接总督宫（法院）和监狱，犯人走过此桥时透过窗户看最后一眼自由世界而叹息。"
        },
        {
            "question": "威尼斯的建筑基础是什么？",
            "options": ["石头地基", "混凝土桩", "木桩", "钢铁支架"],
            "answer": 2,
            "explanation": "威尼斯建筑的基础是数百万根从大陆运来的木桩，打入泻湖底直到触及硬土层，在水下缺氧环境中不腐烂。"
        },
        {
            "question": "圣马可广场的特殊之处是什么？",
            "options": ["最大的广场", "欧洲唯一被称为Piazza的广场", "最古老的广场", "海拔最低的广场"],
            "answer": 1,
            "explanation": "在威尼斯，只有圣马可广场被称为'Piazza'（广场），其他所有广场都被称为'Campo'（田野）。"
        },
        {
            "question": "朱丽叶故居的阳台是什么时候添加的？",
            "options": ["14世纪", "16世纪", "20世纪", "是原装的"],
            "answer": 2,
            "explanation": "朱丽叶故居的阳台是20世纪为了吸引游客而添加的，朱丽叶这个人物可能只是文学创作。"
        },
        {
            "question": "四匹青铜马（Quadriga）来自哪里？",
            "options": ["罗马", "希腊或君士坦丁堡", "威尼斯本地", "埃及"],
            "answer": 1,
            "explanation": "四匹青铜马原本在君士坦丁堡赛车场，1204年第四次十字军东征时被威尼斯人抢来。"
        },
        {
            "question": "维罗纳竞技场现在的主要用途是什么？",
            "options": ["博物馆", "斗牛场", "歌剧院", "体育场馆"],
            "answer": 2,
            "explanation": "维罗纳竞技场至今仍在使用，每年夏天举办大型歌剧节，是世界上仍在使用的最古老的剧场之一。"
        },
        {
            "question": "贡多拉的标准价格是多少？",
            "options": ["50欧/30分钟", "80欧/30分钟", "100欧/30分钟", "120欧/30分钟"],
            "answer": 1,
            "explanation": "贡多拉官方价格是白天80欧/30分钟，晚上100欧/30分钟，最多可坐6人分摊。"
        },
        {
            "question": "总督宫大议会厅有什么特别之处？",
            "options": ["最大的壁画", "世界最大的房间之一，无柱子", "最高的天花板", "最多的窗户"],
            "answer": 1,
            "explanation": "总督宫大议会厅（53×25米）是世界上最大的房间之一，没有一根柱子支撑！"
        }
    ],
    3: [  # 比萨和佛罗伦萨
        {
            "question": "比萨斜塔为什么会倾斜？",
            "options": ["设计如此", "地基不稳", "地震影响", "战争破坏"],
            "answer": 1,
            "explanation": "比萨斜塔因为建在松软的沙土和粘土地基上，在建造过程中就开始倾斜。"
        },
        {
            "question": "圣母百花大教堂的穹顶是谁设计的？",
            "options": ["米开朗基罗", "布鲁内莱斯基", "阿尔伯蒂", "瓦萨里"],
            "answer": 1,
            "explanation": "圣母百花大教堂的穹顶由菲利波·布鲁内莱斯基设计，是文艺复兴建筑的里程碑。"
        },
        {
            "question": "《大卫》雕像现在收藏在哪里？",
            "options": ["乌菲兹美术馆", "学院美术馆", "巴杰罗博物馆", "皮蒂宫"],
            "answer": 1,
            "explanation": "米开朗基罗的《大卫》原作收藏在佛罗伦萨学院美术馆，1504年完成。"
        },
        {
            "question": "佛罗伦萨在意大利语中叫什么？",
            "options": ["Florence", "Firenze", "Firenza", "Flora"],
            "answer": 1,
            "explanation": "佛罗伦萨在意大利语中叫Firenze，意思是'百花之城'，英语叫Florence。"
        },
        {
            "question": "美第奇家族统治佛罗伦萨大约多长时间？",
            "options": ["约100年", "约200年", "约300年", "约400年"],
            "answer": 2,
            "explanation": "美第奇家族从15世纪到18世纪统治佛罗伦萨约300年，是文艺复兴最重要的赞助者。"
        },
        {
            "question": "乌菲兹美术馆最初是什么建筑？",
            "options": ["宫殿", "办公室", "教堂", "市场"],
            "answer": 1,
            "explanation": "Uffizi在意大利语中意思是'办公室'，最初是美第奇家族的行政办公楼。"
        },
        {
            "question": "老桥（Ponte Vecchio）上的店铺原来卖什么？",
            "options": ["珠宝", "皮革", "肉类", "丝绸"],
            "answer": 2,
            "explanation": "老桥上原来主要是肉铺，1593年费迪南多一世下令改为珠宝店，以消除臭味。"
        },
        {
            "question": "比萨斜塔建造用了多长时间？",
            "options": ["约50年", "约100年", "约200年", "约300年"],
            "answer": 2,
            "explanation": "比萨斜塔从1173年开始建造，因为倾斜和战争中断，到1372年才完成，历时约200年。"
        },
        {
            "question": "《春》和《维纳斯的诞生》是谁的作品？",
            "options": ["达芬奇", "米开朗基罗", "波提切利", "拉斐尔"],
            "answer": 2,
            "explanation": "这两幅名画都是桑德罗·波提切利的作品，收藏在乌菲兹美术馆。"
        },
        {
            "question": "洗礼堂的金色大门被米开朗基罗称为什么？",
            "options": ["天堂之门", "文艺复兴之门", "黄金之门", "诸神之门"],
            "answer": 0,
            "explanation": "佛罗伦萨洗礼堂的东门由吉贝尔蒂制作，米开朗基罗赞叹其为'天堂之门'。"
        }
    ],
    4: [  # 佛罗伦萨深度
        {
            "question": "米开朗基罗广场是以谁命名的？",
            "options": ["一位教皇", "雕塑家米开朗基罗", "一位将军", "一位商人"],
            "answer": 1,
            "explanation": "米开朗基罗广场以文艺复兴大师米开朗基罗命名，广场上有他著名作品的青铜复制品。"
        },
        {
            "question": "圣十字教堂安葬了多少位意大利名人？",
            "options": ["约50位", "约150位", "约300位", "约500位"],
            "answer": 2,
            "explanation": "圣十字教堂被称为'意大利的先贤祠'，安葬了约300位意大利名人，包括米开朗基罗、伽利略等。"
        },
        {
            "question": "皮蒂宫最初是谁的住所？",
            "options": ["美第奇家族", "皮蒂家族", "教皇", "国王"],
            "answer": 1,
            "explanation": "皮蒂宫最初由皮蒂家族建造，后来被美第奇家族收购，成为他们的住所。"
        },
        {
            "question": "波波里花园是什么风格的园林？",
            "options": ["英式", "法式", "意式", "日式"],
            "answer": 2,
            "explanation": "波波里花园是典型的意式园林，以雕塑、喷泉和几何布局为特色。"
        },
        {
            "question": "但丁故居纪念的是谁？",
            "options": ["一位画家", "一位诗人", "一位建筑师", "一位政治家"],
            "answer": 1,
            "explanation": "但丁故居纪念的是意大利文学之父但丁·阿利吉耶里，他写了《神曲》。"
        },
        {
            "question": "佛罗伦萨的市花是什么？",
            "options": ["玫瑰", "百合", "鸢尾花", "向日葵"],
            "answer": 2,
            "explanation": "佛罗伦萨的市花是鸢尾花（giglio），象征百花之城，在佛罗伦萨的徽章上可以看到。"
        },
        {
            "question": "领主广场上的大卫像是原件吗？",
            "options": ["是原件", "是复制品", "是部分原件", "已经移走了"],
            "answer": 1,
            "explanation": "领主广场上的大卫像是复制品，原件于1873年移至学院美术馆保护。"
        },
        {
            "question": "佣兵凉廊的主要功能是什么？",
            "options": ["市场", "集会和典礼", "军事训练", "宗教仪式"],
            "answer": 1,
            "explanation": "佣兵凉廊（Loggia dei Lanzi）是用于公共集会和典礼的开放空间，现在展示雕塑作品。"
        },
        {
            "question": "新圣母玛利亚教堂的立面是谁设计的？",
            "options": ["布鲁内莱斯基", "阿尔伯蒂", "米开朗基罗", "瓦萨里"],
            "answer": 1,
            "explanation": "新圣母玛利亚教堂的立面由莱昂·巴蒂斯塔·阿尔伯蒂设计，是文艺复兴建筑的典范。"
        },
        {
            "question": "中央市场主要卖什么？",
            "options": ["服装", "食品", "珠宝", "艺术品"],
            "answer": 1,
            "explanation": "中央市场是佛罗伦萨的主要食品市场，一楼卖肉类和奶酪，二楼是美食广场。"
        }
    ],
    5: [  # 锡耶纳
        {
            "question": "锡耶纳田野广场的形状像什么？",
            "options": ["圆形", "正方形", "扇形", "三角形"],
            "answer": 2,
            "explanation": "锡耶纳田野广场呈独特的扇形（贝壳形），是欧洲最大的中世纪广场之一。"
        },
        {
            "question": "锡耶纳赛马节每年举办几次？",
            "options": ["1次", "2次", "3次", "4次"],
            "answer": 1,
            "explanation": "锡耶纳赛马节（Palio）每年举办两次：7月2日和8月16日，是锡耶纳最重要的传统活动。"
        },
        {
            "question": "锡耶纳大教堂的地面有什么特别之处？",
            "options": ["是纯金的", "有马赛克镶嵌画", "是大理石拼图", "有铜版画"],
            "answer": 1,
            "explanation": "锡耶纳大教堂的地面有56块大理石马赛克镶嵌画，描绘宗教和历史故事，被称为'大理石地毯'。"
        },
        {
            "question": "锡耶纳有多少个行政区（Contrada）？",
            "options": ["10个", "17个", "21个", "25个"],
            "answer": 1,
            "explanation": "锡耶纳分为17个行政区（Contrada），每个区都有自己的象征、教堂和社区认同。"
        },
        {
            "question": "锡耶纳和佛罗伦萨的历史关系如何？",
            "options": ["一直是盟友", "长期敌对", "一直和平共处", "没有交集"],
            "answer": 1,
            "explanation": "锡耶纳和佛罗伦萨长期敌对，1555年佛罗伦萨最终击败锡耶纳，使其并入托斯卡纳公国。"
        },
        {
            "question": "曼吉亚塔楼有多高？",
            "options": ["66米", "88米", "102米", "120米"],
            "answer": 2,
            "explanation": "曼吉亚塔楼高102米，是锡耶纳的标志性建筑，可以俯瞰整个田野广场。"
        },
        {
            "question": "锡耶纳的圣凯瑟琳是什么人物？",
            "options": ["女王", "圣女和神秘主义者", "画家", "建筑师"],
            "answer": 1,
            "explanation": "圣凯瑟琳是锡耶纳的守护圣人，14世纪的神秘主义者，也是教会圣师之一。"
        },
        {
            "question": "皮科洛米尼图书馆位于哪里？",
            "options": ["佛罗伦萨", "锡耶纳大教堂内", "梵蒂冈", "罗马"],
            "answer": 1,
            "explanation": "皮科洛米尼图书馆位于锡耶纳大教堂内，以精美的壁画和彩色手稿闻名。"
        },
        {
            "question": "锡耶纳大学成立于哪一年？",
            "options": ["1240年", "1340年", "1440年", "1540年"],
            "answer": 0,
            "explanation": "锡耶纳大学成立于1240年，是世界上最古老的大学之一。"
        },
        {
            "question": "田野广场上的'欢乐之泉'是什么？",
            "options": ["雕塑", "喷泉", "纪念碑", "雕塑群"],
            "answer": 1,
            "explanation": "欢乐之泉（Fonte Gaia）是田野广场上的喷泉，由雅各布·德拉·奎尔恰雕刻。"
        }
    ],
    6: [  # 托斯卡纳奥尔恰谷
        {
            "question": "奥尔恰谷以什么景观闻名？",
            "options": ["山脉", "海岸", "起伏的丘陵和丝柏树", "平原"],
            "answer": 2,
            "explanation": "奥尔恰谷以标志性的起伏丘陵、丝柏树小路和田园风光闻名，是托斯卡纳的象征。"
        },
        {
            "question": "皮恩扎被称为什么？",
            "options": ["文艺复兴理想城市", "山城", "海滨小镇", "工业城市"],
            "answer": 0,
            "explanation": "皮恩扎被称为'文艺复兴理想城市'，由教皇庇护二世按照文艺复兴城市规划重建。"
        },
        {
            "question": "蒙塔尔奇诺以什么酒闻名？",
            "options": ["Chianti", "Brunello", "Prosecco", "Barolo"],
            "answer": 1,
            "explanation": "蒙塔尔奇诺以Brunello di Montalcino葡萄酒闻名，是意大利最顶级的红酒之一。"
        },
        {
            "question": "奥尔恰谷是什么时候被列入UNESCO世界遗产的？",
            "options": ["1990年", "2000年", "2004年", "2010年"],
            "answer": 2,
            "explanation": "奥尔恰谷于2004年被列入UNESCO世界遗产名录，因其独特的文化景观。"
        },
        {
            "question": "小教堂（Cappella della Madonna di Vitaleta）位于哪里？",
            "options": ["皮恩扎", "奥尔恰谷田野中", "锡耶纳", "蒙特普尔恰诺"],
            "answer": 1,
            "explanation": "小教堂位于奥尔恰谷的田野中，是托斯卡纳最上镜的建筑之一。"
        },
        {
            "question": "蒙特普尔恰诺以什么酒闻名？",
            "options": ["Brunello", "Vino Nobile", "Chianti Classico", "Super Tuscan"],
            "answer": 1,
            "explanation": "蒙特普尔恰诺以Vino Nobile di Montepulciano葡萄酒闻名。"
        },
        {
            "question": "圣奎里科多尔恰有什么特色？",
            "options": ["大教堂", "中世纪小村和意大利花园", "温泉", "城堡"],
            "answer": 1,
            "explanation": "圣奎里科多尔恰是一个迷人的中世纪小村，有美丽的意大利花园（Horti Leonini）。"
        },
        {
            "question": "奥尔恰谷的标志性树木是什么？",
            "options": ["橄榄树", "丝柏树", "松树", "橡树"],
            "answer": 1,
            "explanation": "丝柏树（Cypress）是奥尔恰谷的标志性树木，笔直的轮廓点缀在起伏的丘陵上。"
        },
        {
            "question": "皮恩扎以什么奶酪闻名？",
            "options": ["帕尔马干酪", "皮科里诺奶酪", "马苏里拉", "戈尔贡佐拉"],
            "answer": 1,
            "explanation": "皮恩扎以皮科里诺奶酪（Pecorino）闻名，是当地的特产羊奶酪。"
        },
        {
            "question": "巴尼奥维尼奥尼以什么闻名？",
            "options": ["葡萄酒", "天然温泉", "城堡", "教堂"],
            "answer": 1,
            "explanation": "巴尼奥维尼奥尼是一个温泉小镇，自古罗马时代就以天然温泉闻名。"
        }
    ],
    7: [  # 梵蒂冈
        {
            "question": "梵蒂冈的面积有多大？",
            "options": ["0.11平方公里", "0.44平方公里", "1平方公里", "2.3平方公里"],
            "answer": 1,
            "explanation": "梵蒂冈面积仅0.44平方公里，是世界上最小的独立国家。"
        },
        {
            "question": "西斯廷教堂天顶画是谁画的？",
            "options": ["拉斐尔", "达芬奇", "米开朗基罗", "波提切利"],
            "answer": 2,
            "explanation": "西斯廷教堂的天顶画《创世纪》由米开朗基罗绘制于1508-1512年。"
        },
        {
            "question": "圣彼得大教堂的穹顶有多高？",
            "options": ["100米", "120米", "136.6米", "150米"],
            "answer": 2,
            "explanation": "圣彼得大教堂的穹顶高136.6米，是世界上最高的教堂穹顶之一。"
        },
        {
            "question": "《最后的审判》位于哪里？",
            "options": ["西斯廷教堂天顶", "西斯廷教堂祭坛墙", "圣彼得大教堂", "拉斐尔房间"],
            "answer": 1,
            "explanation": "《最后的审判》位于西斯廷教堂的祭坛墙上，是米开朗基罗晚年的杰作。"
        },
        {
            "question": "《创世纪》中上帝与亚当的手指相距多远？",
            "options": ["已经接触", "几乎接触", "约2厘米", "约5厘米"],
            "answer": 1,
            "explanation": "在《创造亚当》中，上帝与亚当的手指几乎接触但未触及，这是米开朗基罗最著名的构图。"
        },
        {
            "question": "梵蒂冈博物馆每年接待多少游客？",
            "options": ["约300万", "约500万", "约700万", "约1000万"],
            "answer": 2,
            "explanation": "梵蒂冈博物馆每年接待约600-700万游客，是世界上参观人数最多的博物馆之一。"
        },
        {
            "question": "圣彼得广场有多少根柱子？",
            "options": ["140根", "240根", "284根", "300根"],
            "answer": 2,
            "explanation": "圣彼得广场由贝尔尼尼设计，有284根多立克柱和88根方柱，形成两个巨大的半圆形柱廊。"
        },
        {
            "question": "拉斐尔房间原来是做什么用的？",
            "options": ["博物馆", "教皇公寓", "教堂", "图书馆"],
            "answer": 1,
            "explanation": "拉斐尔房间（Stanze di Raffaello）原来是教皇朱利叶斯二世的私人公寓。"
        },
        {
            "question": "《雅典学院》是谁的作品？",
            "options": ["米开朗基罗", "拉斐尔", "达芬奇", "提香"],
            "answer": 1,
            "explanation": "《雅典学院》是拉斐尔的杰作，位于梵蒂冈的签字厅，描绘古希腊哲学家聚会场景。"
        },
        {
            "question": "圣彼得大教堂是谁设计的穹顶？",
            "options": ["贝尔尼尼", "米开朗基罗", "布拉曼特", "马代尔诺"],
            "answer": 1,
            "explanation": "圣彼得大教堂的穹顶主要由米开朗基罗设计，他接手了布拉曼特的工程并改进了设计。"
        }
    ],
    8: [  # 罗马巴洛克
        {
            "question": "特雷维喷泉有多高？",
            "options": ["16.9米", "26.3米", "35米", "42米"],
            "answer": 1,
            "explanation": "特雷维喷泉高26.3米，宽49.15米，是罗马最大的巴洛克喷泉。"
        },
        {
            "question": "向特雷维喷泉投硬币的传统意味着什么？",
            "options": ["发财", "重返罗马", "找到真爱", "健康长寿"],
            "answer": 1,
            "explanation": "传说背对喷泉，用右手从左肩后方投掷硬币，意味着你将重返罗马。"
        },
        {
            "question": "西班牙台阶有多少级？",
            "options": ["105级", "125级", "135级", "145级"],
            "answer": 2,
            "explanation": "西班牙台阶共有135级，是欧洲最宽的阶梯，连接西班牙广场和山上天主圣三教堂。"
        },
        {
            "question": "万神殿的穹顶有什么特别之处？",
            "options": ["是金色的", "有一个圆孔（眼）", "是透明的", "可以打开"],
            "answer": 1,
            "explanation": "万神殿穹顶中央有一个直径8.9米的圆孔（oculus），是建筑物唯一的自然光源。"
        },
        {
            "question": "纳沃纳广场原本是什么？",
            "options": ["市场", "体育场", "花园", "墓地"],
            "answer": 1,
            "explanation": "纳沃纳广场原本是古罗马图密善竞技场，后来改建成巴洛克风格的广场。"
        },
        {
            "question": "《圣特雷莎的狂喜》是谁的作品？",
            "options": ["米开朗基罗", "贝尔尼尼", "卡拉瓦乔", "拉斐尔"],
            "answer": 1,
            "explanation": "《圣特雷莎的狂喜》是吉安·洛伦佐·贝尔尼尼的雕塑杰作，位于胜利之后圣母堂。"
        },
        {
            "question": "真理之口是什么？",
            "options": ["泉眼", "井盖", "古代石雕", "雕塑"],
            "answer": 2,
            "explanation": "真理之口是一个古代的石雕井盖，传说说谎者把手伸进去会被咬住。"
        },
        {
            "question": "博尔盖塞美术馆主要收藏什么时期的作品？",
            "options": ["中世纪", "文艺复兴和巴洛克", "现代艺术", "当代艺术"],
            "answer": 1,
            "explanation": "博尔盖塞美术馆主要收藏文艺复兴和巴洛克时期的作品，包括贝尔尼尼和卡拉瓦乔的杰作。"
        },
        {
            "question": "四河喷泉代表哪四条河？",
            "options": ["尼罗河、多瑙河、恒河、拉普拉塔河", "长江、黄河、尼罗河、亚马逊河", "泰晤士河、塞纳河、莱茵河、波河", "恒河、幼发拉底河、尼罗河、多瑙河"],
            "answer": 0,
            "explanation": "四河喷泉代表当时已知的四大洲的主要河流：尼罗河（非洲）、多瑙河（欧洲）、恒河（亚洲）、拉普拉塔河（美洲）。"
        },
        {
            "question": "《大卫》雕塑（博尔盖塞版本）是谁的作品？",
            "options": ["米开朗基罗", "贝尔尼尼", "多纳泰罗", "韦罗基奥"],
            "answer": 1,
            "explanation": "博尔盖塞美术馆的《大卫》是贝尔尼尼的作品，捕捉了大卫投掷石头的动态瞬间。"
        }
    ],
    9: [  # 罗马古迹
        {
            "question": "罗马斗兽场能容纳多少观众？",
            "options": ["约3万人", "约5万人", "约8万人", "约10万人"],
            "answer": 2,
            "explanation": "罗马斗兽场能容纳约5-8万观众，是古罗马最大的圆形竞技场。"
        },
        {
            "question": "罗马斗兽场建造用了多长时间？",
            "options": ["约5年", "约10年", "约20年", "约30年"],
            "answer": 1,
            "explanation": "罗马斗兽场从公元72年开始建造，约公元80年完成，仅用了约10年时间。"
        },
        {
            "question": "古罗马广场的主要功能是什么？",
            "options": ["居住区", "政治、商业和宗教中心", "军事训练场", "皇家花园"],
            "answer": 1,
            "explanation": "古罗马广场（Forum Romanum）是古罗马的政治、商业和宗教中心，是城市的核心。"
        },
        {
            "question": "帕拉蒂尼山与什么传说有关？",
            "options": ["凯撒的住所", "罗马建城传说", "角斗士训练", "神庙遗址"],
            "answer": 1,
            "explanation": "帕拉蒂尼山是传说中罗慕路斯建立罗马的地方，也是后来皇帝宫殿的所在地。"
        },
        {
            "question": "卡拉卡拉浴场有什么特别之处？",
            "options": ["是最大的浴场", "保存最完好", "是最古老的", "是最小的"],
            "answer": 0,
            "explanation": "卡拉卡拉浴场是古罗马最大的浴场之一，可同时容纳1600人沐浴。"
        },
        {
            "question": "图拉真柱有多高？",
            "options": ["约20米", "约30米", "约40米", "约50米"],
            "answer": 2,
            "explanation": "图拉真柱高约40米（包括底座），柱身螺旋浮雕描绘图拉真皇帝征服达契亚的战争。"
        },
        {
            "question": "万神殿是谁下令建造的？",
            "options": ["凯撒", "奥古斯都", "哈德良", "图拉真"],
            "answer": 2,
            "explanation": "现在的万神殿主要由哈德良皇帝于公元118-128年重建，保留了阿格里帕神庙的门廊。"
        },
        {
            "question": "圣天使堡最初是什么建筑？",
            "options": ["教堂", "皇帝陵墓", "军事要塞", "宫殿"],
            "answer": 1,
            "explanation": "圣天使堡最初是哈德良皇帝的陵墓，后来改建成要塞、监狱，现在是博物馆。"
        },
        {
            "question": "罗马斗兽场的地下有什么？",
            "options": ["地下河", "角斗士和动物等候区", "皇帝密室", "宝藏"],
            "answer": 1,
            "explanation": "斗兽场地下有复杂的通道和房间，是角斗士等候和动物关押的地方，还有升降装置。"
        },
        {
            "question": "威尼斯广场的维托里亚诺纪念什么？",
            "options": ["罗马建城", "意大利统一", "一战胜利", "教皇加冕"],
            "answer": 1,
            "explanation": "维托里亚诺（祖国祭坛）纪念意大利统一和维托里奥·埃马努埃莱二世国王。"
        }
    ],
    10: [  # 返程
        {
            "question": "意大利的官方货币是什么？",
            "options": ["里拉", "欧元", "法郎", "马克"],
            "answer": 1,
            "explanation": "意大利从2002年开始使用欧元，取代了原来的意大利里拉。"
        },
        {
            "question": "意大利的国土形状像什么？",
            "options": ["一只手", "一只靴子", "一条腿", "一颗心"],
            "answer": 1,
            "explanation": "意大利的国土形状像一只靴子，西西里岛像是靴尖上的足球。"
        },
        {
            "question": "意大利有多少个UNESCO世界遗产？",
            "options": ["约30个", "约40个", "约60个", "约80个"],
            "answer": 2,
            "explanation": "意大利拥有约60个UNESCO世界遗产，是世界上世界遗产最多的国家之一（与中国并列）。"
        },
        {
            "question": "意大利的国花是什么？",
            "options": ["玫瑰", "百合", "雏菊", "向日葵"],
            "answer": 2,
            "explanation": "意大利的国花是雏菊（margherita），象征纯洁和爱情。"
        },
        {
            "question": "意大利的咖啡文化中，卡布奇诺通常什么时候喝？",
            "options": ["任何时间", "只在早晨", "只在下午", "只在晚上"],
            "answer": 1,
            "explanation": "在意大利，卡布奇诺通常只在早晨饮用，意大利人认为饭后喝加奶的咖啡会影响消化。"
        },
        {
            "question": "意大利语中'Grazie'是什么意思？",
            "options": ["你好", "再见", "谢谢", "对不起"],
            "answer": 2,
            "explanation": "'Grazie'在意大利语中是'谢谢'的意思，是最常用的礼貌用语之一。"
        },
        {
            "question": "意大利最长的河流是哪条？",
            "options": ["台伯河", "波河", "阿诺河", "皮亚韦河"],
            "answer": 1,
            "explanation": "波河（Po River）是意大利最长的河流，全长约652公里，流经波河平原。"
        },
        {
            "question": "意大利最大的湖泊是哪个？",
            "options": ["科莫湖", "加尔达湖", "马焦雷湖", "特拉西梅诺湖"],
            "answer": 1,
            "explanation": "加尔达湖（Lake Garda）是意大利最大的湖泊，面积约370平方公里。"
        },
        {
            "question": "意大利人口最多的城市是哪个？",
            "options": ["米兰", "那不勒斯", "罗马", "都灵"],
            "answer": 2,
            "explanation": "罗马是意大利人口最多的城市，也是首都，人口约280万。"
        },
        {
            "question": "意大利最著名的冰淇淋叫什么？",
            "options": ["Ice cream", "Gelato", "Sorbetto", "Semifreddo"],
            "answer": 1,
            "explanation": "意大利冰淇淋叫做Gelato，与普通冰淇淋相比，脂肪含量更低，口感更绵密。"
        }
    ]
}

def parse_frontmatter(content):
    """解析YAML前置数据"""
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                return frontmatter, body
            except:
                pass
    return {}, content

def extract_yaml_blocks(content):
    """提取内容中的YAML块（位置信息等）"""
    blocks = []
    # 匹配 ```yaml ... ``` 块
    pattern = r'```yaml\s*\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL)
    for match in matches:
        try:
            # 去掉YAML文档分隔符（---）
            clean_match = match.strip()
            if clean_match.startswith('---'):
                clean_match = clean_match[3:].strip()
            if clean_match.endswith('---'):
                clean_match = clean_match[:-3].strip()

            data = yaml.safe_load(clean_match)
            if data:
                blocks.append(data)
        except Exception as e:
            print(f"YAML parse error: {e}")
            pass
    return blocks

def get_day_info(filename):
    """获取某一天的概要信息"""
    filepath = os.path.join(DAYS_DIR, filename)
    if not os.path.exists(filepath):
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    # 提取标题（第一个#标题）
    title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    title = title_match.group(1) if title_match else filename

    # 提取日期
    date_match = re.search(r'\*\*日期\*\*:\s*(.+)', body)
    date = date_match.group(1).strip() if date_match else ''

    # 提取城市
    city_match = re.search(r'\*\*住宿\*\*:\s*(.+)', body)
    city = city_match.group(1).strip() if city_match else ''

    # 提取行程表
    schedule_match = re.search(r'\| 时间 \| 地点 \|.+?\n((?:\|.+\n)+)', body, re.DOTALL)
    schedule = []
    if schedule_match:
        lines = schedule_match.group(1).strip().split('\n')
        for line in lines:
            if '---' not in line:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 3:
                    schedule.append({
                        'time': parts[0],
                        'location': parts[1],
                        'activity': parts[2]
                    })

    # 提取YAML位置信息块
    locations = extract_yaml_blocks(body)

    return {
        'filename': filename,
        'title': title,
        'date': date,
        'city': city,
        'schedule': schedule,
        'locations': locations,
        'has_content': bool(body)
    }

def get_all_days():
    """获取所有天数的信息"""
    days = []
    for i in range(1, 11):
        filename = f'day{i}.md' if i < 10 else f'day{i}-departure.md'

        # 实际文件名
        actual_names = [
            f'day{i}-milan.md',
            f'day{i}-verona-venice.md',
            f'day{i}-pisa-florence.md',
            f'day{i}-florence-deep.md',
            f'day{i}-florence-siena.md',
            f'day{i}-val-dorcia.md',
            f'day{i}-vatican-rome.md',
            f'day{i}-rome-baroque.md',
            f'day{i}-rome-ancient.md',
            f'day{i}-departure.md'
        ]

        for name in actual_names:
            info = get_day_info(name)
            if info:
                days.append(info)
                break

    return days

def render_markdown(content):
    """渲染Markdown为HTML，并添加图片支持"""

    # 处理YAML块，提取图片信息并转换为图片卡片
    def replace_yaml_with_image(match):
        yaml_content = match.group(1)
        try:
            data = yaml.safe_load(yaml_content)
            if data and 'images' in data and 'suggested' in data['images']:
                # 获取景点名称
                location_name = data.get('location', {}).get('name', '景点')
                images = data['images']['suggested'][:2]  # 最多显示2张图片

                html = '<div class="attraction-images">\n'
                if len(images) == 1:
                    img = images[0]
                    # 使用Unsplash的占位图
                    search_terms = '+'.join(img.get('keywords', ['italy', 'travel']))
                    html += f'''
                    <div class="attraction-image">
                        <img src="https://source.unsplash.com/800x400/?{search_terms}" alt="{img.get('description', location_name)}" loading="lazy">
                        <div class="caption">
                            <h4>{location_name}</h4>
                            <p>{img.get('description', '')}</p>
                        </div>
                    </div>
                    '''
                else:
                    html += '<div class="image-grid">\n'
                    for img in images:
                        search_terms = '+'.join(img.get('keywords', ['italy', 'travel']))
                        html += f'''
                        <img src="https://source.unsplash.com/400x300/?{search_terms}" alt="{img.get('description', '')}" loading="lazy" title="{img.get('description', '')}">
                        '''
                    html += '</div>\n'
                html += '</div>'
                return html
        except:
            pass
        return ''  # 如果解析失败，隐藏YAML块

    content = re.sub(r'```yaml\s*\n(.*?)\n```', replace_yaml_with_image, content, flags=re.DOTALL)

    # 使用markdown2渲染
    html = markdown2.markdown(content, extras={
        'fenced-code-blocks': True,
        'tables': True,
        'header-ids': True,
        'strike': True,
        'task_list': True
    })

    return html

# 上下文处理器 - 自动提供变量给所有模板
@app.context_processor
def inject_all_days():
    return dict(all_days=get_all_days())

# 路由

@app.route('/')
def index():
    """首页"""
    days = get_all_days()
    return render_template('index.html', days=days, all_days=days)

@app.route('/day/<int:day_num>')
def day_detail(day_num):
    """某一天的详细内容"""
    # 文件名映射
    filename_map = {
        1: 'day1-milan.md',
        2: 'day2-verona-venice.md',
        3: 'day3-pisa-florence.md',
        4: 'day4-florence-deep.md',
        5: 'day5-florence-siena.md',
        6: 'day6-val-dorcia.md',
        7: 'day7-vatican-rome.md',
        8: 'day8-rome-baroque.md',
        9: 'day9-rome-ancient.md',
        10: 'day10-departure.md'
    }

    filename = filename_map.get(day_num)
    if not filename:
        return "Day not found", 404

    filepath = os.path.join(DAYS_DIR, filename)
    if not os.path.exists(filepath):
        return "File not found", 404

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)
    html_content = render_markdown(body)
    locations = extract_yaml_blocks(content)

    # 获取所有天数用于导航
    all_days = get_all_days()

    # 提取标题
    title_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    title = title_match.group(1) if title_match else f'Day {day_num}'

    return render_template('day.html',
                         day_num=day_num,
                         title=title,
                         content=html_content,
                         locations=locations,
                         all_days=all_days)

@app.route('/city/<city_name>')
def city_detail(city_name):
    """城市页面"""
    city_map = {
        'milan': {'name': '米兰', 'days': [1]},
        'venice': {'name': '威尼斯', 'days': [2]},
        'verona': {'name': '维罗纳', 'days': [2]},
        'pisa': {'name': '比萨', 'days': [3]},
        'florence': {'name': '佛罗伦萨', 'days': [3, 4, 5]},
        'siena': {'name': '锡耶纳', 'days': [5]},
        'tuscany': {'name': '托斯卡纳', 'days': [6]},
        'rome': {'name': '罗马', 'days': [7, 8, 9]},
        'vatican': {'name': '梵蒂冈', 'days': [7]}
    }

    city_info = city_map.get(city_name.lower())
    if not city_info:
        return "City not found", 404

    all_days = get_all_days()
    city_days = [all_days[d-1] for d in city_info['days'] if d <= len(all_days)]

    return render_template('city.html',
                         city_name=city_info['name'],
                         city_key=city_name.lower(),
                         days=city_days,
                         all_days=all_days)

@app.route('/api/search')
def search():
    """搜索API"""
    query = request.args.get('q', '').lower()
    if not query:
        return jsonify([])

    results = []
    for filename in os.listdir(DAYS_DIR):
        if filename.endswith('.md'):
            filepath = os.path.join(DAYS_DIR, filename)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().lower()

            if query in content:
                info = get_day_info(filename)
                if info:
                    results.append({
                        'title': info['title'],
                        'filename': info['filename'],
                        'day_num': int(filename.replace('day', '').split('-')[0])
                    })

    return jsonify(results)

@app.route('/practical')
def practical():
    """实用信息页面"""
    filepath = os.path.join(GUIDE_DIR, 'PRACTICAL.md')
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        html_content = render_markdown(content)
    else:
        html_content = "<p>内容加载中...</p>"

    all_days = get_all_days()
    return render_template('page.html',
                         title='实用信息',
                         content=html_content,
                         all_days=all_days)

@app.route('/about')
def about():
    """关于页面"""
    all_days = get_all_days()
    return render_template('about.html', all_days=all_days)

@app.route('/api/quiz/<int:day_num>')
def get_quiz(day_num):
    """获取指定天的测验题目（随机10题）"""
    if day_num not in QUIZ_DATABASE:
        return jsonify({"error": "No quiz available for this day"}), 404

    questions = QUIZ_DATABASE[day_num]
    # 随机选择10题（如果有的话）
    selected = random.sample(questions, min(10, len(questions)))

    # 返回完整的题目数据用于答案校验
    quiz_data = []
    for i, q in enumerate(selected):
        quiz_data.append({
            "id": i,
            "question": q["question"],
            "options": q["options"],
            "answer": q["answer"],
            "explanation": q["explanation"]
        })

    return jsonify({
        "day_num": day_num,
        "total_questions": len(quiz_data),
        "questions": quiz_data
    })

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8686, use_reloader=False)
