"""
Emotion → Drink 智能匹配引擎
方案一（风味向量余弦相似度）+ 方案二（情绪→分类映射）结合
"""
import math
from typing import Optional

# ============================================================
# 六维风味维度定义
# (甜度, 茶感, 奶香, 果香, 清爽度, 口感层次)
# 每项 0-100
# ============================================================

FLAVOR_DIMS = ("甜度", "茶感", "奶香", "果香", "清爽度", "口感层次")

# ============================================================
# NRC 情绪 → 目标风味向量（从 emotender_emotion.py 复用）
# ============================================================

EMOTION_FLAVOR_MATRIX = {
    "anger":        (20, 70, 20, 30, 80, 65),
    "anticipation": (45, 55, 20, 65, 75, 75),
    "disgust":      (15, 65, 10, 35, 90, 55),
    "fear":         (55, 35, 65, 30, 45, 55),
    "joy":          (65, 30, 35, 80, 75, 70),
    "sadness":      (70, 25, 80, 30, 35, 65),
    "surprise":     (50, 35, 20, 85, 80, 80),
    "trust":        (55, 45, 70, 35, 45, 75),
}

# 中文情绪名 → NRC 英文键
_CN_TO_NRC = {
    "愤怒": "anger", "期待": "anticipation", "厌恶": "disgust", "恐惧": "fear",
    "喜悦": "joy", "悲伤": "sadness", "惊讶": "surprise", "信任": "trust",
    "生气": "anger", "焦虑": "anger", "紧张": "fear", "害怕": "fear",
    "开心": "joy", "高兴": "joy", "快乐": "joy", "难过": "sadness",
    "伤心": "sadness", "吃惊": "surprise", "意外": "surprise",
}

# ============================================================
# 情绪标签 → 适配饮品分类（方案二）
# ============================================================

MOOD_TO_CATEGORIES = {
    "焦虑": ["经典牛乳鲜奶茶", "纯原叶无添加纯茶", "抹茶&可可浓醇系列", "限定工艺系列"],
    "难过": ["经典牛乳鲜奶茶", "抹茶&可可浓醇系列", "生打椰椰系列", "时令季节限定"],
    "兴奋": ["招牌芝芝鲜果茶", "生打椰椰系列", "时令季节限定", "限定工艺系列"],
    "疲惫": ["生打椰椰系列", "纯原叶无添加纯茶", "经典牛乳鲜奶茶", "限定工艺系列"],
    "清醒": ["纯原叶无添加纯茶", "喜乐芝纯茶奶盖", "招牌芝芝鲜果茶", "限定工艺系列"],
    "犹豫": ["招牌芝芝鲜果茶", "经典牛乳鲜奶茶", "喜乐芝纯茶奶盖", "时令季节限定"],
}

# ============================================================
# 饮品数据库：每杯饮品的风味向量 + 元数据
# (甜度, 茶感, 奶香, 果香, 清爽度, 口感层次)
# ============================================================

DRINK_DB = [
    # ── 招牌芝芝鲜果茶 ──
    {"name": "多肉葡萄", "category": "招牌芝芝鲜果茶", "flavor": (45, 40, 10, 85, 80, 60),
     "desc": "巨峰葡萄清甜多汁，绿茶底回甘清爽，奶盖咸甜中和果酸"},
    {"name": "芝芝多肉青提", "category": "招牌芝芝鲜果茶", "flavor": (40, 38, 10, 82, 82, 55),
     "desc": "阳光玫瑰青提玫瑰花香，甜度更高、清甜淡雅"},
    {"name": "芝芝莓莓", "category": "招牌芝芝鲜果茶", "flavor": (50, 35, 12, 80, 72, 55),
     "desc": "草莓酸甜浓郁，果香鲜活，微酸开胃"},
    {"name": "多肉桃李", "category": "招牌芝芝鲜果茶", "flavor": (48, 32, 5, 78, 78, 58),
     "desc": "黄桃+红心李子双果融合，层次丰富"},
    {"name": "满杯红柚", "category": "招牌芝芝鲜果茶", "flavor": (35, 38, 5, 75, 85, 45),
     "desc": "西柚微苦清甜，解腻刮油，低卡无负担"},
    {"name": "多肉杨梅", "category": "招牌芝芝鲜果茶", "flavor": (50, 30, 5, 82, 70, 55),
     "desc": "仙居杨梅醇厚酸甜，夏季限定"},
    {"name": "酷黑莓桑", "category": "招牌芝芝鲜果茶", "flavor": (42, 35, 5, 80, 72, 60),
     "desc": "黑莓+桑葚双重浆果，花青素丰富"},

    # ── 生打椰椰系列 ──
    {"name": "生打椰椰奶冻", "category": "生打椰椰系列", "flavor": (45, 10, 55, 20, 65, 60),
     "desc": "醇厚椰奶香顺滑，搭配Q弹椰奶冻+脆波波"},
    {"name": "多肉芒芒甘露", "category": "生打椰椰系列", "flavor": (60, 15, 45, 75, 55, 70),
     "desc": "芒果+西柚+椰乳，杨枝甘露升级版"},
    {"name": "椰椰芒芒", "category": "生打椰椰系列", "flavor": (58, 10, 50, 72, 58, 55),
     "desc": "芒果椰香更纯粹，无西柚苦味"},
    {"name": "生打椰椰葡萄", "category": "生打椰椰系列", "flavor": (48, 12, 48, 70, 62, 58),
     "desc": "葡萄果香叠加椰乳清甜，双重口感"},

    # ── 经典牛乳鲜奶茶 ──
    {"name": "烤黑糖波波牛乳", "category": "经典牛乳鲜奶茶", "flavor": (75, 30, 85, 10, 20, 75),
     "desc": "焦香黑糖醇厚，软糯波波嚼劲十足，热饮天花板"},
    {"name": "水牛乳双拼波波", "category": "经典牛乳鲜奶茶", "flavor": (68, 25, 88, 8, 22, 70),
     "desc": "水牛乳奶香浓郁，黑糖波波+芋圆双料"},
    {"name": "咸酪碎银子", "category": "经典牛乳鲜奶茶", "flavor": (35, 70, 65, 5, 25, 72),
     "desc": "普洱熟茶醇厚温润，咸芝士奶盖，秋冬首选"},
    {"name": "糯糯芋泥鲜奶", "category": "经典牛乳鲜奶茶", "flavor": (60, 15, 80, 5, 25, 68),
     "desc": "手捣厚芋泥绵密香甜，饱腹感强"},

    # ── 喜乐芝纯茶奶盖 ──
    {"name": "芝士绿妍", "category": "喜乐芝纯茶奶盖", "flavor": (30, 65, 35, 15, 55, 50),
     "desc": "茉莉绿茶清香鲜爽，经典入门奶盖茶"},
    {"name": "芝士金凤茶王", "category": "喜乐芝纯茶奶盖", "flavor": (25, 78, 35, 8, 40, 60),
     "desc": "乌龙茶香醇厚，炭火香气，回甘悠长"},
    {"name": "芝士四季春", "category": "喜乐芝纯茶奶盖", "flavor": (28, 68, 32, 12, 52, 48),
     "desc": "四季春乌龙清甜柔和，大众接受度最高"},
    {"name": "芝士玉露茶后", "category": "喜乐芝纯茶奶盖", "flavor": (22, 72, 30, 10, 60, 55),
     "desc": "日式煎茶鲜爽清淡，微海苔香气"},

    # ── 抹茶&可可浓醇系列 ──
    {"name": "三倍厚抹茶拿铁", "category": "抹茶&可可浓醇系列", "flavor": (40, 55, 75, 5, 30, 68),
     "desc": "宇治抹茶微苦回甘，三重乳基底加厚"},
    {"name": "苦巧咸酪", "category": "抹茶&可可浓醇系列", "flavor": (30, 60, 70, 5, 25, 80),
     "desc": "纯黑可可醇厚微苦，苦甜咸三层风味"},
    {"name": "提拉米苏浓巧", "category": "抹茶&可可浓醇系列", "flavor": (55, 45, 72, 8, 20, 75),
     "desc": "可可+芝士奶香融合，复刻提拉米苏"},

    # ── 纯原叶无添加纯茶 ──
    {"name": "绿妍", "category": "纯原叶无添加纯茶", "flavor": (8, 85, 2, 10, 78, 40),
     "desc": "九窨茉莉绿茶，花香清雅，零糖零卡"},
    {"name": "金凤茶王", "category": "纯原叶无添加纯茶", "flavor": (5, 90, 2, 5, 55, 55),
     "desc": "醇厚炭香乌龙，回甘悠长，茶感浓郁"},
    {"name": "四季春", "category": "纯原叶无添加纯茶", "flavor": (10, 82, 2, 12, 70, 42),
     "desc": "清甜柔和，花香果香交织，清爽解腻"},
    {"name": "碎银子普洱", "category": "纯原叶无添加纯茶", "flavor": (12, 88, 5, 3, 35, 58),
     "desc": "温润顺滑，糯香浓郁，养胃暖身"},
    {"name": "雪毫茉王", "category": "纯原叶无添加纯茶", "flavor": (8, 92, 2, 8, 72, 48),
     "desc": "茉莉香气极致浓郁，鲜爽甘甜"},

    # ── 限定工艺系列 ──
    {"name": "铜锅现煲锅煲乳茶", "category": "限定工艺系列", "flavor": (40, 75, 65, 5, 25, 78),
     "desc": "铜锅单杯焖煮，茶香充分释放，醇厚层次感极强"},
    {"name": "铜网手冲茗茶", "category": "限定工艺系列", "flavor": (5, 95, 2, 3, 65, 55),
     "desc": "手冲精品原叶茶，纯品茶仪式感"},
    {"name": "康普茶轻酵果茶", "category": "限定工艺系列", "flavor": (30, 45, 5, 60, 82, 65),
     "desc": "72小时发酵，气泡微酸，清爽助消化"},

    # ── 时令季节限定 ──
    {"name": "黄皮康普茶", "category": "时令季节限定", "flavor": (32, 40, 3, 65, 85, 58),
     "desc": "黄皮酸甜+康普茶微酸气泡，夏日解腻"},
    {"name": "荔枝系列", "category": "时令季节限定", "flavor": (55, 30, 5, 78, 75, 50),
     "desc": "荔枝清甜多汁，果香浓郁"},
    {"name": "水蜜桃系列", "category": "时令季节限定", "flavor": (58, 28, 5, 80, 72, 48),
     "desc": "水蜜桃香甜软糯，桃香浓郁"},
    {"name": "柿子鲜果茶", "category": "时令季节限定", "flavor": (55, 32, 5, 70, 65, 52),
     "desc": "柿子醇厚甜糯，秋季限定"},
    {"name": "石榴鲜果茶", "category": "时令季节限定", "flavor": (42, 35, 5, 72, 80, 50),
     "desc": "石榴清甜爆汁，秋季限定"},
    {"name": "车厘子鲜果茶", "category": "时令季节限定", "flavor": (50, 38, 8, 75, 70, 58),
     "desc": "车厘子醇厚甜酸，冬季限定"},
    {"name": "烤栗子系列", "category": "时令季节限定", "flavor": (65, 20, 60, 10, 25, 65),
     "desc": "烤栗子绵密香甜，秋冬暖饮"},
    {"name": "热红酒风味果茶", "category": "时令季节限定", "flavor": (50, 45, 5, 55, 50, 70),
     "desc": "香料风味浓郁，冬日氛围感拉满"},
]


# ============================================================
# 核心算法
# ============================================================

def cosine_similarity(a: tuple, b: tuple) -> float:
    """计算两个向量的余弦相似度"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def weighted_emotion_flavor(scores: dict) -> tuple:
    """
    从 NRC 八类分数加权计算目标风味向量。
    scores: {"anger": 0.0, "fear": 0.7, "sadness": 0.3, ...}
    返回六维元组
    """
    dims = [0.0] * 6
    total_weight = 0.0
    for emotion, score in scores.items():
        if score <= 0.05:
            continue
        flavor = EMOTION_FLAVOR_MATRIX.get(emotion)
        if flavor is None:
            continue
        for i in range(6):
            dims[i] += flavor[i] * score
        total_weight += score
    if total_weight == 0:
        # 兜底：信任情绪
        return EMOTION_FLAVOR_MATRIX["trust"]
    return tuple(round(d / total_weight) for d in dims)


def get_eligible_categories(emotion_label: str) -> list[str]:
    """从情绪标签获取适配的饮品分类列表"""
    return MOOD_TO_CATEGORIES.get(emotion_label, list(set(d["category"] for d in DRINK_DB)))


def match_drinks(
    scores: dict,
    emotion_label: str,
    top_n: int = 3,
) -> list[dict]:
    """
    核心匹配函数：
    1. 从情绪分数计算目标风味向量
    2. 筛选出适配分类下的饮品
    3. 按余弦相似度排序，返回 Top N

    返回: [{"name": "...", "category": "...", "flavor": (...), "similarity": 0.95, "desc": "..."}]
    """
    target_flavor = weighted_emotion_flavor(scores)
    eligible_cats = get_eligible_categories(emotion_label)

    candidates = []
    for drink in DRINK_DB:
        if drink["category"] not in eligible_cats:
            continue
        sim = cosine_similarity(target_flavor, drink["flavor"])
        candidates.append({
            "name": drink["name"],
            "category": drink["category"],
            "flavor": drink["flavor"],
            "flavor_dict": dict(zip(FLAVOR_DIMS, drink["flavor"])),
            "similarity": round(sim, 4),
            "desc": drink["desc"],
        })

    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates[:top_n]


def build_llm_drink_prompt(candidates: list[dict], emotion_label: str, user_text: str) -> str:
    """
    构建给 LLM 的饮品选择 prompt，让它从 Top 3 中选一杯并写推荐理由。
    """
    lines = []
    for i, c in enumerate(candidates, 1):
        flavor_str = ", ".join(f"{k}:{v}" for k, v in c["flavor_dict"].items())
        lines.append(f"{i}. {c['name']}（{c['category']}）— 相似度 {c['similarity']:.2f}")
        lines.append(f"   口味特点：{c['desc']}")
        lines.append(f"   风味向量：{flavor_str}")

    return f"""你是情绪茶饮师茗茗。用户情绪为「{emotion_label}」，原话：「{user_text}」

系统根据情绪风味向量匹配了以下 3 杯候选饮品：

{chr(10).join(lines)}

请从中选择最合适的一杯，并用 2-3 句话写推荐理由。
要求：
- 引用用户原话中的关键词
- 用感官语言描述饮品
- 不要提到"相似度""向量"等技术词
- 语气温暖、像朋友说话

输出 JSON：
{{"drink_name": "选中的饮品名", "reason": "推荐理由"}}"""


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    # 模拟：用户说"明天就要答辩了，脑子停不下来"
    test_scores = {"fear": 0.7, "anticipation": 0.25, "anger": 0.05}
    test_label = "焦虑"

    print(f"情绪: {test_label}")
    print(f"分数: {test_scores}")
    print(f"目标风味: {weighted_emotion_flavor(test_scores)}")
    print(f"适配分类: {get_eligible_categories(test_label)}")
    print()

    results = match_drinks(test_scores, test_label)
    for r in results:
        print(f"  {r['name']} ({r['category']}) — 相似度 {r['similarity']:.4f}")
        print(f"    {r['desc']}")
        print()

    print("---LLM Prompt---")
    print(build_llm_drink_prompt(results, test_label, "明天就要答辩了，脑子停不下来"))
