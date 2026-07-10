import json
import logging
import os
import hashlib
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("emotender")

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel

try:
    from funasr import AutoModel
except ModuleNotFoundError:
    AutoModel = None

load_dotenv()

app = FastAPI(title="EmoTender Backend")


class TextAnalyzeRequest(BaseModel):
    user_text: str
    username: Optional[str] = None


class UserLoginRequest(BaseModel):
    username: str


class UserLogoutRequest(BaseModel):
    username: Optional[str] = None

BASE_DIR = Path(__file__).resolve().parent
AUDIO_PATH = BASE_DIR / "recording.wav"
PROMPT_LIBRARY_PATH = BASE_DIR / "prompts" / "drink_mapping.json"
PROFILE_SUMMARY_PROMPT_PATH = BASE_DIR / "prompts" / "profile_summary_prompt.md"
PROFILE_DIR = BASE_DIR / "data" / "profiles"
recording_process: Optional[subprocess.Popen] = None
last_result: Optional[dict] = None
conversation_history: list[dict] = []
conversation_summary = ""
emotion_history: list[str] = []  # Track emotion trend across turns
current_username: Optional[str] = None
MAX_EMOTION_HISTORY = 5

MAX_HISTORY_ITEMS = 8
MAX_SUMMARY_CHARS = 1200
NO_FORMAL_DRINK_NAME = "无正式推荐"
PROFILE_LIST_KEYS = (
    "taste_preferences",
    "emotion_patterns",
    "drink_history",
    "conversation_style",
    "avoidances",
)

# ==================== Drink Menu (from teammate frontend/backend update) ====================
DRINK_MENU = {
    "单品": {
        "清醒": {
            "name": "冷启动", "name_en": "Cold Start",
            "recipe_modules": ["clear_balance", "bitter_focus", "spark_restart"],
            "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
            "color_profile": "透明偏冷调，带一点淡青色",
            "face_state": "focused", "action_sequence": "make_cold_start",
            "kernel": "不是提神，是'在长夜里给自己点一盏孤灯'",
            "emotional_value": "独处时的清醒，比喧闹中的狂欢更体面",
            "serve_line": "这杯叫《冷启动》。你看它，像不像凌晨三点的海面？我用清酒和柚子汁调出了这种苦，但苦得刚刚好。喝完它，世界安静了，你也是。",
            "flavor": "我不加多余的甜，因为清醒本身就是一种味道。清酒做底，鲜柚和青柠提供锋利的酸度，最后用苏打水的气泡把它们托起来——那些压着你胸口的东西，会跟着气泡浮上来，再散掉。",
            "backstory": "以前有个总坐角落的客人，每次来都点这杯。他说：'老柯，喝别的像在逃避，喝这杯像在跟自己谈判。'后来他走了，每年跨年还给我发消息：'今晚没你，但窗外的海还是蓝的。'",
            "recipe": "清酒45ml + 鲜榨柚子汁20ml + 青柠汁10ml + 薄荷叶3片 + 龙舌兰糖浆5ml + 苏打水补满，高球杯加冰",
            "color": "透明偏冷调，淡青色",
        },
        "兴奋": {
            "name": "气泡重启", "name_en": "Spark Restart",
            "recipe_modules": ["bright_bubble", "spark_restart", "clear_balance"],
            "flavor_profile": "明亮、轻酸、气泡感明显",
            "color_profile": "明亮浅黄色或淡青色",
            "face_state": "happy", "action_sequence": "make_spark_restart",
            "kernel": "不是狂欢，是'雨停之后，屋檐还在滴水，但天空已经放亮'",
            "emotional_value": "那些微小的、明亮的喜悦，值得被郑重对待",
            "serve_line": "这杯叫《气泡重启》。你看杯里那些往上窜的小气泡，像不像雨后冒出来的新芽？血橙的明亮和起泡酒的跳跃，就是为了告诉你——日子就是靠这些瞬间撑起来的。",
            "flavor": "血橙的酸是清早推开窗吸的第一口凉气，起泡酒的气泡是踩过水洼溅起的亮光。金酒带来植物的清香，但我不把它调得太甜，因为真正的高兴，不需要太用力的证明。",
            "backstory": "这杯是我为一个刚离职的老客人调的。他那天进来，笑得像卸了盔甲。他说：'老柯，我三个月没笑这么大声了。'我给他倒了这杯，气泡滋滋响，像在替他鼓掌。",
            "recipe": "金酒40ml + 鲜榨血橙汁30ml + 柠檬汁10ml + 蜂蜜糖浆10ml + 香槟/起泡酒30ml漂浮，蝶形香槟杯",
            "color": "明亮橘粉渐变，底部浓郁上层轻盈",
        },
        "难过": {
            "name": "软着陆", "name_en": "Soft Landing",
            "recipe_modules": ["soft_comfort", "blue_calm", "clear_balance"],
            "flavor_profile": "柔和、低酸、低刺激、有一点甜感",
            "color_profile": "浅蓝紫色或淡粉色",
            "face_state": "gentle", "action_sequence": "make_soft_comfort",
            "kernel": "不是安慰，是'夜深知雪重，时闻折竹声'的静默陪伴",
            "emotional_value": "你可以脆弱，吧台不审判你",
            "serve_line": "这杯叫《软着陆》。温热的牛奶和朗姆酒，像不像冬天窗户上呵出的气？喝完别急着说话，让这口温柔先替你落个地。",
            "flavor": "我把所有的烈性都藏在了温牛奶和枫糖底下。舌尖碰到它的时候，先是肉桂和肉豆蔻的香料暖意，然后是奶香的顺滑。像有人轻轻拍了拍你的手背，说'没事'。",
            "backstory": "有一年冬天，店里暖气坏了，一个姑娘坐了一整晚。我给她这杯，她捧在手里暖了半小时才喝。临走她说：'这杯不是酒，是围巾。'后来，'围巾'就留下来了。",
            "recipe": "白朗姆30ml + 温牛奶60ml + 香草精2滴 + 枫糖浆15ml + 肉桂粉微量 + 肉豆蔻微量，陶瓷马克杯",
            "color": "奶白微黄，暖色调",
        },
        "疲惫": {
            "name": "灰度模式", "name_en": "Grayscale Mode",
            "recipe_modules": ["clear_balance", "bitter_focus"],
            "flavor_profile": "深沉、微苦、低甜、有草本余韵",
            "color_profile": "淡金色，微光柔和",
            "face_state": "gentle", "action_sequence": "make_cold_start",
            "kernel": "不是单调，是褪去五彩斑斓的伪装后，只剩黑白分明的'算了'",
            "emotional_value": "不再强求解释，是一种'都行'的、沉到底的松弛",
            "serve_line": "这杯叫《灰度模式》。日本威士忌的深沉，配冷泡洋甘菊的草本，像不像雨天旧报纸上洇开的铅字？它不讨好任何人的眼睛。喝完它，那些紧绷的执念，会融成一种温柔的漠然。",
            "flavor": "我把所有的甜都压到了最低，只留威士忌的木质调和洋甘菊的微甘。像翻开一本旧书的味道，纸页发黄，但字迹清晰。你品到的涩，不是失败，是你终于允许自己'不选择'。",
            "backstory": "有个写代码的客人，天天来修bug，眼神永远焦灼。他说：'白天世界是彩色的，每个颜色都在催我干活。'我给他这杯，他盯着看了很久，忽然舒了口气：'原来不选颜色，才是最大的自由。'",
            "recipe": "日本威士忌35ml + 洋甘菊茶(冷泡)45ml + 柠檬皮1片 + 蜂蜜10ml + 干燥薰衣草2粒，古典杯加大冰球",
            "color": "淡金色，微光柔和",
        },
        "焦虑": {
            "name": "断点续传", "name_en": "Breakpoint Resume",
            "recipe_modules": ["blue_calm", "clear_balance"],
            "flavor_profile": "清凉、清脆、微甜回甘",
            "color_profile": "淡绿色，清澈透明",
            "face_state": "focused", "action_sequence": "make_soft_comfort",
            "kernel": "不是重来，是那个被生活猛然掐断的瞬间，被小心翼翼地接住了、续上了",
            "emotional_value": "允许中断，允许暂停，因为你知道断掉的那根线头还在手里",
            "serve_line": "这杯叫《断点续传》。你看这杯酒，伏特加做底，青瓜和接骨木花提供了一条清晰的'线'。喝下去，那根断掉的弦，会自己找到接口。",
            "flavor": "开头是青瓜的清脆和青柠的酸，像进度条突然卡住。但别急，接骨木花的回甘是续传成功的提示音。芹菜苦精像一声极轻的叹息——苦涩之后，一切归于平静。",
            "backstory": "有个写小说的客人，卡文卡了整整两个月，每晚来就盯着这杯发呆。有一天他忽然一口闷了，眼睛亮了：'我知道主角下一章怎么走了。'后来他书里写：'生活给我们的从来不是答案，是一个断点后的回车键。'",
            "recipe": "伏特加40ml + 鲜榨青瓜汁30ml + 青柠汁15ml + 接骨木花糖浆10ml + 芹菜苦精2滴，岩石杯加碎冰",
            "color": "淡绿色，清澈透明",
        },
        "犹豫": {
            "name": "延时摄影", "name_en": "Time-lapse",
            "recipe_modules": ["clear_balance", "soft_comfort"],
            "flavor_profile": "烟熏辛辣开头，果甜收尾",
            "color_profile": "琥珀色带轻微浑浊",
            "face_state": "thinking", "action_sequence": "gesture_thinking",
            "kernel": "不是等待，是'你盯着花苞看了很久，它不动；你转个身，它忽然开了'的那种时光的狡猾",
            "emotional_value": "你不需要一直盯着进度条，该来的，会在你不注意的时候悄悄抵达",
            "serve_line": "这杯叫《延时摄影》。梅斯卡尔的烟熏香，混着菠萝和姜的辛辣，像不像你盯着窗台发呆时，光影偷偷爬过墙角的痕迹？喝完别回头，你等的那个答案，可能已经在路上了。",
            "flavor": "开头是黑胡椒和姜的锐利辛辣，让你的思路卡在犹豫的瞬间。但收尾会涌上来菠萝的果甜和梅斯卡尔独特的烟熏回甘——像春天夜里，你忽然闻到不知从哪飘来的花香，你找不见花在哪，但你知道它开了。",
            "backstory": "有个做纪录片的姑娘，拍一朵昙花开放，蹲了七个通宵。第七晚她撑不住睡着了，醒来发现花已经开败了——但监视器里录下了全过程。她冲进店里说：'老柯，我守了七天，它偏偏在我闭眼的时候开。'我给她这杯。她说：'懂了，有些事不是等来的，是你忘了等，它自己就来了。'",
            "recipe": "梅斯卡尔30ml + 鲜榨菠萝汁25ml + 青柠汁10ml + 姜糖浆10ml + 黑胡椒微量，尼克诺拉杯",
            "color": "琥珀色带轻微浑浊",
        },
    },
    "混合": [
        {"name":"晨光破晓","name_en":"Dawn Break","emotions":["清醒","兴奋"],"recipe_modules":["clear_balance","bright_bubble","spark_restart"],"flavor_profile":"清爽明亮，层次渐变","color_profile":"淡青向橘粉渐变","face_state":"happy","action_sequence":"make_spark_restart","serve_line":"这杯叫《晨光破晓》。你看它杯里那层从青到粉的渐变，像不像你熬夜等来的那个日出？第一口是清醒的冷，第二口是兴奋的暖——喝完你会发现，原来克制和放肆，可以在一杯酒里握手言和。","flavor":"清酒的米香是底色，像你脑子里那个理性的声音。但金酒的血橙和起泡酒会慢慢浮上来——那是你压抑了一整天的、想跑想跳的那部分。","recipe":"清酒25ml+金酒20ml+柚子汁15ml+血橙汁20ml+柠檬汁5ml+蜂蜜糖浆5ml+苏打水20ml+起泡酒20ml漂浮，高球杯加冰","color":"杯底淡青色向杯口橘粉色渐变","backstory":"有个做审计的姑娘，每年忙季结束那天都来。她说：'老柯，我连续六十天早上六点起，今天终于不用设闹钟了，但反而睡不着。'我给她这杯。她看着杯里的分层慢慢混在一起，喝了一口说：'原来我身体里那个想赖床的小孩，和那个逼自己起床的大人，可以同时被满足。'"},
        {"name":"炉火余烬","name_en":"Ember Glow","emotions":["难过","疲惫"],"recipe_modules":["soft_comfort","blue_calm"],"flavor_profile":"温热柔和，低酸无刺激","color_profile":"暖调奶白色","face_state":"gentle","action_sequence":"make_soft_comfort","serve_line":"这杯叫《炉火余烬》。它捧在手里的温度，像不像小时候冬天围炉时，最后那点炭火的余温？别急着喝，先让掌心暖一暖。这杯酒不问你发生了什么，它只负责接住你。","flavor":"温牛奶是底，像一条厚毛毯把你裹住。白朗姆的甜润和威士忌的木质调叠在一起，像炉火里慢慢燃尽的木头。洋甘菊和薰衣草是那缕飘起来的烟——不浓，但你知道它还在。","recipe":"白朗姆20ml+日本威士忌15ml+温牛奶50ml+冷泡洋甘菊茶20ml+香草精1滴+枫糖浆12ml+肉桂粉微量+肉豆蔻微量+干燥薰衣草1粒，陶瓷马克杯","color":"暖调奶白色，表面浮着淡金色香料","backstory":"有个刚失去母亲的老客人走进来，眼睛是红的，但一滴泪都没掉。他在吧台坐了四十分钟，什么都没点。我给他这杯，他捧了二十分钟才开始喝。喝完他说：'我妈走之前那晚，握着我的手也是这个温度。'"},
        {"name":"静湖锚点","name_en":"Still Anchor","emotions":["焦虑","清醒"],"recipe_modules":["blue_calm","clear_balance"],"flavor_profile":"清澈冷静，极低甜度","color_profile":"极淡透明绿色","face_state":"focused","action_sequence":"make_cold_start","serve_line":"这杯叫《静湖锚点》。你看它清澈得像不像暴雨来临前，那片刻的、诡异的宁静？伏特加是底，青瓜和接骨木花是水面——喝完它，那些在你脑子里狂奔的念头，会像被按了暂停键。","flavor":"伏特加是'无'，它不给你任何多余的味道，只给你一个干干净净的容器。青瓜汁和芹菜苦精是那种'深呼吸一口雨后空气'的清凉感。接骨木花的甜很克制，像你在乱成一团的桌面上，终于找到了一支还能写字的笔。","recipe":"伏特加40ml+清酒15ml+鲜榨青瓜汁30ml+鲜榨柚子汁10ml+青柠汁8ml+接骨木花糖浆5ml+芹菜苦精3滴，岩石杯加碎冰","color":"极淡的透明绿色，清澈见底","backstory":"有个创业的年轻人，有段时间天天来，手机响个不停。有一天他忽然说：'老柯，我每天回两百条消息，但没有一条是回给我自己的。'我给他这杯。他喝了三口，关了手机。喝完他说：'原来安静不是环境，是你终于允许自己听不见。'"},
        {"name":"花火指南","name_en":"Spark Compass","emotions":["犹豫","兴奋"],"recipe_modules":["bright_bubble","spark_restart"],"flavor_profile":"烟熏果香，气泡跳跃","color_profile":"琥珀色微浑+橘粉气泡","face_state":"happy","action_sequence":"make_spark_restart","serve_line":"这杯叫《花火指南》。你看它杯底那层浑浊的琥珀色，像不像你在脑子里反复修改了八百遍的那个决定？但上面那层起泡酒会告诉你——犹豫是正常的，但花火不会等你看清楚了才绽放。","flavor":"梅斯卡尔是烟熏的、野性的，像你心里那个'不管了'的冲动。菠萝和血橙把它裹上了一层果香，让你觉得这个决定没那么可怕。起泡酒不是用来喝的，是用来提醒你的——气泡往上冲的时候，你的脚已经离开地面了。","recipe":"梅斯卡尔20ml+金酒20ml+鲜榨菠萝汁25ml+鲜榨血橙汁20ml+青柠汁5ml+姜糖浆8ml+蜂蜜糖浆5ml+黑胡椒微量+起泡酒25ml漂浮，蝶形香槟杯","color":"底层琥珀色微浑，上层浅橘粉透明","backstory":"有个做了十年公务员的客人，每天晚上来，翻手机里一个辞职信草稿，翻了半年。有一天他进来，没掏手机。我给他这杯。他喝了一半，忽然笑了：'老柯，我明天交信。'后来他去了云南做民宿，给我寄过一箱他自己酿的梅子酒。"},
        {"name":"雨停之后","name_en":"After Rain","emotions":["难过","焦虑"],"recipe_modules":["soft_comfort","blue_calm"],"flavor_profile":"温热与清凉双层口感","color_profile":"下层奶白上层淡绿","face_state":"gentle","action_sequence":"make_soft_comfort","serve_line":"这杯叫《雨停之后》。它入口的第一秒是温的，像眼泪滑过脸颊的温度。但别怕，第二秒会有一股凉意跟上来——那是雨停了之后，你推开窗吸到的第一口空气。","flavor":"白朗姆和温牛奶是那个'允许你哭'的怀抱，甜润、包容、不评判。但伏特加和青瓜汁会从底下浮上来——那是你身体里更理智的那部分，告诉你'哭完了，擦擦脸，去喝杯热水'。","recipe":"白朗姆20ml+伏特加15ml+温牛奶30ml+鲜榨青瓜汁20ml+香草精1滴+枫糖浆10ml+接骨木花糖浆5ml，陶瓷马克杯","color":"下层奶白，上层淡绿透明，两层分明","backstory":"有个做护士的姑娘，疫情那几年常来。有一晚她进来，口罩没摘就趴在吧台上。我把这杯推过去。她喝了一口说：'老柯，我今天送走了一个病人，家属没来，我一直握着他的手。'她说完就哭了。哭完把那杯酒喝完，站起来说：'好了，我回去值夜班了。'"},
        {"name":"荒野驿站","name_en":"Waystation","emotions":["疲惫","犹豫"],"recipe_modules":["clear_balance","soft_comfort"],"flavor_profile":"烟熏深沉，微甜温暖","color_profile":"琥珀色带轻微浑浊","face_state":"gentle","action_sequence":"gesture_thinking","serve_line":"这杯叫《荒野驿站》。你看它杯壁那层慢慢凝出的水珠，像不像你走了很远的路之后，额头上的汗？别急着决定下一站去哪儿，先让这口烟熏的暖意，把你的脚底板从路上解放出来。","flavor":"威士忌的深沉和梅斯卡尔的烟熏叠在一起，像荒野里远远看见的、一间亮着灯的木屋。洋甘菊的草本是那种'推开门，闻到一股旧木头和干草'的味道。","recipe":"日本威士忌25ml+梅斯卡尔15ml+冷泡洋甘菊茶30ml+鲜榨菠萝汁15ml+青柠汁5ml+姜糖浆5ml+蜂蜜糖浆5ml+黑胡椒微量，古典杯加大冰球","color":"琥珀色带轻微浑浊，像旧木头的颜色","backstory":"有个跑长途货运的司机，每两个月路过一次这个城市。他每次都进来喝一杯，然后靠墙睡到天亮。有一回他走之前说：'老柯，我开了二十年车，每次停下来都不知道自己在哪儿。'"},
        {"name":"冰岛温泉","name_en":"Iceland Spring","emotions":["清醒","难过"],"recipe_modules":["clear_balance","soft_comfort"],"flavor_profile":"冷热双层，清冽中带温柔","color_profile":"下层清澈淡青，上层奶白暖黄","face_state":"focused","action_sequence":"make_cold_start","serve_line":"这杯叫《冰岛温泉》。你看它——下面是冰的，上面是温的。像不像你心里那个'我没事'和'我不好'在同时说话？别急着让它们分出胜负，先喝一口，让它们在你嘴里碰个头。","flavor":"清酒是冰的、锐利的，像你脑子里那个'理性分析'的声音。柚子的苦是它的锋芒。但温牛奶和枫糖会慢慢漫上来——那是你身体里更诚实的那部分，说'其实我有点疼'。","recipe":"清酒30ml+白朗姆15ml+鲜榨柚子汁15ml+温牛奶25ml+香草精1滴+枫糖浆8ml+龙舌兰糖浆3ml+肉豆蔻微量，古典杯不加冰","color":"下层清澈淡青，上层奶白暖黄","backstory":"有个离婚的男客人，每次来都点最烈的酒。有一晚他忽然说：'老柯，我在法庭上特别冷静，律师都夸我体面。但我昨晚一个人把冰箱里的剩菜全倒掉了，一边倒一边哭。'我给他这杯。他后来再没点过烈酒。"},
        {"name":"金色午觉","name_en":"Golden Nap","emotions":["疲惫","兴奋"],"recipe_modules":["bright_bubble","spark_restart","clear_balance"],"flavor_profile":"温暖明亮，轻盈气泡","color_profile":"整体暖金色","face_state":"happy","action_sequence":"make_spark_restart","serve_line":"这杯叫《金色午觉》。你看它杯里那层温暖的金色，像不像窗帘没拉严时，漏在你被子上的那一条光？喝下去，你会觉得身体醒了，但脑子还愿意再赖一会儿床。","flavor":"威士忌是深沉的那个你，告诉你'慢慢来'。但金酒和血橙会轻轻推你的肩膀——那是阳光在叫你起床。洋甘菊是那种'再躺五分钟'的赖床感，蜂蜜是那五分钟里做的那个美梦。","recipe":"日本威士忌20ml+金酒20ml+冷泡洋甘菊茶25ml+鲜榨血橙汁20ml+柠檬汁5ml+蜂蜜糖浆12ml+起泡酒20ml漂浮，蝶形香槟杯","color":"整体暖金色，下层略深，上层明亮轻盈","backstory":"有个写代码的自由职业者，日夜颠倒。他说：'老柯，我连续三个月每天只睡四小时，但我写不出任何东西。'我给他这杯。他喝到第三口说：'我好像很久没在白天醒着的时候，觉得高兴了。'"},
        {"name":"决策树","name_en":"Decision Tree","emotions":["焦虑","犹豫"],"recipe_modules":["blue_calm","clear_balance","soft_comfort"],"flavor_profile":"浑浊厚重，香料层次丰富","color_profile":"琥珀色带丰富悬浮颗粒","face_state":"thinking","action_sequence":"gesture_thinking","serve_line":"这杯叫《决策树》。你看它浑浊的琥珀色里，那些细小的悬浮物，像不像你脑子里那些纠缠不清的选项？别急着挑，先让烟熏和姜暖把你那些'万一'先放一放。","flavor":"伏特加是空白，它是你面前那张干净的纸。梅斯卡尔是烟熏的、有力的，像你内心里那个'其实早就有答案'的声音。菠萝的甜是'选A也不错'，青瓜的清爽是'选B也行'。","recipe":"伏特加20ml+梅斯卡尔20ml+鲜榨菠萝汁20ml+鲜榨青瓜汁15ml+青柠汁8ml+接骨木花糖浆8ml+姜糖浆5ml+黑胡椒微量+芹菜苦精2滴，岩石杯加碎冰","color":"琥珀色带丰富悬浮颗粒，浑浊厚重","backstory":"有个刚毕业的男孩，拿了两个offer，来店里坐了三晚。第三晚我把这杯推过去。他喝完忽然说：'其实我知道选哪个，我只是不敢承认。'"},
        {"name":"子夜书简","name_en":"Midnight Letter","emotions":["清醒","疲惫"],"recipe_modules":["clear_balance","bitter_focus"],"flavor_profile":"澄澈深沉，微苦有回甘","color_profile":"淡金色，澄澈透明","face_state":"focused","action_sequence":"make_cold_start","serve_line":"这杯叫《子夜书简》。你看它淡金色的光泽，像不像深夜台灯下，一张被反复修改过、但终于写完了的信纸？喝完它，你会发现——你不是不想睡，你是不舍得结束这一天。","flavor":"清酒的凛冽和威士忌的深沉，像你脑子里的'清醒'和身体里的'疲惫'在互相拉扯。洋甘菊是那个劝你'去睡吧'的声音，柚子的苦是'但还有事没想通'。蜂蜜是最后的妥协。","recipe":"清酒25ml+日本威士忌20ml+冷泡洋甘菊茶30ml+鲜榨柚子汁15ml+柠檬皮1片+蜂蜜糖浆8ml+干燥薰衣草1粒，古典杯加大冰球","color":"淡金色，澄澈透明，像深夜灯光下的茶汤","backstory":"有个写专栏的作家，截稿日当晚总来。他每次在吧台写完最后一段，然后点这杯。他说：'在你这儿喝完这杯再回去，那个结尾才算是被郑重地放好了。'"},
        {"name":"雨中探戈","name_en":"Tango in the Rain","emotions":["兴奋","难过"],"recipe_modules":["bright_bubble","soft_comfort"],"flavor_profile":"热烈与温柔三层渐变","color_profile":"底层橘红，中层淡粉，上层奶白","face_state":"happy","action_sequence":"make_spark_restart","serve_line":"这杯叫《雨中探戈》。你看它——下面是热烈的橘红，上面是沉静的奶白。像不像你心里那场'不管了，先笑吧'和'但我还是有点疼'的拉锯战？喝下去你会发现，它们可以同时存在。","flavor":"金酒和血橙是那个'踩着水洼跳舞'的你，明亮、果决、带着气泡的俏皮。但白朗姆和温牛奶会从底下托住你——那是你知道'就算摔倒了，也会有人接住'的安全感。","recipe":"金酒20ml+白朗姆15ml+鲜榨血橙汁25ml+温牛奶20ml+柠檬汁5ml+蜂蜜糖浆10ml+枫糖浆5ml+肉桂粉微量+起泡酒15ml，蝶形香槟杯","color":"底层橘红，中层淡粉气泡，上层奶白，三层分明","backstory":"有个学舞蹈的姑娘，比赛前被分手。她来店里说：'老柯，我明天要上台，但我现在笑不出来。'我给她这杯。她看着杯子愣了很久，然后忽然笑了：'这杯像我的舞——前半段是快乐的，后半段是心碎的，但观众不知道，他们只看到美。'"},
        {"name":"尘埃落定","name_en":"Settle Down","emotions":["犹豫","焦虑"],"recipe_modules":["clear_balance","blue_calm"],"flavor_profile":"浑浊沉降，辛香回甘","color_profile":"浑浊淡琥珀色","face_state":"thinking","action_sequence":"gesture_thinking","serve_line":"这杯叫《尘埃落定》。你看它杯里那些细小的悬浮物，在光线下慢慢往下沉——像不像你脑子里那些翻来覆去的念头，终于有了落脚的力气？喝完它，你会发现答案不在别处，就在你停下来的地方。","flavor":"梅斯卡尔的烟熏是'想不清楚'的焦灼感，伏特加是'那就不想了'的空白。姜糖浆的暖意贯穿始终，像一束光从杯子底部打上来——让那些悬浮的尘埃，终于有了落下时的方向。","recipe":"梅斯卡尔25ml+伏特加15ml+鲜榨菠萝汁20ml+鲜榨青瓜汁15ml+青柠汁10ml+姜糖浆10ml+接骨木花糖浆5ml+黑胡椒微量，岩石杯加碎冰","color":"浑浊的淡琥珀色，细密悬浮物在光线下缓缓下沉","backstory":"有个考了三年研的男孩，第三年出分那晚，他进来没说分数，只是盯着杯子发呆。我把这杯推过去。他看着那些悬浮物慢慢沉底，忽然开口：'老柯，我好像一直觉得答案在天上，要跳起来够。但你看这些渣滓——它们不跳，它们只是等。'"},
        {"name":"壁炉晨光","name_en":"Firelight Dawn","emotions":["疲惫","清醒"],"recipe_modules":["clear_balance","bitter_focus","spark_restart"],"flavor_profile":"深沉暖调，微带清醒草本","color_profile":"琥珀色带金色光泽","face_state":"focused","action_sequence":"make_cold_start","serve_line":"这杯叫《壁炉晨光》。你看它——琥珀色的酒体里，透着一层薄薄的金色光晕，像不像冬夜壁炉的火还没灭，但窗帘缝里已经漏进了早晨的光？喝完它，你会带着身体的暖意，慢慢睁开眼睛。","flavor":"威士忌的深沉是壁炉里将熄未熄的炭火，清酒的清冽是推窗时涌进来的冷空气。柚子皮的香是那种'睁开眼，还没起床，先闻到厨房里有人煮茶'的细微幸福。","recipe":"日本威士忌25ml+清酒20ml+冷泡绿茶35ml+柚子皮1片+柠檬汁5ml+蜂蜜糖浆10ml，古典杯加大冰球","color":"琥珀色带金色光泽，像晨光穿过威士忌","backstory":"有个总上夜班的医生，下班时天刚亮。她每次进来都带着一身消毒水的味道，说：'老柯，我那个世界是惨白的，我想看看有颜色的天亮。'我给她这杯。她捧着杯子看向窗外，说：'这杯酒的颜色，跟我办公室窗外那个冬天的日出一样。'"},
        {"name":"跳跳糖协议","name_en":"Pop Protocol","emotions":["兴奋","犹豫"],"recipe_modules":["bright_bubble","spark_restart","clear_balance"],"flavor_profile":"烟熏果香，气泡爆炸感","color_profile":"下层深琥珀微浑，上层明亮橘粉","face_state":"happy","action_sequence":"make_spark_restart","serve_line":"这杯叫《跳跳糖协议》。你看它杯底那些持续往上窜的小气泡——像不像你心里那个'管他呢'的声音，正在替你按下确认键？别犹豫，喝下去的时候，你的脚已经离地了。","flavor":"金酒的植物清香是'先冷静分析一下'，但梅斯卡尔的烟熏会立刻盖上来——那是'分析够了'。起泡酒不是装饰——它是跳进泳池时，溅起来的第一朵水花。","recipe":"金酒20ml+梅斯卡尔20ml+鲜榨血橙汁25ml+鲜榨菠萝汁15ml+青柠汁5ml+姜糖浆10ml+蜂蜜糖浆5ml+黑胡椒微量+起泡酒30ml漂浮，蝶形香槟杯","color":"下层深琥珀带微浑，上层明亮橘粉气泡","backstory":"有个一直想辞职旅行但不敢的姑娘，来店里画路线图画了两个月。有一天她把画满地图的笔记本往吧台一拍：'老柯，我决定了。'我给她这杯。她一口喝完，杯底朝天：'你看，喝完了，没得犹豫了。'"},
        {"name":"离线模式","name_en":"Offline Mode","emotions":["难过","焦虑","疲惫"],"recipe_modules":["soft_comfort","blue_calm","clear_balance"],"flavor_profile":"极淡，微凉，几乎无味","color_profile":"极淡灰白色近乎透明","face_state":"gentle","action_sequence":"serve_only","serve_line":"这杯叫《离线模式》。它没有任何鲜明的颜色、强烈的味道或张扬的气泡。它淡得像一杯放凉了的水。但喝下去之后——你会感觉到，那些后台乱跑的进程，终于被你亲手结束了。","flavor":"我把所有的糖、酸、苦都调到了最低，只留下微弱的植物气息——白朗姆的柔、伏特加的净、洋甘菊的草、青瓜的凉。它们在口腔里几乎不打架，也不争抢，只是安安静静地流过去。","recipe":"白朗姆15ml+伏特加15ml+温牛奶15ml+冷泡洋甘菊茶25ml+鲜榨青瓜汁15ml+蜂蜜糖浆3ml，岩石杯加碎冰","color":"极淡的灰白色，近乎透明，像一杯被稀释了的薄雾","backstory":"有个做心理咨询师的客人，自己也有焦虑症。她说：'老柯，我今天听了九个病人的故事，每个都把我的能量吸走一点。我现在像一块电量1%的手机。'我给她这杯。她喝了四十分钟，走的时候说：'我没关机，但我把所有的通知都关了。'"},
    ]
}


DRINK_METADATA_FIELDS = (
    "name",
    "name_en",
    "recipe_modules",
    "flavor_profile",
    "color_profile",
    "face_state",
    "action_sequence",
    "kernel",
    "emotional_value",
    "serve_line",
    "flavor",
    "backstory",
    "recipe",
    "color",
    "emotions",
)


def _build_single_menu_lines() -> list[str]:
    lines = []
    for emotion, drink in DRINK_MENU["单品"].items():
        lines.append(
            f"  {emotion} -> 「{drink['name']}」{drink['name_en']}: "
            f"{drink['flavor_profile']} | face={drink['face_state']} "
            f"action={drink['action_sequence']} | {drink['serve_line']}"
        )
    return lines


def _build_blend_menu_lines() -> list[str]:
    lines = []
    for drink in DRINK_MENU["混合"]:
        emotion_text = " x ".join(drink["emotions"])
        lines.append(
            f"  {emotion_text} -> 「{drink['name']}」{drink['name_en']}: "
            f"{drink['flavor_profile']} | face={drink['face_state']} "
            f"action={drink['action_sequence']} | {drink['serve_line']}"
        )
    return lines


MENU_LINES_SINGLE = _build_single_menu_lines()
MENU_LINES_BLEND = _build_blend_menu_lines()


def get_drink_info(drink_name: str) -> Optional[dict]:
    for drink in DRINK_MENU["单品"].values():
        if drink["name"] == drink_name:
            return drink
    for drink in DRINK_MENU["混合"]:
        if drink["name"] == drink_name:
            return drink
    return None


def build_drink_metadata(drink_name: str) -> Optional[dict]:
    drink = get_drink_info(drink_name)
    if drink is None:
        return None
    return {field: drink[field] for field in DRINK_METADATA_FIELDS if field in drink}


def enrich_result_with_drink_metadata(data: dict) -> dict:
    if data["turn_type"] in CHAT_ONLY_TURN_TYPES or data["drink_name"] == NO_FORMAL_DRINK_NAME:
        data["drink_metadata"] = None
        return data

    data["drink_metadata"] = build_drink_metadata(data["drink_name"])
    return data


ASR_MODEL = (
    AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        punc_model="ct-punc-c",
    )
    if AutoModel is not None
    else None
)

client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
)

MODEL = os.environ["LLM_MODEL"]

ALLOWED_ACTION_SEQUENCES = {
    "make_cold_start",
    "make_soft_comfort",
    "make_spark_restart",
    "serve_only",
    "gesture_thinking",
    "gesture_thumb_up",
    "gesture_shrug",
}

ALLOWED_FACE_STATES = {
    "idle",
    "listening",
    "thinking",
    "focused",
    "happy",
    "gentle",
    "awkward",
    "mysterious",
}

ALLOWED_RECIPE_MODULES = {
    "blue_calm",
    "clear_balance",
    "spark_restart",
    "soft_comfort",
    "bright_bubble",
    "bitter_focus",
}

RECOMMENDATION_TRIGGERS = (
    "推荐",
    "调一杯",
    "来一杯",
    "喝什么",
    "适合喝",
    "做一杯",
    "按你说的",
    "你做主",
)

SAFETY_TRIGGERS = (
    "未成年",
    "喝醉",
    "开车",
    "酒驾",
    "吃药",
    "失眠怎么治",
    "抑郁诊断",
    "自杀",
    "伤害别人",
)

CHAT_ONLY_TURN_TYPES = {
    "bar_chat",
    "safety",
}


def route_turn_type(user_text: str) -> str:
    text = user_text.strip()

    if any(trigger in text for trigger in SAFETY_TRIGGERS):
        return "safety"

    if any(trigger in text for trigger in RECOMMENDATION_TRIGGERS):
        return "recommendation"

    return "bar_chat"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def normalize_username(username: Optional[str]) -> Optional[str]:
    if username is None:
        return None
    cleaned = username.strip()
    return cleaned or None


def require_username(username: Optional[str]) -> str:
    cleaned = normalize_username(username)
    if cleaned is None:
        raise ValueError("username must not be empty")
    return cleaned


def profile_path_for_username(username: str) -> Path:
    digest = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return PROFILE_DIR / f"{digest}.json"


def default_user_profile(username: str) -> dict:
    timestamp = now_iso()
    return {
        "username": username,
        "created_at": timestamp,
        "updated_at": timestamp,
        "stable_profile": {
            "taste_preferences": [],
            "emotion_patterns": [],
            "drink_history": [],
            "conversation_style": [],
            "avoidances": [],
        },
        "session_summaries": [],
    }


def load_user_profile(username: str) -> dict:
    username = require_username(username)
    path = profile_path_for_username(username)
    if not path.exists():
        return default_user_profile(username)
    with open(path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    profile.setdefault("username", username)
    profile.setdefault("created_at", now_iso())
    profile.setdefault("updated_at", now_iso())
    profile.setdefault("stable_profile", {})
    profile.setdefault("session_summaries", [])
    for key in PROFILE_LIST_KEYS:
        profile["stable_profile"].setdefault(key, [])
    return profile


def save_user_profile(username: str, profile: dict) -> dict:
    username = require_username(username)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile["username"] = username
    profile["updated_at"] = now_iso()
    profile.setdefault("created_at", profile["updated_at"])
    path = profile_path_for_username(username)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return profile


def append_unique(target: list, values) -> None:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if cleaned and cleaned not in target:
            target.append(cleaned)


def compact_profile_context(username: Optional[str]) -> dict:
    username = normalize_username(username)
    if username is None:
        return {
            "mode": "anonymous",
            "message": "用户未登录，不使用长期 profile。",
        }
    profile = load_user_profile(username)
    return {
        "mode": "logged_in",
        "username": username,
        "stable_profile": profile["stable_profile"],
        "recent_session_summaries": profile["session_summaries"][-5:],
    }


def merge_session_summary_into_profile(profile: dict, summary: dict) -> dict:
    stable = profile.setdefault("stable_profile", {})
    for key in PROFILE_LIST_KEYS:
        stable.setdefault(key, [])

    append_unique(stable["taste_preferences"], summary.get("taste_preferences", []))
    append_unique(stable["emotion_patterns"], summary.get("emotional_pattern", ""))
    append_unique(stable["drink_history"], summary.get("drink_name", ""))
    append_unique(stable["conversation_style"], summary.get("conversation_style", []))
    append_unique(stable["avoidances"], summary.get("avoidances", []))

    profile.setdefault("session_summaries", []).append(summary)
    profile["session_summaries"] = profile["session_summaries"][-20:]
    return profile


def get_recent_history() -> list[dict]:
    return conversation_history[-MAX_HISTORY_ITEMS:]


def get_conversation_state() -> dict:
    return {
        "summary": conversation_summary,
        "history": list(conversation_history),
        "username": current_username,
    }


def reset_conversation_state() -> None:
    global conversation_summary, emotion_history
    conversation_history.clear()
    conversation_summary = ""
    emotion_history.clear()
    logger.info("会话状态已重置")


def update_conversation_state(data: dict) -> None:
    global conversation_summary

    item = {
        "turn_type": data["turn_type"],
        "user_text": data["user_text"],
        "emotion_label": data["emotion_label"],
        "need_summary": data["need_summary"],
        "face_state": data["face_state"],
        "action_sequence": data["action_sequence"],
        "bartender_line": data["bartender_line"],
    }

    if data["turn_type"] == "recommendation":
        item["drink_name"] = data["drink_name"]
        item["recipe_modules"] = data["recipe_modules"]

    conversation_history.append(item)
    emotion_history.append(data["emotion_label"])
    if len(emotion_history) > MAX_EMOTION_HISTORY:
        emotion_history.pop(0)

    if len(conversation_history) > MAX_HISTORY_ITEMS:
        del conversation_history[:-MAX_HISTORY_ITEMS]

    summary_piece = (
        f"第{len(conversation_history)}轮："
        f"{data['turn_type']}；"
        f"用户情绪={data['emotion_label']}；"
        f"需求={data['need_summary']}"
    )
    conversation_summary = (
        f"{conversation_summary}\n{summary_piece}".strip()
        if conversation_summary
        else summary_piece
    )

    if len(conversation_summary) > MAX_SUMMARY_CHARS:
        conversation_summary = conversation_summary[-MAX_SUMMARY_CHARS:]


def transcribe_audio(wav_path: Path) -> str:
    if ASR_MODEL is None:
        raise RuntimeError("asr_unavailable")

    logger.info(f"开始语音识别: {wav_path}")
    result = ASR_MODEL.generate(input=str(wav_path))
    text = result[0].get("text", "").strip()
    if not text or len(text) < 2:
        logger.warning(f"静默或过短语音: '{text}'")
        raise RuntimeError("silence_detected")
    logger.info(f"识别结果: {text}")
    return text


def extract_json(content: str) -> dict:
    content = content.strip()

    if content.startswith("```json"):
        content = content.removeprefix("```json").strip()
    if content.startswith("```"):
        content = content.removeprefix("```").strip()
    if content.endswith("```"):
        content = content.removesuffix("```").strip()

    return json.loads(content)


def analyze_text(user_text: str, turn_type: str, profile_context: Optional[dict] = None) -> dict:
    with open(PROMPT_LIBRARY_PATH, "r", encoding="utf-8") as f:
        prompt_library = json.load(f)
    recent_history = get_recent_history()
    profile_context = profile_context or compact_profile_context(None)
    single_menu = "\n".join(MENU_LINES_SINGLE)
    blend_menu = "\n".join(MENU_LINES_BLEND)

    # Build emotion trend
    emotion_trend = ""
    if len(emotion_history) >= 2:
        trend_labels = emotion_history[-3:] if len(emotion_history) >= 3 else emotion_history
        emotion_trend = f"\n用户情绪变化趋势（最近{len(trend_labels)}轮）：{' → '.join(trend_labels)}。请根据趋势判断用户情绪走向，据此调整你的回应。"

    prompt = f"""
你是 EmoTender 情绪酒保的 AI 中控分析模块。
你的角色是老柯 / Alex Cole，38岁，12年调酒师。
你的信念是：酒是情绪的缓冲剂，不是解决方案。
你的表达必须低沉、松弛、直球、不说废话。

你必须只输出一个合法 JSON 对象。
不要输出 Markdown。
不要输出解释。
不要输出代码块。
不要在 JSON 前后添加任何文字。

本轮模式：
{turn_type}

用户原话：
{user_text}

会话摘要：
{conversation_summary or "暂无"}
{emotion_trend}

最近对话历史：
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

用户长期 profile：
{json.dumps(profile_context, ensure_ascii=False, indent=2)}

这是 EmoTender 的 prompt 库，包含情绪维度、混合规则、隐藏饮品、配方模块、表情状态和动作序列：
{json.dumps(prompt_library, ensure_ascii=False, indent=2)}

这是 EmoTender 当前可用于正式推荐和牛皮纸小票的后端饮品菜单：
单品：
{single_menu}

混合情绪特调：
{blend_menu}

必须输出这些字段：
schema_version, turn_type, user_text, emotion_label, emotion_blend, complex_emotion,
need_summary, drink_name, recipe_modules, flavor_profile, color_profile,
face_state, bartender_line, action_sequence, feedback_prompt。

字段类型要求：
- schema_version 必须是字符串，例如 "1.0"
- turn_type 必须是字符串，例如 "initial_order"
- user_text 必须是字符串
- emotion_label 必须是字符串
- complex_emotion 必须是字符串
- need_summary 必须是字符串
- drink_name 必须是字符串
- recipe_modules 必须是字符串数组，例如 ["blue_calm", "clear_balance"]
- flavor_profile 必须是字符串
- color_profile 必须是字符串
- face_state 必须是单个字符串，例如 "focused"，不能是数组
- bartender_line 必须是字符串
- action_sequence 必须是单个字符串，例如 "make_cold_start"，不能是数组
- feedback_prompt 必须是字符串
- emotion_blend 必须是数组，每一项包含 emotion 和 weight，例如 [{{"emotion": "难过", "weight": 0.7}}, {{"emotion": "焦虑", "weight": 0.3}}]
- emotion_blend 的 weight 总和必须接近 1.0

模式规则：
- 如果 turn_type 是 "bar_chat"，这一轮是闲聊。你仍然必须输出完整 JSON，用于驱动机器人表情、动作和台词，但不要正式推荐饮品。
- 如果 turn_type 是 "bar_chat"，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，flavor_profile 使用 "无正式推荐"，color_profile 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，face_state 必须体现用户情绪，action_sequence 优先使用 "gesture_thinking"、"gesture_shrug"、"serve_only"。
- 如果 turn_type 是 "recommendation"，必须正式推荐当前后端饮品菜单中的饮品，drink_name 必须精确使用菜单里的中文饮品名，recipe_modules 不能为空。
- 如果推荐时判断为单一情绪，优先使用菜单“单品”；如果判断为两种或三种主要情绪，可以使用菜单“混合情绪特调”。
- 推荐饮品时，bartender_line 优先使用或贴近菜单中对应饮品的 serve_line。
- 如果 turn_type 是 "safety"，不要推荐酒精饮品，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，action_sequence 优先使用 "serve_only"。
- 如果用户长期 profile 中有口味偏好、历史饮品或情绪模式，请把它作为个性化依据，但不要在台词里暴露“我保存了你的资料”这类后台措辞。
- 每轮最多问一个问题。
- 不要使用这些词：亲、哦、呢、呀、哈、啦、咱、呗。
- 不要做医学诊断、法律建议、股票建议。
"""

    # LLM 调用 + 自动重试（最多2次，指数退避）
    max_retries = 2
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"LLM 调用 (尝试 {attempt+1}/{max_retries+1})")
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "你只输出合法 JSON 对象。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                timeout=30,
            )
            llm_content = response.choices[0].message.content
            return extract_json(llm_content)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning(f"LLM 调用失败 (尝试 {attempt+1}), {wait}s 后重试: {exc}")
                time.sleep(wait)
            else:
                logger.error(f"LLM 调用全部失败: {exc}")
    raise last_error


def normalize_result(data: dict) -> dict:
    if isinstance(data.get("action_sequence"), list):
        if len(data["action_sequence"]) == 1:
            data["action_sequence"] = data["action_sequence"][0]
        else:
            raise TypeError(f"action_sequence must be a string, got list: {data['action_sequence']}")

    if isinstance(data.get("face_state"), list):
        if len(data["face_state"]) == 1:
            data["face_state"] = data["face_state"][0]
        else:
            raise TypeError(f"face_state must be a string, got list: {data['face_state']}")

    return data


def validate_result(data: dict) -> None:
    required_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_label",
        "complex_emotion",
        "need_summary",
        "drink_name",
        "recipe_modules",
        "flavor_profile",
        "color_profile",
        "face_state",
        "bartender_line",
        "action_sequence",
        "feedback_prompt",
        "emotion_blend",
    ]

    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing field: {field}")

    if not isinstance(data["emotion_blend"], list):
        raise TypeError(f"emotion_blend must be a list, got {type(data['emotion_blend']).__name__}: {data['emotion_blend']}")

    if not data["emotion_blend"]:
        raise ValueError("emotion_blend must not be empty")

    total_weight = 0.0
    for item in data["emotion_blend"]:
        if not isinstance(item, dict):
            raise TypeError(f"emotion_blend item must be an object, got {type(item).__name__}: {item}")

        if "emotion" not in item:
            raise ValueError(f"emotion_blend item missing emotion: {item}")

        if "weight" not in item:
            raise ValueError(f"emotion_blend item missing weight: {item}")

        if not isinstance(item["emotion"], str):
            raise TypeError(f"emotion_blend emotion must be a string: {item}")

        if not isinstance(item["weight"], (int, float)):
            raise TypeError(f"emotion_blend weight must be a number: {item}")

        if item["weight"] < 0 or item["weight"] > 1:
            raise ValueError(f"emotion_blend weight must be between 0 and 1: {item}")

        total_weight += item["weight"]

    if abs(total_weight - 1.0) > 0.05:
        raise ValueError(f"emotion_blend weights must sum to 1.0, got {total_weight}")

    string_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_label",
        "complex_emotion",
        "need_summary",
        "drink_name",
        "flavor_profile",
        "color_profile",
        "face_state",
        "bartender_line",
        "action_sequence",
        "feedback_prompt",
    ]

    for field in string_fields:
        if not isinstance(data[field], str):
            raise TypeError(f"{field} must be a string, got {type(data[field]).__name__}: {data[field]}")
        if not data[field].strip():
            raise ValueError(f"{field} must not be empty")

    if not isinstance(data["recipe_modules"], list):
        raise TypeError(f"recipe_modules must be a list, got {type(data['recipe_modules']).__name__}: {data['recipe_modules']}")

    if not data["recipe_modules"] and data["turn_type"] not in CHAT_ONLY_TURN_TYPES:
        raise ValueError("recipe_modules must not be empty")

    for module in data["recipe_modules"]:
        if not isinstance(module, str):
            raise TypeError(f"recipe_modules item must be a string, got {type(module).__name__}: {module}")
        if module not in ALLOWED_RECIPE_MODULES:
            raise ValueError(f"Unknown recipe module: {module}")

    if data["face_state"] not in ALLOWED_FACE_STATES:
        raise ValueError(f"Unknown face_state: {data['face_state']}")

    if data["action_sequence"] not in ALLOWED_ACTION_SEQUENCES:
        raise ValueError(f"Unknown action_sequence: {data['action_sequence']}")


def fallback_result(user_text: str, turn_type: str = "recommendation") -> dict:
    """内置熔断兜底：LLM 链路断开或输出非法 JSON 时，返回完整 Schema v1.0 安全字典。
    
    闲聊/安全模式 -> 点亮【疲惫】gentle 表情，不推荐饮品。
    推荐模式     -> 点亮【清醒】focused 表情，推荐标志性"冷启动"。
    """
    if turn_type in CHAT_ONLY_TURN_TYPES:
        return {
            "schema_version": "1.0",
            "turn_type": turn_type,
            "user_text": user_text,
            "emotion_label": "疲惫",
            "emotion_blend": [
                {"emotion": "疲惫", "weight": 1.0}
            ],
            "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
            "need_summary": "系统自检中，需要被接住而不是立刻推荐饮品。",
            "drink_name": NO_FORMAL_DRINK_NAME,
            "recipe_modules": [],
            "flavor_profile": NO_FORMAL_DRINK_NAME,
            "color_profile": NO_FORMAL_DRINK_NAME,
            "face_state": "gentle",
            "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，你先缓一缓，我马上回来。",
            "action_sequence": "gesture_thinking" if turn_type == "bar_chat" else "serve_only",
            "feedback_prompt": "你愿意的话，可以再说一点。",
        }

    return {
        "schema_version": "1.0",
        "turn_type": "recommendation",
        "user_text": user_text,
        "emotion_label": "清醒",
        "emotion_blend": [
            {"emotion": "清醒", "weight": 1.0}
        ],
        "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
        "need_summary": "系统自检，需要一杯清爽低甜的特调冷启动。",
        "drink_name": "冷启动",
        "recipe_modules": [
            "clear_balance",
            "bitter_focus",
        ],
        "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
        "color_profile": "透明偏冷调，带一点淡青色",
        "face_state": "focused",
        "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，我先为你推荐一杯标志性的'冷启动'，让我们重新连接。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完感觉清醒一点了吗？",
    }


def build_robot_reply_text(control_json: dict) -> str:
    bartender_line = control_json["bartender_line"].strip()
    feedback_prompt = control_json["feedback_prompt"].strip()

    if control_json["turn_type"] == "bar_chat" and feedback_prompt:
        return f"{bartender_line}\n{feedback_prompt}"

    return bartender_line


def process_user_text(user_text: str, username: Optional[str] = None) -> dict:
    global current_username

    user_text = user_text.strip()
    if not user_text:
        raise ValueError("user_text must not be empty")

    username = normalize_username(username) or current_username
    current_username = username
    profile_context = compact_profile_context(username)
    turn_type = route_turn_type(user_text)
    used_fallback = False
    llm_error = None

    try:
        result = analyze_text(user_text, turn_type, profile_context)
        result = normalize_result(result)
        result["turn_type"] = turn_type
        result["user_text"] = user_text
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)
    except Exception as exc:
        used_fallback = True
        llm_error = str(exc)
        logger.warning(f"LLM/NLP 链路异常，使用熔断兜底: {exc}")
        result = fallback_result(user_text, turn_type)
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)

    update_conversation_state(result)

    return {
        "ok": True,
        "username": username,
        "user_text": user_text,
        "turn_type": turn_type,
        "control_json": result,
        "robot_reply_text": build_robot_reply_text(result),
        "profile_context": profile_context,
        "conversation_state": get_conversation_state(),
        "used_fallback": used_fallback,
        "llm_error": llm_error,
    }


def load_profile_summary_prompt() -> str:
    if PROFILE_SUMMARY_PROMPT_PATH.exists():
        return PROFILE_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8")
    return (
        "你是 EmoTender 的用户记忆整理模块。根据本次对话输出合法 JSON，"
        "字段包含 date, username, session_emotion, drink_name, drink_result, "
        "event_summary, taste_preferences, emotional_pattern, future_hint。"
    )


def summarize_session_for_profile(username: str, profile: dict, state: dict) -> dict:
    prompt = f"""
{load_profile_summary_prompt()}

用户名：
{username}

已有 profile：
{json.dumps(profile, ensure_ascii=False, indent=2)}

本次会话：
{json.dumps(state, ensure_ascii=False, indent=2)}
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你只输出合法 JSON 对象。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        timeout=30,
    )
    summary = extract_json(response.choices[0].message.content)
    summary["username"] = username
    summary.setdefault("date", datetime.now().date().isoformat())
    summary.setdefault("drink_name", NO_FORMAL_DRINK_NAME)
    summary.setdefault("drink_result", "未记录")
    summary.setdefault("event_summary", "本次会话没有形成明确事件摘要。")
    summary.setdefault("taste_preferences", [])
    summary.setdefault("emotional_pattern", "")
    summary.setdefault("future_hint", "")
    return summary


def run_pipeline() -> dict:
    try:
        user_text = transcribe_audio(AUDIO_PATH)
    except RuntimeError as exc:
        if "silence_detected" in str(exc):
            logger.info("检测到静默录音，返回提示")
            silence_result = {
                "schema_version": "1.0",
                "turn_type": "bar_chat",
                "user_text": "",
                "emotion_label": "清醒",
                "emotion_blend": [{"emotion": "清醒", "weight": 1.0}],
                "complex_emotion": "未检测到有效语音。",
                "need_summary": "等待用户说话。",
                "drink_name": "无正式推荐",
                "recipe_modules": [],
                "flavor_profile": "无正式推荐",
                "color_profile": "无正式推荐",
                "face_state": "thinking",
                "bartender_line": "嗯？我没太听清，能再说一遍吗？",
                "action_sequence": "gesture_thinking",
                "feedback_prompt": "",
                "drink_metadata": None,
            }
            update_conversation_state(silence_result)
            return {
                "ok": True,
                "audio_path": str(AUDIO_PATH),
                "user_text": "",
                "turn_type": "bar_chat",
                "control_json": silence_result,
                "robot_reply_text": silence_result["bartender_line"],
                "conversation_state": get_conversation_state(),
                "used_fallback": False,
                "llm_error": None,
            }
        raise

    result = process_user_text(user_text)
    result["audio_path"] = str(AUDIO_PATH)
    return result


@app.get("/api/status")
def status():
    return {
        "recording": recording_process is not None,
        "audio_path": str(AUDIO_PATH),
        "last_result": last_result,
        "conversation_state": get_conversation_state(),
    }


@app.post("/api/text/analyze")
def analyze_text_api(payload: TextAnalyzeRequest):
    try:
        return process_user_text(payload.user_text, payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/user/login")
def login_user_api(payload: UserLoginRequest):
    global current_username
    try:
        username = require_username(payload.username)
        profile = load_user_profile(username)
        save_user_profile(username, profile)
        current_username = username
        reset_conversation_state()
        return {
            "ok": True,
            "username": username,
            "profile": profile,
            "message": "Login complete",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/user/logout")
def logout_user_api(payload: UserLogoutRequest):
    global current_username
    try:
        username = normalize_username(payload.username) or current_username
        username = require_username(username)
        profile = load_user_profile(username)
        state = get_conversation_state()
        saved_summary = None
        if state["history"]:
            saved_summary = summarize_session_for_profile(username, profile, state)
            profile = merge_session_summary_into_profile(profile, saved_summary)
            save_user_profile(username, profile)
        reset_conversation_state()
        current_username = None
        return {
            "ok": True,
            "username": username,
            "saved_summary": saved_summary,
            "profile": profile,
            "message": "Logout complete",
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/user/profile")
def get_user_profile_api(username: str):
    try:
        username = require_username(username)
        return {
            "ok": True,
            "username": username,
            "profile": load_user_profile(username),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/voice/start")
def start_recording():
    global recording_process

    if recording_process is not None:
        # Auto-stop existing recording before starting a new one
        try:
            os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
            recording_process.communicate(timeout=2)
        except Exception:
            pass
        finally:
            recording_process = None

    if AUDIO_PATH.exists():
        AUDIO_PATH.unlink()

    import platform
    if platform.system() == "Darwin":
        command = [
            "ffmpeg",
            "-f", "avfoundation",
            "-i", ":0",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            "-t", "30",
            "-y",
            str(AUDIO_PATH),
        ]
    else:
        command = [
            "arecord",
            "-D", "default",
            "-f", "S16_LE",
            "-r", "16000",
            "-d", "30",
            "-c", "1",
            str(AUDIO_PATH),
        ]

    recording_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )

    time.sleep(0.5)

    if recording_process.poll() is not None:
        _, stderr = recording_process.communicate()
        recording_process = None
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start recording: {stderr.decode(errors='ignore')}",
        )

    logger.info("录音已启动 (30s 超时)")
    return {
        "ok": True,
        "state": "listening",
        "max_duration": 30,
        "message": "Recording started (30s max)",
    }


@app.post("/api/voice/stop")
def stop_recording():
    global recording_process
    global last_result

    if recording_process is None:
        raise HTTPException(status_code=400, detail="Recording is not running")

    os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
    _, stderr = recording_process.communicate(timeout=5)
    recording_process = None

    if not AUDIO_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Recording file was not created: {stderr.decode(errors='ignore')}",
        )

    if AUDIO_PATH.stat().st_size == 0:
        raise HTTPException(status_code=500, detail="Recording file is empty")

    try:
        logger.info("录音已停止，开始分析管线")
        last_result = run_pipeline()
        logger.info(f"分析完成: emotion={last_result.get('control_json',{}).get('emotion_label','?')}")
        return last_result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/reset")
def reset():
    global recording_process
    global last_result

    if recording_process is not None:
        os.killpg(os.getpgid(recording_process.pid), signal.SIGINT)
        recording_process.communicate(timeout=5)
        recording_process = None

    last_result = None
    reset_conversation_state()

    return {
        "ok": True,
        "message": "Reset complete",
    }


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Error: static/index.html not found</h1>",
            status_code=500,
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
