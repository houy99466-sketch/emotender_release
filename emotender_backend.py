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
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from emotender_emotion import (
    NRC_EMOTIONS,
    build_uev,
    build_ambient_plan,
    build_fallback_emotion_assessment,
    build_target_flavor_vector,
    derive_legacy_fields,
    validate_emotion_assessment,
    build_vad_vector,
    compute_emotion_trend,
    TREND_DISPLAY,
)

import httpx
import base64

load_dotenv()

app = FastAPI(title="EmoTender · 此刻一杯 Backend")


class TextAnalyzeRequest(BaseModel):
    user_text: str
    username: Optional[str] = None


class UserLoginRequest(BaseModel):
    username: str


class UserLogoutRequest(BaseModel):
    username: Optional[str] = None


class AmbientPlanRequest(BaseModel):
    emotion_assessment: dict

BASE_DIR = Path(__file__).resolve().parent
AUDIO_PATH = BASE_DIR / "recording.wav"
PROMPT_LIBRARY_PATH = BASE_DIR / "prompts" / "drink_mapping.json"
PROFILE_SUMMARY_PROMPT_PATH = BASE_DIR / "prompts" / "profile_summary_prompt.md"
PROFILE_DIR = BASE_DIR / "data" / "profiles"
STATIC_DIR = BASE_DIR / "static"
recording_process: Optional[subprocess.Popen] = None
last_result: Optional[dict] = None
conversation_history: list[dict] = []
conversation_summary = ""
emotion_history: list[dict] = []  # Track VAD trend across turns
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
    "mood_regulation_style",
)

# ==================== Drink Menu (from teammate frontend/backend update) ====================
DRINK_MENU = {
  "单品": {
    "清醒": {
      "name": "晨露茉莉",
      "name_en": "Morning Dew Jasmine",
      "recipe_modules": [
        "clear_balance",
        "bitter_focus",
        "spark_restart"
      ],
      "flavor_profile": "茉莉花香、微涩回甘、低甜、清爽提神",
      "color_profile": "淡绿清透，茶汤明亮",
      "face_state": "focused",
      "action_sequence": "make_cold_start",
      "kernel": "不是提神，是在清晨的薄雾里看清自己",
      "emotional_value": "清醒，是独处时最体面的姿态",
      "serve_line": "这杯叫《晨露茉莉》。你看茶汤里那片茉莉花瓣，像不像清晨五点半窗台上凝着的露珠？绿妍茶底配鲜柚，微涩但不苦——喝完它，世界安静了，你也是。",
      "flavor": "绿妍的茉莉花香做底，青柠和柚子提供清冽的酸度。我不加多余的糖，因为清醒本身就是一种味道。最后那抹薄荷叶的凉意，像有人在你昏沉的脑门上轻轻点了一下。",
      "backstory": "有个考研的女生，每天六点准时来，坐在靠窗的位子，点一杯晨露茉莉。她从不说话，只是翻书。后来她考上了，给我寄了一张明信片：「茗茗，那些天亮的早晨，谢谢你陪我。」",
      "recipe": "绿妍茶底250ml + 鲜榨柚子汁15ml + 青柠汁5ml + 薄荷叶2片 + 冰糖浆5ml，大杯少冰",
      "color": "淡绿清透，茶汤明亮"
    },
    "兴奋": {
      "name": "莓果派对",
      "name_en": "Berry Fiesta",
      "recipe_modules": [
        "bright_bubble",
        "spark_restart",
        "clear_balance"
      ],
      "flavor_profile": "草莓果香、明亮酸甜、气泡跳跃感",
      "color_profile": "粉嫩明亮，果肉悬浮",
      "face_state": "happy",
      "action_sequence": "make_spark_restart",
      "kernel": "不是狂欢，是心里那朵花终于开了",
      "emotional_value": "那些微小的、明亮的喜悦，值得被郑重对待",
      "serve_line": "这杯叫《莓果派对》。你看杯壁上挂着的水珠，像不像你笑出眼泪时的眼角？草莓和青提在杯底跳舞，气泡滋滋往上冒——喝完它你会发现，日子就是靠这些瞬间撑起来的。",
      "flavor": "绿妍茶底提供清爽的底色，草莓的酸甜是那种「忍不住想跟人分享」的开心。脆波波在齿间咯吱响，像有人在替你鼓掌。最后加一层云顶——那是给好心情加的一个感叹号。",
      "backstory": "有个刚升职的姑娘，发工资那天跑进来，说要请所有陌生人喝茶。她说：「茗茗，我等了三年，今天终于能说了——我做到了。」我给她这杯，她喝了一口，对着杯子拍了十几张照。",
      "recipe": "绿妍茶底200ml + 鲜草莓3颗捣碎 + 青提汁20ml + 脆波波1份 + 云顶1层，大杯少冰",
      "color": "粉嫩明亮，草莓果肉悬浮"
    },
    "难过": {
      "name": "暖绒厚乳",
      "name_en": "Warm Velvet Milk",
      "recipe_modules": [
        "soft_comfort",
        "blue_calm",
        "clear_balance"
      ],
      "flavor_profile": "嫣红茶底、厚乳醇香、微甜温热",
      "color_profile": "奶茶色暖调，表面浮着淡金奶沫",
      "face_state": "gentle",
      "action_sequence": "make_soft_comfort",
      "kernel": "不是安慰，是一双手轻轻接住了你的疲惫",
      "emotional_value": "你可以脆弱，这杯茶不会审判你",
      "serve_line": "这杯叫《暖绒厚乳》。温热的嫣红茶底和厚乳，像不像冬天呵在窗玻璃上的那口热气？喝完别急着说话，让这口温柔先替你落个地。",
      "flavor": "嫣红的麦芽香做底，厚乳的包裹感像一条毛毯。我把所有的刺激都藏在了温度里——热茶入口，先是奶香的顺滑，然后是茶的回甘。像有人轻轻拍了拍你的手背，说「没事」。",
      "backstory": "有一年冬天，店里来了个刚失恋的男孩，坐了一整晚不说话。我给他这杯，他捧在手里暖了好久。临走他说：「这杯不是茶，是围巾。」后来，「围巾」就留下来了。",
      "recipe": "嫣红茶底200ml + 厚乳80ml + 芝士糯糯1份 + 芋圆1份 + 黑糖5ml，热饮马克杯",
      "color": "奶茶色暖调，表面浮着淡金色奶沫"
    },
    "疲惫": {
      "name": "椰风轻语",
      "name_en": "Coconut Whisper",
      "recipe_modules": [
        "clear_balance",
        "soft_comfort"
      ],
      "flavor_profile": "椰奶清甜、无咖啡因、极轻柔、微凉",
      "color_profile": "奶白微透，清澈柔和",
      "face_state": "gentle",
      "action_sequence": "serve_only",
      "kernel": "不是休息，是终于允许自己什么都不选",
      "emotional_value": "不问你任何问题，这杯就是「辛苦了」三个字",
      "serve_line": "这杯叫《椰风轻语》。无茶底、无咖啡因、不加糖——它不讨好任何人的舌头。喝完它，那些紧绷的执念，会融成一种温柔的漠然。",
      "flavor": "我把所有的茶感都压到最低，只留椰奶的清甜和椰奶冻的Q弹。像夏天傍晚窗台上那盆薄荷，你路过的时候，它刚好被风吹了一下——什么都没发生，但你觉得被轻轻问候了。",
      "backstory": "有个连续加班两周的姑娘，进来就说：「茗茗，给我一杯什么都不问的。」我给她这杯。她喝完靠在沙发上睡了一个小时。醒来她说：「原来不回复消息，天也不会塌。」",
      "recipe": "无茶底椰奶300ml + 椰奶冻1份 + 桂花冻1份，常温去冰",
      "color": "奶白微透，清澈柔和"
    },
    "焦虑": {
      "name": "普洱安坐",
      "name_en": "Pu'er Settle",
      "recipe_modules": [
        "blue_calm",
        "clear_balance",
        "soft_comfort"
      ],
      "flavor_profile": "普洱陈香、微涩沉稳、温热回甘",
      "color_profile": "深琥珀色，茶汤厚重",
      "face_state": "focused",
      "action_sequence": "make_soft_comfort",
      "kernel": "不是镇定，是在浑水里等到泥沙自己沉下去",
      "emotional_value": "允许暂停，因为你知道那根线头还在手里",
      "serve_line": "这杯叫《普洱安坐》。碎银子普洱的陈香，配厚乳的醇厚——像不像雨天旧书店里翻开的第一页？喝完别找答案，先让那些在脑子里狂奔的念头，像茶叶一样慢慢沉到杯底。",
      "flavor": "碎银子普洱是底色，糯米香是茶叶自己长出来的——不是加进去的。厚乳的包裹感让涩味变得温柔。每一口都在提醒你：先坐稳，那些「万一」还没发生。",
      "backstory": "有个创业的年轻人，有段时间天天来，手机响个不停。有一天他忽然关了手机，盯着杯子说：「茗茗，我每天回两百条消息，没有一条是回给我自己的。」我给他这杯。他喝到第三口，肩膀终于放下来了。",
      "recipe": "碎银子普洱200ml + 厚乳60ml + 脆波波1份 + 黑糖波波1份，热饮大杯",
      "color": "深琥珀色，茶汤厚重"
    },
    "犹豫": {
      "name": "桂花弄",
      "name_en": "Osmanthus Drift",
      "recipe_modules": [
        "clear_balance",
        "soft_comfort"
      ],
      "flavor_profile": "桂花清香、四季春淡雅、微甜不腻",
      "color_profile": "淡金黄色，桂花悬浮",
      "face_state": "thinking",
      "action_sequence": "gesture_thinking",
      "kernel": "不是选择，是你盯着花苞看了很久，转个身它自己开了",
      "emotional_value": "不急着决定——有些答案，会在你不注意的时候悄悄抵达",
      "serve_line": "这杯叫《桂花弄》。四季春做底，桂花冻在水晶般的杯子里晃——像不像你翻来覆去想的那件事，在某个瞬间忽然变得很轻？喝完别回头，你等的那个答案，可能已经在路上了。",
      "flavor": "四季春是那种「不争不抢」的茶底，花香恰到好处，不压你也不讨好你。桂花冻在齿间轻轻裂开，像有人在耳边说「没关系，慢慢来」。脆波波的嚼感，是把犹豫一口一口咬碎。",
      "backstory": "有个做了十年公务员的客人，每天晚上翻手机里一个辞职信草稿，翻了半年。有一天他进来，没掏手机。我给他这杯。他喝到一半笑了：「茗茗，我明天交信。」后来他去了云南开民宿，给我寄过一箱他自己种的花。",
      "recipe": "四季春茶底250ml + 桂花冻1份 + 脆波波1份 + 冰糖浆5ml，大杯少冰",
      "color": "淡金黄色，桂花悬浮"
    }
  },
  "混合": [
    {
      "name": "晨光果茶",
      "name_en": "Dawn Fruit Tea",
      "emotions": [
        "清醒",
        "兴奋"
      ],
      "recipe_modules": [
        "clear_balance",
        "bright_bubble",
        "spark_restart"
      ],
      "flavor_profile": "茉莉清香与草莓果香交织",
      "color_profile": "淡绿向粉嫩渐变",
      "face_state": "happy",
      "action_sequence": "make_spark_restart",
      "serve_line": "这杯叫《晨光果茶》。你看它从杯底的淡绿渐变到杯口的粉嫩——像不像熬夜后等来的那个日出？第一口是茉莉的清醒，第二口是草莓的明亮。喝完你会发现，原来克制和放肆，可以在一杯茶里握手言和。",
      "flavor": "绿妍的茉莉花香是底色，像清晨的薄雾。但草莓和青提会慢慢浮上来——那是你压抑了一整天的、想笑想跳的那部分。脆波波在齿间跳舞，像阳光漏进窗帘的缝隙。",
      "recipe": "绿妍茶底150ml + 茉莉绿茶100ml + 草莓3颗捣碎 + 青提汁15ml + 脆波波1份 + 云顶1层，大杯少冰",
      "color": "杯底淡绿向杯口粉嫩渐变",
      "backstory": "有个做审计的姑娘，忙季结束那天来。她说：「茗茗，我连续六十天早上六点起，今天终于不用设闹钟了，但反而睡不着。」我给她这杯。她看着杯里的分层慢慢混在一起，喝了一口说：「原来我身体里那个想赖床的小孩，和那个逼自己起床的大人，可以同时被满足。」"
    },
    {
      "name": "炉火暖茶",
      "name_en": "Hearth Warm Tea",
      "emotions": [
        "难过",
        "疲惫"
      ],
      "recipe_modules": [
        "soft_comfort",
        "blue_calm"
      ],
      "flavor_profile": "温热醇厚，低酸无刺激",
      "color_profile": "暖调奶茶色",
      "face_state": "gentle",
      "action_sequence": "make_soft_comfort",
      "serve_line": "这杯叫《炉火暖茶》。它捧在手里的温度，像不像小时候冬天围炉时，最后那点炭火的余温？别急着喝，先让掌心暖一暖。这杯茶不问你发生了什么，它只负责接住你。",
      "flavor": "嫣红茶底是炉火里慢慢燃尽的木头，厚乳是那条毛毯。芋圆和芝士糯糯不是配料——是那些没说出口的「我有点累了」。喝到最后一口，你会觉得身体比进来时轻了一点点。",
      "recipe": "嫣红茶底200ml + 厚乳70ml + 芋圆1份 + 芝士糯糯1份 + 黑糖5ml，热饮大杯",
      "color": "暖调奶茶色，表面浮着淡金奶沫",
      "backstory": "有个刚失去亲人的老客人走进来，眼睛是红的，但一滴泪都没掉。他在角落坐了很久，什么都没点。我给他这杯。他捧了二十分钟才开始喝。喝完说：「她走之前那晚，握着我的手也是这个温度。」"
    },
    {
      "name": "静湖普洱",
      "name_en": "Still Lake Pu'er",
      "emotions": [
        "焦虑",
        "清醒"
      ],
      "recipe_modules": [
        "blue_calm",
        "clear_balance"
      ],
      "flavor_profile": "清澈沉稳，陈香回甘",
      "color_profile": "深琥珀透亮",
      "face_state": "focused",
      "action_sequence": "make_cold_start",
      "serve_line": "这杯叫《静湖普洱》。你看它茶汤透亮得像不像暴雨来临前，那片刻的、诡异的宁静？碎银子普洱是底，绿妍的茉莉是水面——喝完它，那些在你脑子里狂奔的念头，会像被按了暂停键。",
      "flavor": "碎银子的糯米香是天然陈化出来的，不急不躁。绿妍的茉莉提供一丝凉意——像深呼吸一口雨后的空气。我不加糖，因为安静本身就是回甘。",
      "recipe": "碎银子普洱200ml + 绿妍茶底50ml + 青柠汁3ml + 薄荷叶1片，大杯少冰",
      "color": "深琥珀色透亮，清澈见底",
      "backstory": "有个焦虑症的大学生，期末考前天天来，每次都在吧台前深呼吸。有一天他忽然说：「茗茗，我今天没有查成绩。我居然没有查成绩。」我给他这杯。他喝完说：「原来安静不是环境，是你终于允许自己听不见。」"
    },
    {
      "name": "花果气泡",
      "name_en": "Blossom Fizz",
      "emotions": [
        "犹豫",
        "兴奋"
      ],
      "recipe_modules": [
        "bright_bubble",
        "spark_restart"
      ],
      "flavor_profile": "桂花果香，气泡跳跃",
      "color_profile": "淡金+粉色气泡",
      "face_state": "happy",
      "action_sequence": "make_spark_restart",
      "serve_line": "这杯叫《花果气泡》。你看杯底那层淡金色的桂花冻，像不像你在脑子里反复修改了八百遍的那个决定？但上面那层草莓气泡会告诉你——犹豫是正常的，但花火不会等你看清楚了才绽放。",
      "flavor": "四季春的淡雅是「再想想」，但草莓和青提会推你一把——那是「差不多了」。气泡不是装饰，是跳进泳池时溅起来的第一朵水花。喝完它，你已经在路上了。",
      "recipe": "四季春茶底200ml + 草莓3颗捣碎 + 桂花冻1份 + 脆波波1份 + 云顶1层，大杯少冰",
      "color": "底层淡金，上层粉嫩气泡",
      "backstory": "有个一直想辞职旅行的姑娘，来店里画路线图画了两个月。有一天她把画满地图的笔记本往吧台一拍：「茗茗，我决定了。」我给她这杯。她一口喝到杯底：「你看，喝完了，没得犹豫了。」"
    },
    {
      "name": "雨后暖阳",
      "name_en": "After Rain Sun",
      "emotions": [
        "难过",
        "焦虑"
      ],
      "recipe_modules": [
        "soft_comfort",
        "blue_calm"
      ],
      "flavor_profile": "温热与清凉双层口感",
      "color_profile": "下层奶茶色，上层淡绿",
      "face_state": "gentle",
      "action_sequence": "make_soft_comfort",
      "serve_line": "这杯叫《雨后暖阳》。它入口的第一秒是温的，像眼泪滑过脸颊的温度。但别怕，下面那层绿妍的茉莉凉意会跟上来——那是雨停了之后，你推开窗吸到的第一口空气。",
      "flavor": "嫣红和厚乳是那个「允许你难过」的怀抱，甜润、包容、不评判。但绿妍茶底会从底下浮上来——那是你身体里更理智的那部分，告诉你「哭完了，擦擦脸，去喝杯热水」。",
      "recipe": "嫣红茶底150ml + 绿妍茶底100ml + 厚乳60ml + 芝士糯糯1份，温热大杯",
      "color": "下层奶茶色暖调，上层淡绿透亮",
      "backstory": "有个做护士的姑娘，有一晚进来，口罩没摘就趴在吧台上。我把这杯推过去。她喝了一口说：「茗茗，我今天送走了一个病人，家属没来，我一直握着他的手。」她说完就哭了。哭完把那杯茶喝完，站起来说：「好了，我回去值夜班了。」"
    },
    {
      "name": "荒野驿站",
      "name_en": "Waystation",
      "emotions": [
        "疲惫",
        "犹豫"
      ],
      "recipe_modules": [
        "clear_balance",
        "soft_comfort"
      ],
      "flavor_profile": "陈香深沉，微甜温暖",
      "color_profile": "深琥珀色带金色光泽",
      "face_state": "gentle",
      "action_sequence": "gesture_thinking",
      "serve_line": "这杯叫《荒野驿站》。你看它杯壁那层慢慢凝出的水珠，像不像你走了很远的路之后，额头上的汗？别急着决定下一站去哪儿，先让这口普洱的陈香，把你的脚底板从路上解放出来。",
      "flavor": "碎银子普洱的糯米陈香，像荒野里远远看见的一间亮着灯的木屋。四季春的花香是那种「推开门，闻到一股旧木头和干草」的味道。椰奶冻的甜很克制，像有人给你递了一杯温水。",
      "recipe": "碎银子普洱180ml + 四季春茶底70ml + 椰奶冻1份 + 桂花冻1份 + 黑糖5ml，温热大杯",
      "color": "深琥珀色带金色光泽，像旧木头的颜色",
      "backstory": "有个跑长途货运的司机，每两个月路过一次这个城市。他每次都进来喝一杯，然后靠墙睡到天亮。有一回走之前说：「茗茗，我开了二十年车，每次停下来都不知道自己在哪儿。但这里，我记得。」"
    },
    {
      "name": "晨露暖阳",
      "name_en": "Dew & Sun",
      "emotions": [
        "清醒",
        "难过"
      ],
      "recipe_modules": [
        "clear_balance",
        "soft_comfort"
      ],
      "flavor_profile": "茉莉清香与温热奶香双层",
      "color_profile": "下层淡绿，上层奶茶色",
      "face_state": "focused",
      "action_sequence": "make_cold_start",
      "serve_line": "这杯叫《晨露暖阳》。你看它——下面是清冽的茉莉绿茶，上面是温热的厚乳。像不像你心里那个「我没事」和「其实有点疼」在同时说话？别急着让它们分出胜负，先喝一口，让它们在嘴里碰个头。",
      "flavor": "绿妍茉莉是冰的、锐利的，像你脑子里那个「理性分析」的声音。但嫣红厚乳会慢慢漫上来——那是你身体里更诚实的那部分，终于被允许说「我今天不太好」。",
      "recipe": "绿妍茶底150ml + 嫣红茶底100ml + 厚乳50ml + 蜂蜜5ml，大杯分层（下层冰上层温）",
      "color": "下层淡绿清透，上层奶茶色暖黄",
      "backstory": "有个离婚的男士，每次来都点最提神的。有一晚他忽然说：「茗茗，我在法庭上特别冷静，律师都夸我体面。但我昨晚一个人把冰箱里的剩菜全倒掉了，一边倒一边想她。」我给他这杯。他后来再没点过纯绿的。"
    },
    {
      "name": "倦鸟归林",
      "name_en": "Tired Bird",
      "emotions": [
        "疲惫",
        "兴奋"
      ],
      "recipe_modules": [
        "bright_bubble",
        "soft_comfort",
        "clear_balance"
      ],
      "flavor_profile": "温暖明亮，轻盈舒缓",
      "color_profile": "暖金色",
      "face_state": "happy",
      "action_sequence": "make_spark_restart",
      "serve_line": "这杯叫《倦鸟归林》。你看它那层温暖的金色，像不像窗帘没拉严时，漏在你被子上的那一条光？喝完它，你会觉得身体醒了，但还愿意再赖一会儿。",
      "flavor": "四季春是深沉的那个你，告诉你「慢慢来」。但草莓和柑橘会轻轻推你的肩膀——那是阳光在叫你起床。桂花冻是那种「再躺五分钟」的赖床感，蜂蜜是那五分钟里做的那个美梦。",
      "recipe": "四季春茶底200ml + 草莓2颗捣碎 + 橙汁15ml + 桂花冻1份 + 蜂蜜5ml + 云顶1层，大杯少冰",
      "color": "暖金色，表面浮着白云般的云顶",
      "backstory": "有个写代码的自由职业者，日夜颠倒。他说：「茗茗，我连续三个月每天只睡四小时，但我写不出任何东西。」我给他这杯。他喝到第三口说：「我好像很久没在白天醒着的时候，觉得高兴了。」"
    },
    {
      "name": "花火指南",
      "name_en": "Spark Compass",
      "emotions": [
        "兴奋",
        "难过"
      ],
      "recipe_modules": [
        "bright_bubble",
        "soft_comfort"
      ],
      "flavor_profile": "酸甜交织，双层口感",
      "color_profile": "底层粉红，上层奶白",
      "face_state": "happy",
      "action_sequence": "make_spark_restart",
      "serve_line": "这杯叫《花火指南》。你看它——下面是热烈的草莓粉，上面是沉静的奶白。像不像你心里那场「不管了，先笑吧」和「但我还是有点疼」的拉锯战？喝下去你会发现，它们可以同时存在。",
      "flavor": "草莓和青提是那个「笑着面对世界」的你，明亮、果决、带着气泡的俏皮。但厚乳会从底下托住你——那是你知道「就算摔倒了，也会有人接住」的安全感。",
      "recipe": "绿妍茶底150ml + 草莓3颗捣碎 + 青提汁15ml + 厚乳50ml + 脆波波1份，大杯少冰",
      "color": "底层粉红果肉，上层奶白厚乳",
      "backstory": "有个学舞蹈的女孩，比赛前被分手。她来店里说：「茗茗，我明天要上台，但我现在笑不出来。」我给她这杯。她看着杯子愣了很久，然后笑了：「这杯像我的舞——前半段是快乐的，后半段是心碎的，但观众不知道，他们只看到美。」"
    },
    {
      "name": "迷雾森林",
      "name_en": "Misty Forest",
      "emotions": [
        "犹豫",
        "焦虑"
      ],
      "recipe_modules": [
        "clear_balance",
        "blue_calm"
      ],
      "flavor_profile": "淡雅沉降，微涩回甘",
      "color_profile": "淡琥珀透亮",
      "face_state": "thinking",
      "action_sequence": "gesture_thinking",
      "serve_line": "这杯叫《迷雾森林》。你看茶汤里那些细小的茶叶微粒，在光线下慢慢往下沉——像不像你脑子里那些翻来覆去的念头，终于有了落脚的力气？喝完它，你会发现答案不在别处，就在你停下来的地方。",
      "flavor": "鸭屎香的霸道香气是「想不清楚」的焦灼感，四季春是「那就不想了」的释然。蜂蜜的甜贯穿始终，像一束光从杯子底部打上来——让那些悬浮的思绪，终于有了落下时的方向。",
      "recipe": "鸭屎香茶底150ml + 四季春茶底100ml + 蜂蜜8ml + 桂花冻1份，大杯少冰",
      "color": "淡琥珀色透亮，细微茶叶悬浮",
      "backstory": "有个考了三年研的男孩，第三年出分那晚，他进来没说分数，只是盯着杯子发呆。我把这杯推过去。他看着茶叶慢慢沉底，忽然说：「茗茗，我好像一直觉得答案在天上，要跳起来够。但你看这些茶叶——它们不跳，它们只是等。」"
    },
    {
      "name": "壁炉晨光",
      "name_en": "Firelight Dawn",
      "emotions": [
        "疲惫",
        "清醒"
      ],
      "recipe_modules": [
        "clear_balance",
        "bitter_focus",
        "spark_restart"
      ],
      "flavor_profile": "深沉普洱，微带茉莉清香",
      "color_profile": "深琥珀带金色光泽",
      "face_state": "focused",
      "action_sequence": "make_cold_start",
      "serve_line": "这杯叫《壁炉晨光》。你看它——深琥珀色的茶汤里，透着一层薄薄的金色光晕，像不像冬夜壁炉的火还没灭，但窗帘缝里已经漏进了早晨的光？喝完它，你会带着身体的暖意，慢慢睁开眼睛。",
      "flavor": "碎银子普洱的陈香是壁炉里将熄未熄的炭火，茉莉绿茶的清冽是推窗时涌进来的冷空气。薄荷叶的凉是那种「睁开眼，还没起床，先闻到厨房里有人煮茶」的细微幸福。",
      "recipe": "碎银子普洱180ml + 茉莉绿茶70ml + 薄荷叶1片 + 柠檬汁3ml + 蜂蜜5ml，大杯温热",
      "color": "深琥珀色带金色光泽，像晨光穿过茶汤",
      "backstory": "有个总上夜班的医生，下班时天刚亮。她每次进来都带着消毒水的味道，说：「茗茗，我那个世界是惨白的，我想看看有颜色的天亮。」我给她这杯。她捧着杯子看向窗外，说：「这杯茶的颜色，跟我办公室窗外那个冬天的日出一样。」"
    },
    {
      "name": "离线茶",
      "name_en": "Offline Tea",
      "emotions": [
        "难过",
        "焦虑",
        "疲惫"
      ],
      "recipe_modules": [
        "soft_comfort",
        "blue_calm",
        "clear_balance"
      ],
      "flavor_profile": "极淡，微凉，几乎无味",
      "color_profile": "极淡奶白近乎透明",
      "face_state": "gentle",
      "action_sequence": "serve_only",
      "serve_line": "这杯叫《离线茶》。它没有任何鲜明的颜色、强烈的味道或张扬的香气。它淡得像一杯放凉了的水。但喝下去之后——那些后台乱跑的进程，终于被你亲手结束了。",
      "flavor": "我把所有的甜、酸、苦都调到了最低。无茶底的椰奶是空白的画布，椰奶冻和桂花冻是微弱的笔触。它们在口腔里不打架，也不争抢，只是安安静静地流过去。",
      "recipe": "无茶底椰奶250ml + 椰奶冻1份 + 桂花冻1份 + 蜂蜜3ml，常温去冰",
      "color": "极淡的奶白色，近乎透明，像一杯被稀释了的薄雾",
      "backstory": "有个做心理咨询师的客人，自己也有焦虑。她说：「茗茗，我今天听了九个来访者的故事，每个都把我的能量吸走一点。我现在像一块电量1%的手机。」我给她这杯。她喝了很久，走的时候说：「我没关机，但我把所有的通知都关了。」"
    }
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


# MiMo ASR 云端配置
ASR_API_KEY = os.environ.get("ASR_API_KEY", "")
ASR_BASE_URL = os.environ.get("ASR_BASE_URL", "https://api.xiaomimimo.com/v1")
ASR_MODEL_NAME = os.environ.get("ASR_MODEL", "mimo-v2.5-asr")
ASR_ENABLED = bool(ASR_API_KEY and not ASR_API_KEY.startswith("在这里"))

# MiMo TTS 云端配置
TTS_API_KEY = os.environ.get("TTS_API_KEY", os.environ.get("ASR_API_KEY", ""))
TTS_BASE_URL = os.environ.get("TTS_BASE_URL", os.environ.get("ASR_BASE_URL", "https://api.xiaomimimo.com/v1"))
TTS_MODEL = os.environ.get("TTS_MODEL", "mimo-v2.5-tts")
TTS_VOICE = os.environ.get("TTS_VOICE", "冰糖")
TTS_ENABLED = bool(TTS_API_KEY and not TTS_API_KEY.startswith("在这里"))

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

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

RECOMMENDATION_CONFIRMATIONS = (
    "好",
    "好的",
    "可以",
    "行",
    "来吧",
    "嗯",
    "嗯嗯",
    "要",
    "需要",
    "开始吧",
    "按你说的",
    "你做主",
)

RECOMMENDATION_OFFER_MARKERS = (
    "正式推荐",
    "推荐一杯",
    "给你推荐",
    "为你推荐",
    "要不要",
    "需不需要",
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

ALLOWED_TURN_TYPES = {
    "bar_chat",
    "recommendation",
    "safety",
}


def previous_turn_offered_recommendation() -> bool:
    if not conversation_history:
        return False

    previous = conversation_history[-1]
    prompt_text = " ".join(
        str(previous.get(key, ""))
        for key in ("bartender_line", "feedback_prompt")
    )
    return any(marker in prompt_text for marker in RECOMMENDATION_OFFER_MARKERS)


def is_recommendation_confirmation(user_text: str) -> bool:
    text = user_text.strip()
    return any(trigger in text for trigger in RECOMMENDATION_CONFIRMATIONS)


def route_turn_type(user_text: str) -> str:
    text = user_text.strip()

    if any(trigger in text for trigger in SAFETY_TRIGGERS):
        return "safety"

    if any(trigger in text for trigger in RECOMMENDATION_TRIGGERS):
        return "recommendation"

    if previous_turn_offered_recommendation() and is_recommendation_confirmation(text):
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
            "mood_regulation_style": [],
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


def build_prompt_profile_context(profile_context: dict) -> dict:
    """Expose only stable recommendation preferences, never historical emotion evidence."""
    if profile_context.get("mode") != "logged_in":
        return {
            "mode": "anonymous",
            "message": "用户未登录，不使用长期 profile。",
        }

    stable = profile_context.get("stable_profile", {})
    return {
        "mode": "logged_in",
        "username": profile_context.get("username"),
        "taste_preferences": list(stable.get("taste_preferences", [])),
        "drink_history": list(stable.get("drink_history", [])),
        "conversation_style": list(stable.get("conversation_style", [])),
        "avoidances": list(stable.get("avoidances", [])),
        "mood_regulation_style": list(stable.get("mood_regulation_style", [])),
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
    append_unique(stable["mood_regulation_style"], summary.get("mood_regulation_style", []))

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
        "feedback_prompt": data["feedback_prompt"],
        "emotion_assessment": data["emotion_assessment"],
    }

    if data["turn_type"] == "recommendation":
        item["drink_name"] = data["drink_name"]
        item["recipe_modules"] = data["recipe_modules"]
        item["recommendation_reason"] = data["recommendation_reason"]

    conversation_history.append(item)
    vad = data["emotion_assessment"].get("vad")
    if vad:
        emotion_history.append({"valence": vad["valence"], "arousal": vad["arousal"], "label": data.get("emotion_label", "?")})
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
    if not ASR_ENABLED:
        raise RuntimeError("asr_unavailable")

    logger.info(f"开始 MiMo ASR 语音识别: {wav_path}")
    url = f"{ASR_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {ASR_API_KEY}",
        "Content-Type": "application/json",
    }

    # 读取音频文件并 base64 编码
    with open(wav_path, "rb") as f:
        audio_bytes = f.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    payload = {
        "model": ASR_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "wav",
                        },
                    }
                ],
            }
        ],
        "asr_options": {"language": "zh"},
        "stream": False,
    }

    last_error = None
    for attempt in range(3):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"asr_error_{resp.status_code}")
            result = resp.json()
            text = ""
            choices = result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                text = msg.get("content", "").strip()
            if not text or len(text) < 2:
                logger.warning(f"静默或过短语音: '{text}'")
                raise RuntimeError("silence_detected")
            logger.info(f"MiMo ASR 识别结果: {text}")
            return text
        except Exception as e:
            last_error = e
            if attempt < 2:
                logger.warning(f"ASR 尝试 {attempt+1} 失败, 重试: {e}")
                time.sleep(1)
    raise last_error


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
    prompt_profile_context = build_prompt_profile_context(profile_context)
    single_menu = "\n".join(MENU_LINES_SINGLE)
    blend_menu = "\n".join(MENU_LINES_BLEND)

    # Build emotion trend
    emotion_trend = ""
    if len(emotion_history) >= 2:
        trend_labels = [h["label"] if isinstance(h, dict) else str(h) for h in (emotion_history[-3:] if len(emotion_history) >= 3 else emotion_history)]
        emotion_trend = f"\n用户情绪变化趋势（最近{len(trend_labels)}轮）：{' → '.join(trend_labels)}。该趋势只能用于调整回应语气，不能作为本轮 NRC 评分证据。"

    prompt = f"""
你是「此刻一杯」情绪茶饮的 AI 中控分析模块。
你的角色是茗茗，28岁，开了6年茶饮店。
你的信念是：茶是情绪的容器，不是答案。
你的表达必须低沉、松弛、直球、不说废话。

你必须只输出一个合法 JSON 对象。内部推理尽量简洁，不要展开分析。
不要输出 Markdown。
不要输出解释。
不要输出代码块。
不要在 JSON 前后添加任何文字。

规则路由给出的初步模式建议：
{turn_type}

你必须根据用户原话、最近对话历史和用户长期 profile 自行决定最终 turn_type。
规则路由只是提示，不是最终答案。

用户原话：
{user_text}

会话摘要：
{conversation_summary or "暂无"}
{emotion_trend}

最近对话历史：
{json.dumps(recent_history, ensure_ascii=False, indent=2)}

用户长期 profile 中可用于推荐的稳定偏好：
{json.dumps(prompt_profile_context, ensure_ascii=False, indent=2)}

本轮情绪隔离规则：
- emotion_assessment、emotion_label、emotion_blend、emotion_blend.source 和 complex_emotion 只能依据用户本轮原话与当前会话历史判断。
- 不得根据用户长期 profile、历史会话摘要、上次使用时的情绪或过去发生的事件判断本轮情绪。
- 长期 profile 只能用于口味偏好、避忌、交流风格和历史饮品参考。

NRC 八类情绪评估规则：
- 唯一允许的情绪键为：{json.dumps(NRC_EMOTIONS, ensure_ascii=False)}。
- emotion_assessment.taxonomy 必须是 "nrc_emolex_8"。
- emotion_assessment.scores 必须包含全部八个键，每项范围 0.0 到 1.0，总和必须接近 1.0。
- 必须先从当前会话提取原话证据，再为八类情绪评分。
- primary_emotion 必须对应最高分。
- evidence 每项必须包含 quote、emotions 和 interpretation；quote 必须逐字来自本轮原话或当前会话历史。
- 每个分数大于零的情绪都必须至少出现在一项 evidence.emotions 中。
- 用户明确自述优先；必须正确处理“不是”“没有”“并不”等否定表达，以及“但是”“不过”“同时”等转折或混合表达。
- confidence 范围为 0.0 到 1.0；证据不足时降低 confidence，并将 clarification_needed 设为 true。
- NRC 分数是情绪构成分数，不是医学诊断或心理学概率。

这是 EmoTender 的 prompt 库，包含情绪维度、混合规则、配方模块、表情状态和动作序列：
{json.dumps(prompt_library, ensure_ascii=False, indent=2)}

这是「此刻一杯」当前可用于正式推荐和牛皮纸小票的后端茶饮菜单：
单品：
{single_menu}

混合情绪特调：
{blend_menu}

必须输出这些字段：
schema_version, turn_type, user_text, emotion_assessment, emotion_label, emotion_blend, complex_emotion,
need_summary, drink_name, recipe_modules, flavor_profile, color_profile,
face_state, bartender_line, action_sequence, feedback_prompt, recommendation_reason。

字段类型要求：
- schema_version 必须是字符串，例如 "1.0"
- turn_type 必须是字符串，例如 "initial_order"
- user_text 必须是字符串
- emotion_assessment 必须是对象，包含 taxonomy、scores、primary_emotion、confidence、evidence、clarification_needed
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
- recommendation_reason 必须是字符串
- emotion_blend 必须是数组，每一项包含 emotion、weight 和 source，例如 [{{"emotion": "难过", "weight": 0.7, "source": "用户说今天考试没有考好"}}, {{"emotion": "焦虑", "weight": 0.3, "source": "用户担心明天仍然没有状态"}}]
- emotion_blend 的 weight 总和必须接近 1.0
- emotion_blend.source 必须简短说明该情绪在当前会话中的来源，不能引用长期 profile 或过去会话。

模式规则：
- turn_type 只能是 "bar_chat"、"recommendation" 或 "safety"。
- 如果 turn_type 是 "bar_chat"，这一轮是闲聊。你仍然必须输出完整 JSON，用于驱动机器人表情、动作和台词，但不要正式推荐饮品。
- 如果 turn_type 是 "bar_chat"，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，flavor_profile 使用 "无正式推荐"，color_profile 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，recommendation_reason 使用 "无正式推荐"。
- 如果 turn_type 是 "bar_chat"，face_state 必须体现用户情绪，action_sequence 优先使用 "gesture_thinking"、"gesture_shrug"、"serve_only"。
- 如果 turn_type 是 "recommendation"，必须正式推荐当前后端饮品菜单中的饮品，drink_name 必须精确使用菜单里的中文饮品名，recipe_modules 不能为空。
- 如果 turn_type 是 "recommendation"，recommendation_reason 使用 2 到 4 句话：先准确接住用户在当前会话中提到的具体经历，再说明这款饮品为什么适合此刻；不能引用历史 profile 中的事件或情绪，不能承诺饮品能够解决现实问题。
- 如果推荐时判断为单一情绪，优先使用菜单“单品”；如果判断为两种或三种主要情绪，可以使用菜单“混合情绪特调”。
- 推荐饮品时，bartender_line 优先使用或贴近菜单中对应饮品的 serve_line。
- 如果用户明确要求推荐、来一杯、让你做主，turn_type 必须是 "recommendation"。
- 如果最近一轮你询问是否正式推荐饮品，而用户本轮表达同意、接受、让你安排，turn_type 必须是 "recommendation"。
- 如果用户只是继续倾诉、闲聊、打招呼，且没有表达要饮品推荐，turn_type 使用 "bar_chat"。
- 如果 turn_type 是 "safety"，只推荐无咖啡因温和饮品，drink_name 使用 "无正式推荐"，recipe_modules 使用 []，action_sequence 优先使用 "serve_only"。
- 如果 turn_type 是 "safety"，recommendation_reason 使用 "无正式推荐"。
- 如果用户长期 profile 中有口味偏好、历史饮品或情绪模式，请把它作为个性化依据，但不要在台词里暴露“我保存了你的资料”这类后台措辞。
- 每轮最多问一个问题。
- 不要使用这些词：亲、哦、呢、呀、哈、啦、咱、呗。
- 不要做医学诊断、法律建议、股票建议。

正向情绪放大规则：
- 当 joy 为 primary_emotion 且权重超过 0.5 时，feedback_prompt 应主动引导用户放大此刻的好心情。
- 可以建议：趁状态好试试从没试过的新搭配；把这杯分享给身边的人；记住这个味道，下次不开心时能想起来今天。
- 不要只说"开心就好"，要有具体的、可执行的小建议。

情绪调节建议规则：
- 当用户本轮情绪明显负面（sadness、fear、anger 中任一权重超过 0.4）时，feedback_prompt 末尾可以轻度附带一个情绪调节建议。
- 建议必须温和、具体、不说教。例如："喝完这杯，出去走走"、"今天早点休息"、"给一个信任的人打个电话"、"深呼吸三次"。
- 每轮最多一个调节建议，放在 feedback_prompt 最后，用句号或逗号与前文连接。
- 不要每次都给，根据对话上下文自然决定是否需要。如果用户已经在做调节行为（比如已经在散步），就不再建议。
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
                max_completion_tokens=8192,
                timeout=90,
            )
            llm_content = response.choices[0].message.content
            raw_reasoning = getattr(response.choices[0].message, 'reasoning_content', None)
            logger.info(f"LLM raw content (first 300): {repr(llm_content[:300] if llm_content else None)}")
            logger.info(f"LLM raw reasoning (first 200): {repr(raw_reasoning[:200] if raw_reasoning else None)}")
            logger.info(f"LLM finish_reason: {response.choices[0].finish_reason}")
            parsed = extract_json(llm_content)
            validate_emotion_assessment(
                parsed["emotion_assessment"],
                [
                    user_text,
                    *(str(item.get("user_text", "")) for item in recent_history),
                ],
            )
            return parsed
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


def current_emotion_evidence_texts(user_text: str) -> list[str]:
    return [
        user_text,
        *(str(item.get("user_text", "")) for item in get_recent_history()),
    ]


# 中文情绪名 -> NRC 英文键映射
_CN_TO_NRC = {
    "愤怒": "anger", "期待": "anticipation", "厌恶": "disgust", "恐惧": "fear",
    "喜悦": "joy", "悲伤": "sadness", "惊讶": "surprise", "信任": "trust",
    "生气": "anger", "焦虑": "anger", "紧张": "fear", "害怕": "fear",
    "开心": "joy", "高兴": "joy", "快乐": "joy", "难过": "sadness",
    "伤心": "sadness", "吃惊": "surprise", "意外": "surprise",
}

def _normalize_emotion_blend(blend: list) -> list:
    """将 emotion_blend 中的中文情绪名映射回英文 NRC 键"""
    for item in blend:
        emo = item.get("emotion", "")
        if emo in _CN_TO_NRC:
            item["emotion"] = _CN_TO_NRC[emo]
    return blend

def apply_emotion_compatibility(data: dict) -> dict:
    if "emotion_blend" in data:
        _normalize_emotion_blend(data["emotion_blend"])
    data.update(derive_legacy_fields(data["emotion_assessment"]))
    data["target_flavor_vector"] = build_target_flavor_vector(
        data["emotion_assessment"]["scores"]
    )
    # 生成标准化 UEV
    data["uev"] = build_uev(data["emotion_assessment"], emotion_history)
    return data


def validate_result(data: dict) -> None:
    required_fields = [
        "schema_version",
        "turn_type",
        "user_text",
        "emotion_assessment",
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
        "recommendation_reason",
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

        if "source" not in item:
            raise ValueError(f"emotion_blend item missing source: {item}")

        if not isinstance(item["emotion"], str):
            raise TypeError(f"emotion_blend emotion must be a string: {item}")

        if not isinstance(item["weight"], (int, float)):
            raise TypeError(f"emotion_blend weight must be a number: {item}")

        if not isinstance(item["source"], str):
            raise TypeError(f"emotion_blend source must be a string: {item}")

        if not item["source"].strip():
            raise ValueError(f"emotion_blend source must not be empty: {item}")

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
        "recommendation_reason",
    ]

    for field in string_fields:
        if not isinstance(data[field], str):
            raise TypeError(f"{field} must be a string, got {type(data[field]).__name__}: {data[field]}")
        if not data[field].strip():
            raise ValueError(f"{field} must not be empty")

    if data["turn_type"] not in ALLOWED_TURN_TYPES:
        raise ValueError(f"Unknown turn_type: {data['turn_type']}")

    if data["turn_type"] == "recommendation" and get_drink_info(data["drink_name"]) is None:
        raise ValueError(f"Unknown drink_name: {data['drink_name']}")

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
    emotion_assessment = build_fallback_emotion_assessment(user_text)
    if turn_type in CHAT_ONLY_TURN_TYPES:
        result = {
            "schema_version": "1.0",
            "turn_type": turn_type,
            "user_text": user_text,
            "emotion_assessment": {**emotion_assessment, "vad": build_vad_vector(emotion_assessment["scores"]), "trend": "steady", "trend_display": TREND_DISPLAY["steady"]},
            "emotion_label": "疲惫",
            "emotion_blend": [
                {"emotion": "疲惫", "weight": 1.0, "source": "系统无法完成本轮情绪分析。"}
            ],
            "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
            "need_summary": "系统自检中，需要被接住而不是立刻推荐饮品。",
            "drink_name": NO_FORMAL_DRINK_NAME,
            "recipe_modules": [],
            "flavor_profile": NO_FORMAL_DRINK_NAME,
            "color_profile": NO_FORMAL_DRINK_NAME,
            "face_state": "gentle",
            "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，你先缓一缓，我马上回来。先喝口茶暖暖。",
            "action_sequence": "gesture_thinking" if turn_type == "bar_chat" else "serve_only",
            "feedback_prompt": "你愿意的话，可以再说一点。",
            "recommendation_reason": NO_FORMAL_DRINK_NAME,
        }
        return apply_emotion_compatibility(result)

    result = {
        "schema_version": "1.0",
        "turn_type": "recommendation",
        "user_text": user_text,
        "emotion_assessment": {**emotion_assessment, "vad": build_vad_vector(emotion_assessment["scores"]), "trend": "steady", "trend_display": TREND_DISPLAY["steady"]},
        "emotion_label": "清醒",
        "emotion_blend": [
            {"emotion": "清醒", "weight": 1.0, "source": "系统进入推荐 fallback。"}
        ],
        "complex_emotion": "大模型链路超载，触发酒馆全息自检保护协议。",
        "need_summary": "系统自检，需要一杯清爽低甜的特调冷启动。",
        "drink_name": "晨露茉莉",
        "recipe_modules": [
            "clear_balance",
            "bitter_focus",
        ],
        "flavor_profile": "清爽、微苦、低甜、带轻微气泡感",
        "color_profile": "透明偏冷调，带一点淡青色",
        "face_state": "focused",
        "bartender_line": "（安全协议启动）我的核心大脑似乎开了一会儿小差，不过别担心，我先为你推荐一杯标志性的'晨露茉莉'，让我们重新连接。",
        "action_sequence": "make_cold_start",
        "feedback_prompt": "喝完感觉清醒一点了吗？",
        "recommendation_reason": "这次分析没有完整返回，我先用一杯清爽低甜的冷启动接住这一轮。它不能替你解决正在面对的事情，但能让推荐流程保持完整。",
    }
    return apply_emotion_compatibility(result)


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
    turn_type_hint = route_turn_type(user_text)
    used_fallback = False
    llm_error = None

    try:
        result = analyze_text(user_text, turn_type_hint, profile_context)
        result = normalize_result(result)
        validate_emotion_assessment(
            result["emotion_assessment"],
            current_emotion_evidence_texts(user_text),
        )
        # VAD 三维向量（后处理推导，不依赖 LLM）
        vad = build_vad_vector(result["emotion_assessment"]["scores"])
        result["emotion_assessment"]["vad"] = vad
        # 情绪趋势
        trend = compute_emotion_trend(emotion_history)
        result["emotion_assessment"]["trend"] = trend
        result["emotion_assessment"]["trend_display"] = TREND_DISPLAY.get(trend, trend)
        result = apply_emotion_compatibility(result)
        if turn_type_hint == "safety":
            result["turn_type"] = "safety"
        elif result.get("turn_type") not in ALLOWED_TURN_TYPES:
            result["turn_type"] = turn_type_hint
        result["user_text"] = user_text
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)
        if result["turn_type"] == "recommendation":
            result["ambient_plan"] = {"enabled": False}
    except Exception as exc:
        used_fallback = True
        llm_error = str(exc)
        logger.warning(f"LLM/NLP 链路异常，使用熔断兜底: {exc}", exc_info=True)
        result = fallback_result(user_text, turn_type_hint)
        validate_result(result)
        result = enrich_result_with_drink_metadata(result)
        if result["turn_type"] == "recommendation":
            result["ambient_plan"] = {"enabled": False}

    update_conversation_state(result)

    return {
        "ok": True,
        "username": username,
        "user_text": user_text,
        "turn_type": result["turn_type"],
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
        max_completion_tokens=8192,
        timeout=90,
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
            silence_assessment = {
                "taxonomy": "nrc_emolex_8",
                "scores": {
                    "anger": 0.0,
                    "anticipation": 0.0,
                    "disgust": 0.0,
                    "fear": 0.0,
                    "joy": 0.0,
                    "sadness": 0.0,
                    "surprise": 0.0,
                    "trust": 1.0,
                },
                "primary_emotion": "trust",
                "confidence": 0.0,
                "evidence": [
                    {
                        "quote": "本轮没有检测到有效语音。",
                        "emotions": ["trust"],
                        "interpretation": "没有足够的用户输入用于情绪判断",
                    }
                ],
                "clarification_needed": True,
            }
            silence_result = {
                "schema_version": "1.0",
                "turn_type": "bar_chat",
                "user_text": "",
                "emotion_assessment": silence_assessment,
                "emotion_label": "清醒",
                "emotion_blend": [{"emotion": "清醒", "weight": 1.0, "source": "本轮没有检测到有效语音。"}],
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
                "recommendation_reason": NO_FORMAL_DRINK_NAME,
                "target_flavor_vector": build_target_flavor_vector(
                    silence_assessment["scores"]
                ),
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


@app.post("/api/ambient/plan")
def ambient_plan_api(payload: AmbientPlanRequest):
    try:
        evidence = payload.emotion_assessment.get("evidence", [])
        validate_emotion_assessment(
            payload.emotion_assessment,
            [
                item.get("quote", "")
                for item in evidence
                if isinstance(item, dict)
            ],
        )
        return {
            "ok": True,
            "ambient_plan": build_ambient_plan(payload.emotion_assessment),
        }
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@app.post("/api/tts")
def tts_endpoint(req: dict):
    """TTS 语音合成端点 — 将文本转为 base64 音频"""
    text = (req.get("text") or "").strip()
    voice = req.get("voice") or TTS_VOICE
    if not text:
        return {"ok": False, "error": "empty text"}
    if not TTS_ENABLED:
        return {"ok": False, "error": "TTS not configured"}

    for attempt in range(3):
        try:
            resp = httpx.post(
                f"{TTS_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {TTS_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": TTS_MODEL,
                    "messages": [{"role": "assistant", "content": text}],
                    "modalities": ["text", "audio"],
                    "audio": {"voice": voice, "format": "mp3"},
                },
                timeout=20,
            )
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {"ok": False, "error": "no choices", "detail": data}
            audio = choices[0].get("message", {}).get("audio", {})
            audio_b64 = audio.get("data", "")
            if not audio_b64:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return {"ok": False, "error": "no audio data"}
            return {"ok": True, "audio": audio_b64, "format": "mp3"}
        except Exception as e:
            if attempt < 2:
                logger.warning(f"TTS 尝试 {attempt+1} 失败, 重试: {e}")
                time.sleep(1)
            else:
                return {"ok": False, "error": str(e)}


@app.get("/api/text/stream")
async def text_stream(username: str = "", user_text: str = ""):
    """SSE streaming endpoint for text analysis"""
    import asyncio, json as _json

    def _sse(event_type, data):
        return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_generator():
        if not user_text.strip():
            yield _sse("error", {"error": "empty text"})
            return

        yield _sse("status", {"message": "正在分析情绪..."})

        # Run analysis in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None, process_user_text, user_text.strip(), username or None
            )
        except Exception as exc:
            yield _sse("error", {"error": str(exc)})
            return

        # Send emotion data first
        ea = result.get("control_json", {}).get("emotion_assessment", {})
        yield _sse("emotion", {"emotion_assessment": ea})

        # Stream bartender line character by character
        bartender = result.get("control_json", {}).get("bartender_line", "")
        for ch in bartender:
            yield _sse("token", {"token": ch})
            await asyncio.sleep(0.03)

        # Send final complete result
        yield _sse("done", result)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
def index():
    index_path = BASE_DIR / "static" / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Error: static/index.html not found</h1>",
            status_code=500,
        )
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
