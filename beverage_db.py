"""Tea beverage database for EmoTender (Heytea-based DIY system)."""

# ===== TEA CATEGORIES =====
CATEGORIES = {
    "鲜果茶": "Fresh fruit tea",
    "茶特调": "Tea special",
    "牛乳茶": "Milk tea",
    "0咖啡因": "Caffeine-free",
    "苦巧": "Chocolate special",
}

# ===== TEA BASES =====
TEA_BASES = {
    "绿妍": {"茶感": 40, "清爽度": 70, "caffeine": True, "category": ["鲜果茶", "茶特调"]},
    "茉莉绿茶": {"茶感": 45, "清爽度": 75, "caffeine": True, "category": ["鲜果茶", "茶特调"]},
    "四季春": {"茶感": 50, "清爽度": 60, "caffeine": True, "category": ["牛乳茶", "茶特调"]},
    "嫣红": {"茶感": 55, "清爽度": 45, "caffeine": True, "category": ["牛乳茶"]},
    "鸭屎香": {"茶感": 70, "清爽度": 50, "caffeine": True, "category": ["茶特调"]},
    "花香奇兰": {"茶感": 65, "清爽度": 55, "caffeine": True, "category": ["茶特调"]},
    "碎银子普洱": {"茶感": 80, "清爽度": 35, "caffeine": True, "category": ["牛乳茶", "苦巧"]},
    "大红袍": {"茶感": 75, "清爽度": 30, "caffeine": True, "category": ["牛乳茶", "苦巧"]},
    "无茶底": {"茶感": 5, "清爽度": 50, "caffeine": False, "category": ["0咖啡因", "牛乳茶"]},
}

# ===== FRUIT/JUICE =====
FRUIT_OPTIONS = {
    "草莓": {"果香": 70, "甜度": 60, "color": "粉色", "category": "鲜果茶"},
    "桃": {"果香": 65, "甜度": 55, "color": "蜜桃色", "category": "鲜果茶"},
    "青提": {"果香": 55, "甜度": 50, "color": "淡绿色", "category": "鲜果茶"},
    "葡萄汁": {"果香": 75, "清爽度": 65, "color": "紫色", "category": ["鲜果茶", "茶特调"]},
    "芭乐汁": {"果香": 80, "甜度": 50, "color": "粉色", "category": ["鲜果茶", "茶特调"]},
    "芒果汁": {"果香": 85, "甜度": 70, "color": "芒果色", "category": ["鲜果茶", "茶特调"]},
}

# ===== DAIRY/BASE =====
DAIRY_OPTIONS = {
    "牛乳": {"奶香": 80, "口感层次": 40, "dairy": True},
    "厚乳": {"奶香": 90, "口感层次": 50, "dairy": True},
    "燕麦奶": {"奶香": 55, "口感层次": 35, "dairy": False},
    "椰奶": {"奶香": 70, "口感层次": 45, "dairy": False, "果香": 30},
}

# ===== SWEETNESS =====
SWEETNESS_LEVELS = {
    "全糖": 1.0,
    "七分甜": 0.7,
    "五分甜": 0.5,
    "三分甜": 0.3,
    "不另外加糖": 0.0,
}

# ===== ICE LEVELS =====
ICE_LEVELS = {
    "正常冰": {"清爽度": 80, "口感层次": 30},
    "少冰": {"清爽度": 65, "口感层次": 40},
    "去冰": {"清爽度": 50, "口感层次": 50},
    "冰沙": {"清爽度": 90, "口感层次": 60},
    "常温": {"清爽度": 30, "口感层次": 60},
    "温": {"清爽度": 15, "口感层次": 65},
    "热": {"清爽度": 5, "口感层次": 70},
}

# ===== TOPPINGS =====
TOPPINGS = {
    "脆波波": {"口感层次": 20, "甜度": 15},
    "芋圆": {"口感层次": 25, "color_note": "紫色"},
    "芝士糯糯": {"口感层次": 20, "奶香": 15},
    "黑糖波波": {"口感层次": 20, "甜度": 20},
    "椰奶冻": {"口感层次": 15, "奶香": 15},
    "桂花冻": {"口感层次": 15, "color_note": "淡金色"},
    "西柚粒": {"口感层次": 25, "清爽度": 15},
    "芝士奶盖": {"口感层次": 30, "奶香": 25},
}

# ===== CLOUD TOPPINGS =====
CLOUD_TOPPINGS = {
    "芝芝云顶": {"奶香": 30, "口感层次": 25},
    "苦巧云顶": {"口感层次": 30, "甜度": 15},
    "云顶": {"口感层次": 20, "奶香": 15},
}

# ===== RESTRICTION RULES =====
RESTRICTION_RULES = [
    "鲜果仅限鲜果茶",
    "果汁仅限鲜果茶和茶特调",
    "乳品仅限牛乳茶、0咖啡因、苦巧",
    "芭乐汁与芒果汁互斥",
    "小料最多2种",
    "云顶最多1种",
    "冰沙仅限鲜果茶",
    "22点后优先0咖啡因",
    "热饮不配冰",
]

# ===== EMOTION -> RECOMMENDATION MAPPING =====
EMOTION_RECOMMEND = {
    "焦虑": {
        "category": "牛乳茶",
        "tea_base": "四季春",
        "alt_tea": "嫣红",
        "sweetness": "五分甜",
        "ice": "温",
        "toppings": ["脆波波", "芋圆"],
        "cloud": None,
        "reason": "选你最熟悉的茶底，五分甜的温润刚好接住那些'万一'。",
        "avoid": "新品",
    },
    "烦躁": {
        "category": "茶特调",
        "tea_base": "鸭屎香",
        "alt_tea": "花香奇兰",
        "sweetness": "三分甜",
        "ice": "正常冰",
        "toppings": ["西柚粒"],
        "cloud": None,
        "reason": "鸭屎香的霸道香气，配葡萄汁的清冽——先把火气压下去。不加奶，奶太温柔，压不住。",
        "avoid": "乳品",
    },
    "低落": {
        "category": "牛乳茶",
        "tea_base": "嫣红",
        "alt_tea": "碎银子普洱",
        "sweetness": "五分甜",
        "ice": "热",
        "toppings": ["芝士糯糯", "芋圆"],
        "cloud": "芝芝云顶",
        "reason": "嫣红的麦芽香，厚乳的包裹感，热的。不想说话的时候，这杯替我说。",
        "avoid": None,
    },
    "疲惫": {
        "category": "0咖啡因",
        "tea_base": "无茶底",
        "alt_tea": "四季春",
        "sweetness": "不另外加糖",
        "ice": "常温",
        "toppings": ["椰奶冻"],
        "cloud": None,
        "reason": "不问你任何问题。这杯就是'辛苦了'三个字。最轻的组合。",
        "avoid": "咖啡因",
    },
    "开心": {
        "category": "鲜果茶",
        "tea_base": "绿妍",
        "alt_tea": "茉莉绿茶",
        "sweetness": "三分甜",
        "ice": "少冰",
        "toppings": [],
        "cloud": "云顶",
        "reason": "绿妍的茉莉香配芭乐汁的粉色，今天值得。加个云顶，像给好心情加了个感叹号。",
        "avoid": None,
    },
    "麻木": {
        "category": "牛乳茶",
        "tea_base": "碎银子普洱",
        "alt_tea": "大红袍",
        "sweetness": "三分甜",
        "ice": "热",
        "toppings": ["黑糖波波", "脆波波"],
        "cloud": None,
        "reason": "碎银子的糯米香不是加进去的，是茶叶自己长出来的。嚼一嚼，帮身体回到这里。",
        "avoid": None,
    },
    "委屈": {
        "category": "0咖啡因",
        "tea_base": "无茶底",
        "alt_tea": "嫣红",
        "sweetness": "五分甜",
        "ice": "热",
        "toppings": ["椰奶冻"],
        "cloud": None,
        "reason": "椰奶的软，从头软到底。不是你的问题。从来都不是。",
        "avoid": "咖啡因",
    },
    "失恋": {
        "category": "苦巧",
        "tea_base": "可可",
        "alt_tea": None,
        "sweetness": "五分甜",
        "ice": "热",
        "toppings": ["黑糖波波"],
        "cloud": "苦巧云顶",
        "reason": "可可的苦是故意的。因为苦过之后的甜，你会记得更清楚。",
        "avoid": None,
    },
    "深夜emo": {
        "category": "0咖啡因",
        "tea_base": "无茶底",
        "alt_tea": None,
        "sweetness": "不另外加糖",
        "ice": "温",
        "toppings": ["椰奶冻", "桂花冻"],
        "cloud": None,
        "reason": "能不能睡着不重要。这个点还有人醒着陪你。最轻的组合，不加云顶。",
        "avoid": "咖啡因",
    },
    "平静": {
        "category": "牛乳茶",
        "tea_base": "四季春",
        "alt_tea": "茉莉绿茶",
        "sweetness": "三分甜",
        "ice": "少冰",
        "toppings": [],
        "cloud": None,
        "reason": "就这样淡淡的。不需要什么特别的。喝茶的人知道，最好的茶不需要太用力。",
        "avoid": None,
    },
    "犹豫": {
        "category": "鲜果茶",
        "tea_base": "茉莉绿茶",
        "alt_tea": "绿妍",
        "sweetness": "五分甜",
        "ice": "少冰",
        "toppings": ["脆波波"],
        "cloud": None,
        "reason": "茉莉绿茶，清香刚好，不压你。脆波波的嚼感，像把犹豫一口一口咬碎。",
        "avoid": None,
    },
}

# ===== PRICING =====
BASE_PRICE = 21
TOPPING_PRICE = 3
CLOUD_PRICE = 3
SPECIAL_CLOUD_PRICE = 4  # 芝士奶盖

# ===== CAPACITY =====
CAPACITY_ML = 500
