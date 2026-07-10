#!/usr/bin/env python3
"""
EmoTender Backend - 情绪酒保 AI 服务
支持语音转文字 + 情绪识别 + 饮品推荐 + 机器人控制指令
格式与 emotender_release 兼容
"""
import base64
import io
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("emotender")

app = FastAPI(title="EmoTender Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== LLM Client ====================
USE_MOCK = os.environ.get("LLM_API_KEY", "").strip() == ""
if USE_MOCK:
    logger.warning("未配置 LLM_API_KEY，使用内置模拟模式")
    client = None
    MODEL = "mock"
else:
    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
    )
    MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    logger.info(f"LLM: {MODEL} @ {os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')}")

# ==================== Conversation State ====================
conversation_history: list[dict] = []
conversation_summary = ""
emotion_history: list[str] = []
MAX_HISTORY = 8
MAX_SUMMARY_CHARS = 1200
MAX_EMOTION_HISTORY = 5
NO_DRINK = "无正式推荐"

# ==================== Allowed Values (matching reference) ====================
ALLOWED_FACE_STATES = {"idle", "listening", "thinking", "focused", "happy", "gentle", "awkward", "mysterious"}
ALLOWED_ACTION_SEQUENCES = {
    "make_cold_start", "make_soft_comfort", "make_spark_restart",
    "serve_only", "gesture_thinking", "gesture_thumb_up", "gesture_shrug",
}
ALLOWED_RECIPE_MODULES = {
    "blue_calm", "clear_balance", "spark_restart",
    "soft_comfort", "bright_bubble", "bitter_focus",
}

# ==================== Drink Menu (from 菜单.docx) ====================
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

def _build_single_menu_lines() -> list[str]:
    lines = []
    for emotion, d in DRINK_MENU["单品"].items():
        lines.append(f"  {emotion} →「{d['name']}」{d['name_en']}: {d['flavor_profile']} | face={d['face_state']} action={d['action_sequence']} | {d['serve_line'][:60]}...")
    return lines

def _build_blend_menu_lines() -> list[str]:
    lines = []
    for d in DRINK_MENU["混合"]:
        emo_str = " × ".join(d["emotions"])
        lines.append(f"  {emo_str} →「{d['name']}」{d['name_en']}: {d['flavor_profile']} | face={d['face_state']} action={d['action_sequence']} | {d['serve_line'][:60]}...")
    return lines

MENU_LINES_SINGLE = _build_single_menu_lines()
MENU_LINES_BLEND = _build_blend_menu_lines()

def get_drink_info(drink_name: str) -> Optional[dict]:
    for d in DRINK_MENU["单品"].values():
        if d["name"] == drink_name:
            return d
    for d in DRINK_MENU["混合"]:
        if d["name"] == drink_name:
            return d
    return None


# ==================== Prompt ====================
def build_system_prompt() -> str:
    single_menu = "\n".join(MENU_LINES_SINGLE)
    blend_menu = "\n".join(MENU_LINES_BLEND)

    return f"""你是情绪酒吧 EmoTender 的酒保"老柯"。你倾听客人心声，判断情绪状态，从菜单推荐最合适的饮品。

## 你的性格
温柔、内敛、有故事但不多话。不直接问"怎么了"，而是通过倾听和调酒回应。每句话都有温度，像深夜炉火旁的低语。真诚自然，偶尔带诗意，绝不矫情。

## 饮品菜单

### 单品
{single_menu}

### 混合情绪特调
{blend_menu}

## 推荐规则
- 单一情绪→对应单品
- 两种情绪→对应混合特调
- 三种（难过+焦虑+疲惫）→「离线模式」
- 上酒时使用菜单原文 serve_line
- 纯聊天 turn_type="bar_chat"，不推荐饮品，drink_name="无正式推荐"

## 输出（纯JSON，不要markdown代码块）
{{
  "schema_version": "1.0",
  "turn_type": "bar_chat|recommendation|safety",
  "user_text": "用户原文",
  "emotion_label": "清醒|兴奋|难过|疲惫|焦虑|犹豫",
  "emotion_blend": [{{"emotion": "情绪名", "weight": 0.0-1.0}}],
  "complex_emotion": "对情绪混合的简短描述",
  "need_summary": "一句话概括用户需求",
  "drink_name": "饮品中文名（bar_chat时用'无正式推荐'）",
  "recipe_modules": ["clear_balance"],
  "flavor_profile": "风味描述（bar_chat时用'无正式推荐'）",
  "color_profile": "色泽描述（bar_chat时用'无正式推荐'）",
  "face_state": "focused|happy|gentle|thinking",
  "bartender_line": "你回复客人的话",
  "action_sequence": "make_cold_start|make_soft_comfort|make_spark_restart|serve_only|gesture_thinking|gesture_thumb_up|gesture_shrug",
  "feedback_prompt": "可选的简短追问（通常为空）"
}}

emotion_blend 的 weight 总和必须接近 1.0。
bar_chat 时 drink_name 和 recipe_modules/flavor_profile/color_profile 用 "无正式推荐"/[]。"""


def extract_json(content: str) -> dict:
    content = content.strip()
    match = re.search(r'\{[\s\S]*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError(f"Cannot extract JSON: {content[:300]}")


# ==================== Mock Responses ====================
MOCK_PATTERNS = [
    (r"推荐|来一杯|喝什么|调一杯|做一杯|菜单", {
        "emotion_label":"疲惫","emotion_blend":[{"emotion":"疲惫","weight":0.8},{"emotion":"清醒","weight":0.2}],
        "complex_emotion":"带着倦意的清醒","need_summary":"想要一杯喝的来放松",
        "drink_name":"灰度模式","recipe_modules":["clear_balance","bitter_focus"],
        "flavor_profile":"深沉、微苦、低甜、有草本余韵","color_profile":"淡金色，微光柔和",
        "face_state":"gentle","action_sequence":"make_cold_start",
        "bartender_line":"看你眼里带着倦意……来，这杯应该适合你。","feedback_prompt":"",
    }),
    (r"难过|伤心|哭|想哭|低落|失恋|分手", {
        "emotion_label":"难过","emotion_blend":[{"emotion":"难过","weight":0.9}],
        "complex_emotion":"深沉的悲伤","need_summary":"需要温柔的陪伴",
        "drink_name":"软着陆","recipe_modules":["soft_comfort","blue_calm","clear_balance"],
        "flavor_profile":"柔和、低酸、低刺激、有一点甜感","color_profile":"浅蓝紫色或淡粉色",
        "face_state":"gentle","action_sequence":"make_soft_comfort",
        "bartender_line":"没关系的……慢慢来，先让这杯陪你一会儿。","feedback_prompt":"",
    }),
    (r"开心|高兴|兴奋|庆祝|好消息|太棒|耶", {
        "emotion_label":"兴奋","emotion_blend":[{"emotion":"兴奋","weight":0.9}],
        "complex_emotion":"明亮的喜悦","need_summary":"值得庆祝的好心情",
        "drink_name":"气泡重启","recipe_modules":["bright_bubble","spark_restart","clear_balance"],
        "flavor_profile":"明亮、轻酸、气泡感明显","color_profile":"明亮浅黄色或淡青色",
        "face_state":"happy","action_sequence":"make_spark_restart",
        "bartender_line":"嘿嘿，看你眼睛都亮了！这杯必须安排上。","feedback_prompt":"",
    }),
    (r"焦虑|紧张|担心|害怕|压力|烦|焦躁", {
        "emotion_label":"焦虑","emotion_blend":[{"emotion":"焦虑","weight":0.85}],
        "complex_emotion":"紧绷的焦虑感","need_summary":"需要冷静下来",
        "drink_name":"断点续传","recipe_modules":["blue_calm","clear_balance"],
        "flavor_profile":"清凉、清脆、微甜回甘","color_profile":"淡绿色，清澈透明",
        "face_state":"focused","action_sequence":"make_soft_comfort",
        "bartender_line":"深呼吸……我在这里陪你。来，先喝一口这个。","feedback_prompt":"",
    }),
    (r"犹豫|纠结|选择|不知道怎么办|迷茫", {
        "emotion_label":"犹豫","emotion_blend":[{"emotion":"犹豫","weight":0.85}],
        "complex_emotion":"徘徊的犹豫","need_summary":"在做决定前需要片刻安静",
        "drink_name":"延时摄影","recipe_modules":["clear_balance","soft_comfort"],
        "flavor_profile":"烟熏辛辣开头，果甜收尾","color_profile":"琥珀色带轻微浑浊",
        "face_state":"thinking","action_sequence":"gesture_thinking",
        "bartender_line":"唔…不着急，答案不用今晚就找到。先喝杯东西，让它自己浮上来。","feedback_prompt":"",
    }),
    (r"累|困|疲惫|好累|没力气|筋疲力尽", {
        "emotion_label":"疲惫","emotion_blend":[{"emotion":"疲惫","weight":0.9}],
        "complex_emotion":"深深的疲倦","need_summary":"需要好好休息",
        "drink_name":"灰度模式","recipe_modules":["clear_balance","bitter_focus"],
        "flavor_profile":"深沉、微苦、低甜、有草本余韵","color_profile":"淡金色，微光柔和",
        "face_state":"gentle","action_sequence":"make_cold_start",
        "bartender_line":"呼……看你这样子，今天一定走了很长的路。坐下来，这杯是你的。","feedback_prompt":"",
    }),
]

BAR_CHAT_MOCKS = [
    {"emotion_label":"清醒","emotion_blend":[{"emotion":"清醒","weight":0.5}],"complex_emotion":"平静的日常","need_summary":"用户打招呼","face_state":"focused","action_sequence":"serve_only","bartender_line":"嗯，今晚店里很安静，适合慢慢喝一杯。","feedback_prompt":""},
    {"emotion_label":"清醒","emotion_blend":[{"emotion":"清醒","weight":0.5}],"complex_emotion":"想找人聊聊","need_summary":"用户闲聊","face_state":"gentle","action_sequence":"gesture_thinking","bartender_line":"想说什么都可以，吧台不赶时间。","feedback_prompt":""},
    {"emotion_label":"清醒","emotion_blend":[{"emotion":"清醒","weight":0.5}],"complex_emotion":"安静的陪伴","need_summary":"用户闲聊","face_state":"focused","action_sequence":"serve_only","bartender_line":"我在这里听了二十年故事了……你的呢？不急，慢慢来。","feedback_prompt":""},
    {"emotion_label":"清醒","emotion_blend":[{"emotion":"清醒","weight":0.5}],"complex_emotion":"需要安静","need_summary":"用户可能需要安静","face_state":"gentle","action_sequence":"serve_only","bartender_line":"有时候什么都不说，光是坐在这里，就已经是在照顾自己了。","feedback_prompt":""},
    {"emotion_label":"清醒","emotion_blend":[{"emotion":"清醒","weight":0.5}],"complex_emotion":"进店看看","need_summary":"用户进店","face_state":"focused","action_sequence":"serve_only","bartender_line":"（擦了擦杯子）今晚想喝点什么？还是……想说点什么？","feedback_prompt":""},
]

def get_mock_result(user_text: str) -> dict:
    import random
    for pattern, result in MOCK_PATTERNS:
        if re.search(pattern, user_text):
            r = dict(result)
            r["turn_type"] = "recommendation"
            return r
    r = dict(random.choice(BAR_CHAT_MOCKS))
    r["turn_type"] = "bar_chat"
    return r

def route_turn_type(user_text: str) -> str:
    text = user_text.strip()
    safety_kw = ("未成年","喝醉","开车","酒驾","吃药","失眠怎么治","自杀","伤害")
    if any(k in text for k in safety_kw):
        return "safety"
    rec_kw = ("推荐","调一杯","来一杯","喝什么","适合喝","做一杯","按你说的","你做主")
    if any(k in text for k in rec_kw):
        return "recommendation"
    return "bar_chat"


# ==================== State Management ====================
def update_state(data: dict) -> None:
    global conversation_summary
    item = {
        "turn_type": data.get("turn_type","bar_chat"),
        "user_text": data.get("user_text",""),
        "emotion_label": data.get("emotion_label","清醒"),
        "need_summary": data.get("need_summary",""),
        "face_state": data.get("face_state","focused"),
        "action_sequence": data.get("action_sequence","serve_only"),
        "bartender_line": data.get("bartender_line",""),
    }
    if data.get("turn_type") == "recommendation":
        item["drink_name"] = data.get("drink_name","")
        item["recipe_modules"] = data.get("recipe_modules",[])
    conversation_history.append(item)
    emotion_history.append(data.get("emotion_label","清醒"))
    if len(emotion_history) > MAX_EMOTION_HISTORY:
        emotion_history.pop(0)
    if len(conversation_history) > MAX_HISTORY:
        del conversation_history[:-MAX_HISTORY]
    summary_piece = f"第{len(conversation_history)}轮：{item['turn_type']}；情绪={item['emotion_label']}；需求={item['need_summary']}"
    conversation_summary = f"{conversation_summary}\n{summary_piece}".strip() if conversation_summary else summary_piece
    if len(conversation_summary) > MAX_SUMMARY_CHARS:
        conversation_summary = conversation_summary[-MAX_SUMMARY_CHARS:]

def get_state() -> dict:
    return {"summary": conversation_summary, "history": list(conversation_history)}

def reset_state() -> None:
    global conversation_summary, emotion_history
    conversation_history.clear()
    conversation_summary = ""
    emotion_history.clear()


# ==================== LLM Call ====================
def call_llm(user_text: str, turn_type: str) -> dict:
    if USE_MOCK:
        time.sleep(0.2)
        result = get_mock_result(user_text)
        result["turn_type"] = turn_type
        return result

    system_prompt = build_system_prompt()
    messages = [{"role": "system", "content": system_prompt}]

    # Build emotion trend
    emotion_trend = ""
    if len(emotion_history) >= 2:
        trend_labels = emotion_history[-3:] if len(emotion_history) >= 3 else emotion_history
        sep = " → "
        emotion_trend = f"用户情绪变化趋势（最近{len(trend_labels)}轮）：{sep.join(trend_labels)}。请根据趋势判断用户情绪走向，据此调整你的回应。"

    recent = conversation_history[-MAX_HISTORY:]
    recent_json = [{
        "turn_type": h.get("turn_type",""),
        "user_text": h.get("user_text",""),
        "emotion_label": h.get("emotion_label",""),
        "bartender_line": h.get("bartender_line",""),
    } for h in recent]

    user_message = f"""本轮模式：
{turn_type}

用户原话：
{user_text}

会话摘要：
{conversation_summary or "暂无"}{emotion_trend}

最近对话历史：
{json.dumps(recent_json, ensure_ascii=False, indent=2)}"""

    messages.append({"role": "user", "content": user_message})

    for attempt in range(3):
        try:
            logger.info(f"LLM调用 (尝试 {attempt+1}/3)")
            response = client.chat.completions.create(
                model=MODEL, messages=messages, temperature=0.7, max_tokens=1000,
            )
            content = response.choices[0].message.content
            logger.info(f"LLM回复: {content[:150]}...")
            return extract_json(content)
        except Exception as e:
            logger.warning(f"LLM尝试{attempt+1}失败: {e}")
            if attempt == 2:
                raise
            time.sleep(1 * (attempt + 1))
    raise RuntimeError("LLM调用失败")


def normalize_result(raw: dict, user_text: str, turn_type: str) -> dict:
    """Ensure all required fields exist with valid values."""
    result = {
        "schema_version": "1.0",
        "turn_type": turn_type,
        "user_text": user_text,
        "emotion_label": raw.get("emotion_label", "清醒"),
        "emotion_blend": raw.get("emotion_blend", [{"emotion": "清醒", "weight": 1.0}]),
        "complex_emotion": raw.get("complex_emotion", ""),
        "need_summary": raw.get("need_summary", ""),
        "drink_name": raw.get("drink_name", NO_DRINK),
        "recipe_modules": raw.get("recipe_modules", []),
        "flavor_profile": raw.get("flavor_profile", NO_DRINK),
        "color_profile": raw.get("color_profile", NO_DRINK),
        "face_state": raw.get("face_state", "focused"),
        "bartender_line": raw.get("bartender_line", "嗯，我在听。"),
        "action_sequence": raw.get("action_sequence", "serve_only"),
        "feedback_prompt": raw.get("feedback_prompt", ""),
    }

    # Normalize emotion_label
    known = {"清醒","兴奋","难过","疲惫","焦虑","犹豫"}
    if result["emotion_label"] not in known:
        for k in known:
            if k in str(result["emotion_label"]):
                result["emotion_label"] = k
                break
        else:
            result["emotion_label"] = "清醒"

    # Validate face_state
    if result["face_state"] not in ALLOWED_FACE_STATES:
        result["face_state"] = "focused"

    # Validate action_sequence
    if result["action_sequence"] not in ALLOWED_ACTION_SEQUENCES:
        result["action_sequence"] = "serve_only"

    # bar_chat: clear drink info
    if turn_type in ("bar_chat", "safety"):
        result["drink_name"] = NO_DRINK
        result["recipe_modules"] = []
        result["flavor_profile"] = NO_DRINK
        result["color_profile"] = NO_DRINK

    # Validate recipe_modules
    result["recipe_modules"] = [m for m in result["recipe_modules"] if m in ALLOWED_RECIPE_MODULES]

    return result


def build_robot_reply_text(control_json: dict) -> str:
    line = control_json["bartender_line"].strip()
    fb = control_json.get("feedback_prompt", "").strip()
    if control_json["turn_type"] == "bar_chat" and fb:
        return f"{line}\n{fb}"
    return line


# ==================== Voice Transcription ====================
def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe audio using OpenAI Whisper API, or fallback."""
    if USE_MOCK or client is None:
        logger.info("模拟模式：跳过语音识别")
        raise RuntimeError("mock_no_asr")

    logger.info(f"调用 Whisper 转写，音频大小: {len(audio_bytes)} bytes")
    try:
        # Create a file-like object
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="zh",
        )
        text = transcript.text.strip()
        logger.info(f"Whisper 结果: {text}")
        if not text or len(text) < 2:
            raise RuntimeError("silence_detected")
        return text
    except Exception as e:
        logger.error(f"语音识别失败: {e}")
        raise


# ==================== Silence / Fallback results ====================
def silence_result() -> dict:
    return {
        "schema_version": "1.0", "turn_type": "bar_chat",
        "user_text": "", "emotion_label": "清醒",
        "emotion_blend": [{"emotion": "清醒", "weight": 1.0}],
        "complex_emotion": "未检测到有效语音",
        "need_summary": "等待用户说话",
        "drink_name": NO_DRINK, "recipe_modules": [],
        "flavor_profile": NO_DRINK, "color_profile": NO_DRINK,
        "face_state": "thinking", "action_sequence": "gesture_thinking",
        "bartender_line": "嗯？我没太听清，能再说一遍吗？",
        "feedback_prompt": "",
    }


# ==================== API Endpoints ====================
@app.get("/")
async def root():
    return FileResponse("index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "mock_mode": USE_MOCK, "model": MODEL}


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/api/chat")
async def chat_text(req: ChatRequest):
    """Text-based chat (keyboard input)"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    user_text = req.message.strip()
    turn_type = route_turn_type(user_text)

    try:
        raw = call_llm(user_text, turn_type)
        result = normalize_result(raw, user_text, turn_type)
    except Exception as e:
        logger.error(f"处理失败: {e}")
        result = normalize_result(get_mock_result(user_text), user_text, turn_type)

    update_state(result)

    return {
        "ok": True,
        "user_text": user_text,
        "turn_type": turn_type,
        "control_json": result,
        "robot_reply_text": build_robot_reply_text(result),
        "conversation_state": get_state(),
        "used_fallback": False,
    }


@app.post("/api/voice/process")
async def voice_process(audio: UploadFile = File(...)):
    """Receive audio from tablet, transcribe, analyze, return control JSON."""
    logger.info(f"收到音频: {audio.filename}, content_type={audio.content_type}")

    audio_bytes = await audio.read()
    if not audio_bytes or len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="音频数据为空")

    # Transcribe
    try:
        user_text = transcribe_audio_bytes(audio_bytes, audio.filename or "audio.webm")
    except RuntimeError as e:
        if "silence_detected" in str(e) or "mock_no_asr" in str(e):
            logger.info("静默/模拟模式，返回提示")
            sil = silence_result()
            update_state(sil)
            return {
                "ok": True, "user_text": "", "turn_type": "bar_chat",
                "control_json": sil,
                "robot_reply_text": sil["bartender_line"],
                "conversation_state": get_state(),
                "used_fallback": False,
            }
        raise HTTPException(status_code=500, detail=f"语音识别失败: {e}")

    # Analyze
    turn_type = route_turn_type(user_text)
    used_fallback = False

    try:
        raw = call_llm(user_text, turn_type)
        result = normalize_result(raw, user_text, turn_type)
    except Exception as e:
        logger.warning(f"LLM失败，使用fallback: {e}")
        result = normalize_result(get_mock_result(user_text), user_text, turn_type)
        used_fallback = True

    update_state(result)

    return {
        "ok": True,
        "user_text": user_text,
        "turn_type": turn_type,
        "control_json": result,
        "robot_reply_text": build_robot_reply_text(result),
        "conversation_state": get_state(),
        "used_fallback": used_fallback,
    }


@app.post("/api/voice/start")
def voice_start():
    """Placeholder for client-side recording start."""
    return {"ok": True, "message": "Recording started (client-side)"}


@app.post("/api/voice/stop")
async def voice_stop():
    """Alias - client should use /api/voice/process with audio blob instead."""
    raise HTTPException(status_code=400, detail="请使用 /api/voice/process 上传音频")


@app.post("/api/reset")
def reset():
    reset_state()
    return {"ok": True, "message": "Reset complete"}


if __name__ == "__main__":
    import uvicorn
    logger.info("启动 EmoTender 后端...")
    uvicorn.run(app, host="0.0.0.0", port=8765)
