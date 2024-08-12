import re
import time

from asyncio import sleep
from collections import defaultdict

from pagermaid import redis, redis_status, log, bot, logs
from pagermaid.listener import listener
from pagermaid.AsyncTask import AsyncTask
from telethon import functions, types

if not redis_status():
    raise Exception("redis未连接无法使用selfDestruct")

ignoreChatKey = "selfDestruct:ignoreChat"
allowPrivateChatKey = "selfDestruct:allowPrivateChat"
sleepTimeRedisKey = "selfDestruct:sleepTime"
messageRedisKey = "selfDestruct:messageList"
messageExpiredRedisKey = "selfDestruct:expiredTime"
redisExpiredTime = redis.get(messageExpiredRedisKey)
expiredTime = 1800 if not redisExpiredTime else int(redisExpiredTime.decode())
redisSleepTime = redis.get(sleepTimeRedisKey)
sleepTime = 60 if not redisSleepTime else int(redisSleepTime.decode())
ignoreChat = ""
allowPrivateChat = ""
traceKeywordsDict = defaultdict()

traceRedisKey = "trace"
globalMatchRedisKey = f'{traceRedisKey}:globalMatch'
globalMatch = redis.get(globalMatchRedisKey)
globalMatch = True if globalMatch else False


def loadSfdChatConfig():
    global ignoreChat, allowPrivateChat
    ignoreChat = redis.get(ignoreChatKey)
    allowPrivateChat = redis.get(allowPrivateChatKey)
    if not ignoreChat:
        ignoreChat = ""
    else:
        ignoreChat = ignoreChat.decode()
    if not allowPrivateChat:
        allowPrivateChat = ""
    else:
        allowPrivateChat = allowPrivateChat.decode()


def loadTraceChatConfig():
    global traceKeywordsDict
    traceKeywordsDict = defaultdict(list)
    keys = redis.keys(f'{traceRedisKey}:*')
    for key in keys:
        traceKeywordsDict[key.decode()] = redis.get(key).decode()


loadSfdChatConfig()
loadTraceChatConfig()


async def getChatId(context):
    try:
        chatId = int(context.parameter[1])
    except:
        chatId = context.chat_id
    return chatId


async def getExpiredTime4ChatId(chatId):
    expiredTime4Chat = redis.get(f'{messageExpiredRedisKey}:{chatId}')
    try:
        expiredTime4Chat = int(expiredTime4Chat.decode()) if expiredTime4Chat else expiredTime
    except:
        expiredTime4Chat = expiredTime
    return expiredTime4Chat


@listener(is_plugin=True, outgoing=True, command="sfd",
          diagnostics=True,
          description="""
将消息id存入redis有序队列按发送时间排序，之后每隔一段时间获取队列中要到期的消息然后删除。

说明：
sfd [ chatId ]，查看当前会话设置或者指定chatId。
sfd time 60，设置检查过期间隔时间为60秒，默认为60秒。
sfd exp 60/- [ chatId ]，设置过期时间为60秒（后面可选指定id），默认为1800秒（30分钟）。时间写-号则删除配置。
sfd { on | off } [ chatId ]，设置当前会话开启/关闭自毁，或者指定id，默认所有非私聊会话自动开启，私聊自动关闭。
sfd pin，回复一条自己发的消息，该消息将不会被删除。
sfd { ! | ！ }，查看禁用自毁会话列表。
sfd his [ chatId ]，删除指定会话所有历史消息或当前会话。
sfd reset，重置所有配置。

sfd trace < emoji > [ keyword ]，设置自动点赞，如果回复一条消息发送emoji，则对那个人自动点赞；如果发送一个\
关键字，则根据关键字进行自动点赞，根据是否回复他人决定是否是全局关键字（如果有回复则设置回复消息所在聊天的关\
键字，否则就是全局关键字）；要删除用-号：-[keyword]；支持正则了，只需要keyword传入 reg/正则表达式 即可。
sfd trace gm { true | false }，开关全局匹配，效果就是同一条消息触发多个点赞。
sfd trace reset，重置自动点赞所有配置。
""",
          parameters="")
async def selfDestruct(context):
    global sleepTime, expiredTime, ignoreChat, allowPrivateChat, globalMatch, traceKeywordsDict
    p = context.parameter
    if len(p) == 0 or (len(p) == 1 and p[0][0] in "-1234567890"):
        if len(p) == 1:
            chatId = p[0]
        else:
            chatId = context.chat_id
        if f'{chatId}'.startswith("-100"):
            # 非私聊
            if f',{chatId},' in f'{ignoreChat},':
                status = "未开启"
            else:
                status = "已开启"
        else:
            # 私聊
            if f',{chatId},' not in f'{allowPrivateChat},':
                status = "未开启"
            else:
                status = "已开启"
        expiredTime4Chat = await getExpiredTime4ChatId(chatId)
        await context.edit(f"⚙️`{chatId}`当前设置\n检测间隔时间：{sleepTime}秒\n消息过期时间：{expiredTime4Chat}秒\n{status}")
        return
    if p[0] == "time":
        if len(p) != 2:
            await context.edit("设置间隔时间参数错误，请输入数字")
            return
        else:
            try:
                sleepTime = int(p[1])
            except:
                await context.edit("设置间隔时间参数错误，请输入数字")
                return
            redis.set(sleepTimeRedisKey, sleepTime)
            await context.edit(f"设置时间间隔为{sleepTime}秒")
            return
    elif p[0] == "exp":
        chatId = ""
        isDelete = False
        try:
            expiredTime4Chat = int(p[1])
        except:
            if p[1] == "-":
                isDelete = True
            else:
                await context.edit("设置过期时间参数错误，请输入数字")
                return
        if len(p) >= 3:
            try:
                chatId = f':{int(p[2])}'
            except:
                await context.edit("指定chatId格式错误，请输入数字")
                return
        if chatId:
            if isDelete:
                redis.delete(f'{messageExpiredRedisKey}{chatId}')
                await context.edit(f"删除 `{chatId[1:]}` 过期时间成功")
            else:
                redis.set(f'{messageExpiredRedisKey}{chatId}', expiredTime4Chat)
                await context.edit(f"设置 `{chatId[1:]}` 过期时间为{expiredTime4Chat}秒")
        else:
            redis.set(messageExpiredRedisKey, expiredTime4Chat)
            expiredTime = expiredTime4Chat
            await context.edit(f"设置全局过期时间为{expiredTime4Chat}秒")
        return
    elif p[0] == "on":
        chatId = await getChatId(context)
        if f'{chatId}'.startswith("-100"):
            # 非私聊
            if f',{chatId},' not in f'{ignoreChat},':
                await context.edit("已在当前会话开启自毁")
                await delayDelete(context)
                return
            finalIgnoreChat = ignoreChat.replace(f',{chatId}', '')
            if finalIgnoreChat:
                redis.set(ignoreChatKey, finalIgnoreChat)
            else:
                redis.delete(ignoreChatKey)
        else:
            # 私聊
            if f',{chatId},' in f'{allowPrivateChat},':
                await context.edit("已在当前会话开启自毁")
                await delayDelete(context)
                return
            redis.set(allowPrivateChatKey, f'{allowPrivateChat},{chatId}')
        loadSfdChatConfig()
        await context.edit("开启自毁成功")
        await delayDelete(context)
    elif p[0] == "off":
        chatId = await getChatId(context)
        if f'{chatId}'.startswith("-100"):
            # 非私聊
            if f',{chatId},' in f'{ignoreChat},':
                await context.edit("当前会话未开启自毁，无需关闭")
                await delayDelete(context)
                return
            redis.set(ignoreChatKey, f'{ignoreChat},{chatId}')
        else:
            # 私聊
            if f',{chatId},' not in f'{allowPrivateChat},':
                await context.edit("当前会话未开启自毁，无需关闭")
                await delayDelete(context)
                return
            finalAllowChat = allowPrivateChat.replace(f',{chatId}', '')
            if finalAllowChat:
                redis.set(allowPrivateChatKey, finalAllowChat)
            else:
                redis.delete(allowPrivateChatKey)
        loadSfdChatConfig()
        await context.edit("关闭自毁成功")
        await delayDelete(context)
    elif p[0] == "pin":
        msg = await context.get_reply_message()
        me = await context.client.get_me()
        if msg and me.id == msg.sender_id:
            redis.zrem(messageRedisKey, f'{msg.chat_id},{msg.id},{msg.text}')
            await context.edit("该消息已取消自毁")
            await delayDelete(context)
        else:
            await context.edit("请回复一条自己发的消息")
            await delayDelete(context)
    elif p[0] == "now":
        msg = redis.zpopmin(messageRedisKey, 1)
        while msg:
            msg = msg[0]
            msg = msg[0].decode().split(",")
            try:
                await bot.delete_messages(entity=int(msg[0]), message_ids=[int(msg[1])])
            except:
                pass
            msg = redis.zpopmin(messageRedisKey, 1)
        await context.edit("历史消息已全部清除")
        await delayDelete(context)
    elif p[0] == "!" or p[0] == "！":
        ids = ignoreChat.split(",")
        content = ""
        for cid in ids:
            if cid:
                content = f'{content}\n`{cid.strip("")}` https://t.me/c/{cid[4:]}'
        content = f'📄当前禁用非私聊自毁会话：{content}\n\n📄当前启用私聊自毁会话：'

        ids = allowPrivateChat.split(",")
        for cid in ids:
            if cid:
                content = f'{content}\n`{cid.strip("")}` tg://user?id={cid}'
        await context.edit(content)
    elif p[0] == "his":
        if len(p) == 1:
            chatId = context.chat_id
            isPrintMsg = False
        else:
            try:
                chatId = int(p[1])
            except:
                try:
                    chatId = int(p[1][:-1])
                except:
                    await context.edit("请输入正确的chatId")
                    await delayDelete(context)
                    return
            isPrintMsg = p[1][-1:] in "!！"
        await clearHistory(context, chatId, isPrintMsg)
    elif p[0] == "reset":
        ignoreChat = ""
        allowPrivateChat = ""
        expiredTime = 1800
        sleepTime = 60
        keys = redis.keys("selfDestruct:*")
        for key in keys:
            redis.delete(key)
        await context.edit("重置所有配置完成")
        await delayDelete(context)
    elif p[0] == "trace":
        reply = await context.get_reply_message()
        chatId = context.chat_id
        try:
            emoji = p[1]
            isDelete = emoji[0] == "-"
        except:
            emoji = ""
            isDelete = False
        # 处理列出所有配置
        if emoji:
            if emoji in "!！":
                await printConfig4Trace(context)
                return
            elif emoji == "gm":
                try:
                    if p[2] == "true":
                        globalMatch = True
                        redis.set(globalMatchRedisKey, "true")
                        msg = "已开启全局匹配"
                    else:
                        globalMatch = False
                        redis.delete(globalMatchRedisKey)
                        msg = "已关闭全局匹配"
                    await context.edit(msg)
                except:
                    await context.edit("请正确输入指令：sfd trace gm <true/false>，开关全局匹配")
                await delayDelete(context)
                return
            elif emoji == "reset":
                traceKeywordsDict = defaultdict()
                globalMatch = False
                keys = redis.keys(f'{traceRedisKey}:*')
                for key in keys:
                    redis.delete(key)
                await context.edit("重置所有配置完成")
                await delayDelete(context)

        if isDelete:
            emoji = emoji[1:]
        if len(p) == 3:
            # 处理有关键词的情况
            kw = p[2]
            # 参数校验
            if ",," in kw:
                await context.edit("请勿连续使用2个以上,号")
                await delayDelete(context)
                return
            # 判断类型：text，regex
            isRegex = False
            if kw.startswith("reg/"):
                try:
                    re.compile(kw[4:])
                    isRegex = True
                except:
                    await context.edit("请输入正确的正则表达式！")
                    await delayDelete(context)
                    return
            # 根据是否回复消息，确定是否全局关键字
            if reply:
                key = f'{traceRedisKey}:keywords:{chatId}'
            else:
                key = f'{traceRedisKey}:keywords'
            globalStr = "当前会话" if reply else "全局"
            keywordTypeStr = "正则" if isRegex else "关键字"
            kws = redis.get(key)
            kws = kws.decode().split(";") if kws else []
            if isDelete:
                # 遍历配置，找到对应emoji的配置，删除对应关键字
                kws = dealWithKeyword(emoji, kw, kws, isDelete)
                if kws:
                    redis.set(key, kws)
                    traceKeywordsDict[key] = kws
                else:
                    redis.delete(key)
                    del traceKeywordsDict[key]
                await context.edit(f'已删除{globalStr}{keywordTypeStr}：{kw}')
            else:
                # 遍历配置，找到对应emoji配置，追加
                kws = dealWithKeyword(emoji, kw, kws, isDelete)
                # 尝试点赞，如果emoji不合法则不添加
                try:
                    await sendReaction(context.client, chatId, context.message.id, [types.ReactionEmoji(emoticon=emoji)])
                    redis.set(key, kws)
                    traceKeywordsDict[key] = kws
                    await context.edit(f'已添加{globalStr}{keywordTypeStr}：{kw}，自动用{emoji}点赞')
                except Exception as e:
                    if str(e).startswith("Invalid reaction"):
                        await context.edit("设置自动点赞失败，请配置合法emoji")
                        await delayDelete(context)
                        return
                    raise e
            await delayDelete(context)
            return
        elif len(p) == 2:
            # 处理只传emoji的情况
            if reply:
                key = f'{traceRedisKey}:{chatId}:{reply.sender_id}'
                redis.set(key, emoji)
                traceKeywordsDict[key] = emoji
                try:
                    await sendReaction(context.client, chatId, reply.id, [types.ReactionEmoji(emoticon=emoji)])
                    await context.edit(f'已对他开启自动点赞：{emoji}')
                except Exception as e:
                    redis.delete(key)
                    del traceKeywordsDict[key]
                    if str(e).startswith("Invalid reaction"):
                        await context.edit("设置自动点赞失败，请配置合法emoji")
                        await delayDelete(context)
                        return
                    raise e
            else:
                await context.edit("请回复一条消息")
            await delayDelete(context)
            return
        # 以上都不是，判断是否回复人，回复了就取消对他自动点赞
        if reply:
            key = f'{traceRedisKey}:{chatId}:{reply.sender_id}'
            if redis.get(key):
                redis.delete(key)
                del traceKeywordsDict[key]
                await context.edit("已取消对他自动点赞")
            else:
                await context.edit("未对他自动点赞无需删除")
            await delayDelete(context)
            return
        await context.edit("请认真阅读help说明，输入正确指令")
        await delayDelete(context)
        return


def convert2Str(configs):
    if not configs:
        return ""
    msg = ""
    for config in configs.split(";"):
        conf = config.split(":")
        kws = ""
        for kw in conf[1].split(",,"):
            if not kw:
                continue
            kws = f'{kws}, `{kw}`'
        msg = f'{msg}{conf[0]}: {kws[2:]}\n'
    return msg


async def printConfig4Trace(context):
    globalKeywords = ""
    chatKeywords = ""
    keywords = ""
    for key in traceKeywordsDict:
        if not key:
            return
        ks = key.split(":")
        if len(ks) == 2:
            # trace:keywords
            if ks[1] != "keywords":
                continue
            globalKeywords = f'{globalKeywords}{convert2Str(traceKeywordsDict[key])}'
        elif ks[1] == "keywords":
            # trace:keywords:-1001589058412
            chatKeywords = f'{chatKeywords}{ks[2]}:\n{convert2Str(traceKeywordsDict[key])}'
        else:
            # trace:-1001589058412:12341512
            keywords = f'{keywords}{ks[1]}([TA](tg://user?id={ks[2]})):{traceKeywordsDict[key]}\n'
    await context.edit(f'全局关键字/正则配置：\n{globalKeywords}\n会话关键字/正则配置：\n{chatKeywords}\n针对个人配置：\n{keywords}')
    await sleep(20)
    await delayDelete(context)


def dealWithKeyword(emoji, kw, kws, isDelete):
    if not isDelete and not kws:
        return f'{emoji}:,,{kw}'
    removeIds = []
    isFound = False
    for i in range(len(kws)):
        k = kws[i]
        split = k.split(":")
        e = split[0]
        if e != emoji:
            continue
        isFound = True
        if isDelete:
            if f',,{kw},,' in f'{split[1]},,':
                keys = split[1].split(",,")
                keys.remove(kw)
                split[1] = f'{",,".join(keys)}'
                if not split[1].strip():
                    removeIds.append(i)
        else:
            if f',,{kw},,' not in f'{split[1]},,':
                split[1] = f'{split[1]},,{kw}'
        kws[i] = ":".join(split)
        break
    if not isFound:
        kws.append(f'{emoji}:,,{kw}')
    if removeIds:
        for i in removeIds:
            del kws[i]
    kws = ";".join(kws)
    return kws


async def clearHistory(context, chatId, isPrintMsg):
    await context.edit("正在统计消息数量。。。")
    msgs = []
    try:
        async for msg in context.client.iter_messages(chatId, from_user="me", reverse=True):
            msgs.append(msg)
    except:
        await context.edit("无法找到该会话，请确认是否已退出或者不存在。")
        await delayDelete(context)
    if msgs:
        count = 0
        total = len(msgs)
        step = int(total / 10)
        step = total if step == 0 else step
        await context.edit(f'共找到{total}条消息，开始删除。。。')
        for message in msgs:
            if isPrintMsg:
                text = message.text if message.text else "空文本消息"
                cid = f'{chatId}'[4:] if f'{chatId}'.startswith("-100") else chatId
                await bot.send_message(context.chat_id, f'[{text}](https://t.me/c/{cid}/{message.id})')
            await message.delete()
            count += 1
            if count % step == 1:
                await context.edit(f'删除中，进度{count}/{total}')
        await context.edit(f'成功删除`{chatId}`会话{count}条消息')
        await sleep(1)
    else:
        await context.edit("没有找到消息")
    await delayDelete(context)


async def delayDelete(context):
    await sleep(2)
    await context.delete()


@listener(incoming=False, outgoing=True, ignore_edited=True)
async def dealWithMessage4Sfd(context):
    chatId = context.chat_id
    msgId = context.message.id
    isAllowPublicChat = f',{chatId},' not in f'{ignoreChat},'
    isAllowPrivateChat = f',{chatId},' in f'{allowPrivateChat},'
    isAllow = isAllowPublicChat if f'{chatId}'.startswith("-100") else isAllowPrivateChat
    if isAllow:
        expiredTime4Chat = await getExpiredTime4ChatId(chatId)
        redis.zadd(messageRedisKey, {f"{chatId},{msgId},{context.text}": int(time.time()) + expiredTime4Chat})


@listener(incoming=True, outgoing=False, ignore_edited=True)
async def traceMessage(context):
    chatId = context.chat_id
    senderId = context.sender_id
    # 获取当前会话关键字配置
    kws = traceKeywordsDict.get(f'{traceRedisKey}:keywords:{chatId}')
    isReturn = await dealWithKeywords4Trace(context, kws)
    if not globalMatch and isReturn:
        return
    # 获取全局关键字配置
    globalKws = traceKeywordsDict.get(f'{traceRedisKey}:keywords')
    isReturn = await dealWithKeywords4Trace(context, globalKws)
    if not globalMatch and isReturn:
        return
    # 获取当前会话发送者的配置
    emoticon = traceKeywordsDict.get(f'{traceRedisKey}:{chatId}:{senderId}')
    if not emoticon:
        return
    try:
        await sendReaction(context.client, chatId, context.message.id, [types.ReactionEmoji(emoticon=emoticon)])
    except Exception as e:
        logs.debug(f'exception: {e}')


async def dealWithKeywords4Trace(context, keywords):
    if not keywords:
        return False
    reactions = []
    text = context.message.text
    for kws in keywords.split(";"):
        kw = kws.split(":")
        ks = kw[1].split(",,")
        for k in ks:
            k = k.strip()
            if not k:
                continue
            if k.startswith("reg/"):
                # 正则
                k = re.compile(k[4:])
                if k.search(text):
                    reactions.append(types.ReactionEmoji(emoticon=kw[0]))
            elif k in text:
                reactions.append(types.ReactionEmoji(emoticon=kw[0]))
            if not globalMatch and len(reactions) == 1:
                break
        if not globalMatch and len(reactions) == 1:
            break

    if len(reactions) > 0:
        try:
            if len(reactions) > 3:
                reactions = reactions[-3:]
            await sendReaction(context.client, context.chat_id, context.message.id, reactions)
        except Exception as e:
            if str(e).startswith("The specified message ID is invalid or you can't do that operation on such message"):
                return True
            logs.debug(f'exception: {e}\n{reactions}')
    return False


async def sendReaction(client, chatId, messageId, emoticon):
    try:
        await client(
            functions.messages.SendReactionRequest(
                peer=chatId,
                msg_id=messageId,
                big=True,
                add_to_recent=True,
                reaction=emoticon
            )
        )
    except Exception as e:
        raise e


@AsyncTask(name="checkMessage")
async def checkMessage(client):
    while True:
        msg = redis.zrange(messageRedisKey, 0, 0, withscores=True)
        if msg:
            msg = msg[0]
            score = int(msg[1])
            msg = msg[0].decode().split(",")
            try:
                if int(time.time()) - score >= 0:
                    await client.delete_messages(entity=int(msg[0]), message_ids=[int(msg[1])])
                    redis.zpopmin(messageRedisKey, 1)
                    continue
            except Exception as e:
                if str(e).startswith("Cannot find any entity corresponding to"):
                    continue
                await log(f'请联系作者添加未处理异常：{str(e)}')
                redis.zpopmin(messageRedisKey, 1)
        await sleep(sleepTime)
