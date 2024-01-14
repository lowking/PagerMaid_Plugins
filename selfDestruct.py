import time
import traceback

from asyncio import sleep
from pagermaid import redis, redis_status, version, log, bot
from pagermaid.listener import listener
from pagermaid.utils import alias_command, pip_install

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


def loadChatConfig():
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


loadChatConfig()


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


@listener(is_plugin=True, outgoing=True, command=alias_command("sfd"),
          diagnostics=True,
          description="""
将消息id存入redis有序队列按发送时间排序，之后每隔一段时间获取队列中要到期的消息然后删除。

说明：
sfd [chatId]，查看当前会话设置或者指定chatId
sfd time 60，设置检查过期间隔时间为60秒，默认为60秒
sfd exp 60 [chatId]，设置过期时间为60秒（后面可选指定id），默认为1800秒（30分钟）
sfd <on/off> [chatId]，设置当前会话开启/关闭自毁，或者指定id，默认所有非私聊会话自动开启，私聊自动关闭
sfd pin，回复一条自己发的消息，该消息将不会被删除
sfd <!/！>，查看禁用自毁会话列表
""",
          parameters="")
async def selfDestruct(context):
    global sleepTime, expiredTime, ignoreChat
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
        try:
            expiredTime4Chat = int(p[1])
        except:
            await context.edit("设置过期时间参数错误，请输入数字")
            return
        if len(p) >= 3:
            try:
                chatId = f':{int(p[2])}'
            except:
                await context.edit("指定chatId格式错误，请输入数字")
                return
        if chatId:
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
        loadChatConfig()
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
        loadChatConfig()
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


async def delayDelete(context):
    await sleep(2)
    await context.delete()


@listener(incoming=False, outgoing=True, ignore_edited=True)
async def dealWithMessage(context):
    chatId = context.chat_id
    msgId = context.message.id
    isAllowPublicChat = f',{chatId},' not in f'{ignoreChat},'
    isAllowPrivateChat = f',{chatId},' in f'{allowPrivateChat},'
    isAllow = isAllowPublicChat if f'{chatId}'.startswith("-100") else isAllowPrivateChat
    if isAllow:
        expiredTime4Chat = await getExpiredTime4ChatId(chatId)
        redis.zadd(messageRedisKey, {f"{chatId},{msgId},{context.text}": int(time.time()) + expiredTime4Chat})


async def checkMessage():
    while True:
        msg = redis.zrange(messageRedisKey, 0, 0, withscores=True)
        if msg:
            msg = msg[0]
            score = int(msg[1])
            msg = msg[0].decode().split(",")
            try:
                if int(time.time()) - score >= 0:
                    await bot.delete_messages(entity=int(msg[0]), message_ids=[int(msg[1])])
                    redis.zpopmin(messageRedisKey, 1)
                    continue
            except Exception as e:
                if str(e).startswith("Cannot find any entity corresponding to"):
                    continue
                await log(f'请联系作者添加未处理异常：{str(e)}')
                redis.zpopmin(messageRedisKey, 1)
        await sleep(sleepTime)


bot.loop.create_task(checkMessage())
