""" PagerMaid module to handle sticker collection. """
import json
import re
from collections import defaultdict
from os import remove
from os.path import exists
from random import randint
from struct import error as StructError

from PIL import Image
from pagermaid import redis, config, bot, log, redis_status
from pagermaid.listener import listener
from pagermaid.utils import alias_command
from requests import get
from telethon.errors.rpcerrorlist import ChatSendStickersForbiddenError
from telethon.events import NewMessage
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.patched import Message
from telethon.tl.types import Channel, MessageEntityMentionName, MessageEntityPhone, MessageEntityBotCommand

try:
    git_source = config['git_source']
except:
    git_source = "https://raw.githubusercontent.com/lowking/PagerMaid_Plugins/master/"
positions = {
    "1": [297, 288],
    "2": [85, 368],
    "3": [127, 105],
    "4": [76, 325],
    "5": [256, 160],
    "6": [298, 22],
}
notifyStrArr = {
    "6": "踢人",
}
# json中的扩展配置
extensionConfig = {}
# 指令接收到的扩展属性
prop = {}
max_number = len(positions)
configFilePath = 'plugins/eat/config.json'
configFileRemoteUrlKey = "eat.configFileRemoteUrl"

defaultConfig = ""
if redis_status():
    defaultConfig = redis.get("eat.default-config").decode()


async def get_full_id(object_n):
    if isinstance(object_n, Channel):
        return (await bot(GetFullChannelRequest(object_n.id))).full_chat.id  # noqa
    return (await bot(GetFullUserRequest(object_n.id))).full_user.id


async def eat_it(context, uid, base, mask, photo, number, layer=0):
    global prop
    isSwap = False
    isRandomAngle = False
    try:
        isSwap = extensionConfig.get(str(number), {}).get("isSwap", isSwap)

        isRandomAngle = extensionConfig.get(str(number), {}).get("isRandomAngle", isRandomAngle)
        isRandomAngle = prop.get("isRandomAngle") if prop.get("isRandomAngle") else isRandomAngle
    except:
        pass

    mask_size = mask.size
    photo_size = photo.size
    if mask_size[0] < photo_size[0] and mask_size[1] < photo_size[1]:
        scale = photo_size[1] / mask_size[1]
        photo = photo.resize((int(photo_size[0] / scale), int(photo_size[1] / scale)), Image.LANCZOS)
    photo = photo.crop((0, 0, mask_size[0], mask_size[1]))
    # 随机角度旋转头像
    if isRandomAngle:
        photo = photo.rotate(randint(1, 359))
    mask1 = Image.new('RGBA', mask_size)
    mask1.paste(photo, mask=mask)
    numberPosition = positions[str(number)]
    # 处理头像，放到和背景同样大小画布的特定位置
    if isSwap:
        photoBg = Image.new('RGBA', base.size)
        photoBg.paste(mask1, (numberPosition[0], numberPosition[1]), mask1)
        photoBg.paste(base, (0, 0), base)
        base = photoBg
    else:
        base.paste(mask1, (numberPosition[0], numberPosition[1]), mask1)

    # 增加判断是否有第二个头像孔
    isContinue = len(numberPosition) > 2 and layer == 0
    if isContinue:
        await context.client.download_profile_photo(
            uid,
            "plugins/eat/" + str(uid) + ".jpg",
            download_big=True
        )
        try:
            markImg = Image.open("plugins/eat/" + str(uid) + ".jpg")
            maskImg = Image.open("plugins/eat/mask" + str(numberPosition[2]) + ".png").convert("RGBA")
        except:
            await context.edit(f"图片模版加载出错，请检查并更新配置：mask{str(numberPosition[2])}.png")
            return base
        prop = {}
        base = await eat_it(context, uid, base, maskImg, markImg, numberPosition[2], layer + 1)

    temp = base.size[0] if base.size[0] > base.size[1] else base.size[1]
    if temp != 512:
        scale = 512 / temp
        base = base.resize((int(base.size[0] * scale), int(base.size[1] * scale)), Image.LANCZOS)

    return base


async def updateConfig(context, forceDownload=False):
    ret = 0
    configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
    if configFileRemoteUrl:
        if not exists(configFilePath):
            f = open(configFilePath, 'w')
            f.close()
        urls = configFileRemoteUrl.decode().split(",")
        try:
            with open(configFilePath, 'r', encoding="utf-8") as source:
                localConfigJson = json.load(source)
        except:
            localConfigJson = json.loads('{"positions": {}, "notifies": {}, "extensionConfig": {}, '
                                         '"needDownloadFileList": []}')
        with open(configFilePath, 'w+', encoding="utf-8") as ms:
            for url in urls:
                try:
                    resp = get(url)
                except:
                    ret = -1
                    break
                remoteConfigJson = json.loads(resp.content)
                # 将文件内容转成json，与下载的内容合并
                localStr = json.dumps(localConfigJson["positions"])
                remoteStr = json.dumps(remoteConfigJson["positions"])
                localConfigJson['positions'] = mergeDict(json.loads(localStr), json.loads(remoteStr))
                localStr = json.dumps(localConfigJson["notifies"])
                remoteStr = json.dumps(remoteConfigJson["notifies"])
                localConfigJson['notifies'] = mergeDict(json.loads(localStr), json.loads(remoteStr))
                localStr = json.dumps(localConfigJson["extensionConfig"])
                remoteStr = json.dumps(remoteConfigJson["extensionConfig"])
                localConfigJson['extensionConfig'] = mergeDict(json.loads(localStr), json.loads(remoteStr))
                localStr = json.dumps(localConfigJson["needDownloadFileList"])
                remoteStr = json.dumps(remoteConfigJson["needDownloadFileList"])
                localConfigJson['needDownloadFileList'] = list(set(json.loads(localStr)).union(set(json.loads(remoteStr))))
            ms.write(json.dumps(localConfigJson, ensure_ascii=False))
        if ret == 0:
            return await loadConfigFile(context, forceDownload)
    return ret


def downloadFileFromUrl(url, filepath):
    try:
        resp = get(url)
        with open(filepath, 'wb') as ms:
                ms.write(resp.content)
    except:
        return -1
    return 0


async def loadConfigFile(context, forceDownload=False):
    global positions, notifyStrArr, extensionConfig
    try:
        with open(configFilePath, 'r', encoding='utf8') as cf:
            # 读取已下载的配置文件
            remoteConfigJson = json.load(cf)
            # positionsStr = json.dumps(positions)
            # positions = json.loads(positionsStr)

            # 读取配置文件中的positions
            positionsStr = json.dumps(remoteConfigJson["positions"])
            data = json.loads(positionsStr)
            # 与预设positions合并
            positions = mergeDict(positions, data)

            # 读取配置文件中的notifies
            data = json.loads(json.dumps(remoteConfigJson["notifies"]))
            # 与预设positions合并
            notifyStrArr = mergeDict(notifyStrArr, data)

            # 读取配置文件中的extensionConfig
            try:
                data = json.loads(json.dumps(remoteConfigJson["extensionConfig"]))
                # 与预设extensionConfig合并
                extensionConfig = mergeDict(extensionConfig, data)
            except:
                # 新增扩展配置，为了兼容旧的配置文件更新不出错，无视异常
                pass

            # 读取配置文件中的needDownloadFileList
            data = json.loads(json.dumps(remoteConfigJson["needDownloadFileList"]))
            # 下载列表中的文件
            for fileUrl in data:
                try:
                    fsplit = fileUrl.split("/")
                    filePath = f"plugins/eat/{fsplit[len(fsplit) - 1]}"
                    if not exists(filePath) or forceDownload:
                        downloadFileFromUrl(fileUrl, filePath)

                except:
                    if context:
                        await context.edit(f"下载文件异常，url：{fileUrl}")
                    return -1
    except:
        return -1
    return 0


def mergeDict(d1, d2):
    dd = defaultdict(list)

    for d in (d1, d2):
        for key, value in d.items():
            dd[key] = value
    return dict(dd)


async def downloadFileByIds(ids, context):
    idsStr = f',{",".join(ids)},'
    try:
        with open(configFilePath, 'r', encoding='utf8') as cf:
            # 读取已下载的配置文件
            remoteConfigJson = json.load(cf)
            data = json.loads(json.dumps(remoteConfigJson["needDownloadFileList"]))
            # 下载列表中的文件
            sucSet = set()
            failSet = set()
            for fileurl in data:
                try:
                    fsplit = fileurl.split("/")
                    fileFullName = fsplit[len(fsplit) - 1]
                    fileName = re.sub(r"\d+", "", fileFullName).split(".")[0].replace("eat", "").replace("mask", "")
                    if f',{fileName},' in idsStr:
                        filePath = f"plugins/eat/{fileFullName}"
                        if downloadFileFromUrl(fileurl, filePath) == 0:
                            sucSet.add(fileName)
                        else:
                            failSet.add(fileName)
                except:
                    failSet.add(fileName)
                    await context.edit(f"下载文件异常，url：{fileurl}")
            notifyStr = "更新模版完成"
            if len(sucSet) > 0:
                notifyStr = f'{notifyStr}\n成功模版如下：{"，".join(sucSet)}'
            if len(failSet) > 0:
                notifyStr = f'{notifyStr}\n失败模版如下：{"，".join(failSet)}'
            await context.edit(notifyStr)
    except:
        await context.edit("更新下载模版图片失败，请确认配置文件是否正确")


@listener(is_plugin=True, outgoing=True, command=alias_command("eat"),
          description="生成一张 吃头像 图片\n"
                      "可选：当第二个参数是数字时，读取预存的配置；\n\n"
                      "当第二个参数是.开头时，头像旋转180°，并且判断r后面是数字则读取对应的配置生成\n\n"
                      "当第二个参数是/开头时，在/后面加url则从url下载配置文件保存到本地，如果就一个/，则直接更新配置文件，删除则是/delete；或者/后面加模版id"
                      "可以手动更新指定模版配置；如果想强制重新下载配置的所有图片，打//即可\n\n "
                      "当第二个参数是-开头时，在-后面加上模版id，即可设置默认模版-eat直接使用该模版，删除默认模版是-eat -\n\n"
                      "当第二个参数是!或者！开头时，列出当前可用模版",
          parameters="<username/uid> [随意内容]")
async def eat(context: NewMessage.Event):
    assert isinstance(context.message, Message)
    global prop
    if len(context.parameter) > 2:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    number, prop = await getConfigAndDealCommand(context)
    if not number:
        return

    if len(notifyStrArr) <= 6 and redis.get(configFileRemoteUrlKey):
        # 未初始化并且订阅了远程配置
        await initConfig(context)
    try:
        notifyStr = notifyStrArr[str(number)]
    except:
        notifyStr = "吃头像"
    await context.edit(f"正在生成 {notifyStr} 图片中 . . .")
    from_user = context.sender
    from_user_id = await get_full_id(from_user)
    target_user_id = await getTargetUserId(context, from_user)
    if not target_user_id:
        return
    photo = await getTargetUserAvatar(context, target_user_id)
    if not photo:
        await context.edit("此用户未设置头像或头像对您不可见。")
        return

    reply_to = context.message.reply_to_msg_id
    if exists("plugins/eat/" + str(target_user_id) + ".jpg"):
        for num in range(1, max_number + 1):
            print(num)
            if not exists('plugins/eat/eat' + str(num) + '.png'):
                resp = get(f'{git_source}eat/eat' + str(num) + '.png')
                with open('plugins/eat/eat' + str(num) + '.png', 'wb') as bg:
                    bg.write(resp.content)
            if not exists('plugins/eat/mask' + str(num) + '.png'):
                resp = get(f'{git_source}eat/mask' + str(num) + '.png')
                with open('plugins/eat/mask' + str(num) + '.png', 'wb') as ms:
                    ms.write(resp.content)
    else:
        await context.edit("此用户未设置头像或头像对您不可见。")
        return
    markImg = Image.open("plugins/eat/" + str(target_user_id) + ".jpg")
    try:
        eatImg = Image.open("plugins/eat/eat" + str(number) + ".png")
        maskImg = Image.open("plugins/eat/mask" + str(number) + ".png")
    except:
        await context.edit(f"图片模版加载出错，请检查并更新配置：{str(number)}")
        return

    if prop.get("diuRound", False):
        markImg = markImg.rotate(180)  # 对图片进行旋转
    result = await eat_it(context, from_user_id, eatImg, maskImg, markImg, number)
    result.save('plugins/eat/eat.webp')
    target_file = await context.client.upload_file("plugins/eat/eat.webp")
    try:
        remove("plugins/eat/" + str(target_user_id) + ".jpg")
        remove("plugins/eat/" + str(target_user_id) + ".png")
        remove("plugins/eat/" + str(from_user_id) + ".jpg")
        remove("plugins/eat/" + str(from_user_id) + ".png")
        remove("plugins/eat/eat.webp")
        remove(photo)
    except:
        pass
    if reply_to:
        try:
            await context.client.send_file(
                context.chat_id,
                target_file,
                link_preview=False,
                force_document=False,
                reply_to=reply_to
            )
            await context.delete()
            remove("plugins/eat/eat.webp")
            try:
                remove(photo)
            except:
                pass
            return
        except ChatSendStickersForbiddenError:
            await context.edit("此群组无法发送贴纸。")
    else:
        try:
            await context.client.send_file(
                context.chat_id,
                target_file,
                link_preview=False,
                force_document=False
            )
            await context.delete()
            remove("plugins/eat/eat.webp")
            try:
                remove(photo)
            except:
                pass
            return
        except ChatSendStickersForbiddenError:
            await context.edit("此群组无法发送贴纸。")


async def initConfig(context):
    # 加载配置
    if exists(configFilePath):
        if await loadConfigFile(context) != 0:
            if context:
                await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
            return 0
    return 1


async def getConfigAndDealCommand(context):
    global defaultConfig
    properties = {
        "diuRound": False,
        "isRandomAngle": False,
    }
    number = randint(1, max_number)
    try:
        p1 = 0
        p2 = 0
        if len(context.parameter) >= 1:
            p1 = context.parameter[0]
            p2 = await parameterPreprocessing(p1, p2, properties)
            if p1[0] == "-":
                if p2:
                    redis.set("eat.default-config", p2)
                    defaultConfig = p2
                    await context.edit(f"已经设置默认配置为：{p2}")
                else:
                    redis.delete("eat.default-config")
                    defaultConfig = ""
                    await context.edit(f"已经清空默认配置")
                return None, properties
            elif p1[0] == "/":
                await context.edit(f"正在更新远程配置文件")
                # 获取参数中的url
                p2 = "".join(p1[1:])
                if p2 == "delete":
                    redis.delete(configFileRemoteUrlKey)
                    await context.edit(f"已清空远程配置文件url")
                elif p2.startswith("http"):
                    # 下载文件
                    configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
                    if configFileRemoteUrl:
                        configFileRemoteUrl = configFileRemoteUrl.decode()
                        if p2 not in configFileRemoteUrl:
                            redis.set(configFileRemoteUrlKey, f"{p2},{configFileRemoteUrl}")
                    else:
                        redis.set(configFileRemoteUrlKey, p2)
                    if await updateConfig(context, False) != 0:
                        configFileRemoteUrl = configFileRemoteUrl.decode().replace(",", "\n")
                        await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确:\n{configFileRemoteUrl}")
                    else:
                        await context.edit(f"下载并加载配置文件成功")
                elif len(p2) == 1 and p2 == "/":
                    configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
                    if not configFileRemoteUrl:
                        await context.edit(f"你没有订阅远程配置文件，更新个🔨")
                        return None, properties
                    configFileRemoteUrl = configFileRemoteUrl.decode().replace(",", "\n")
                    if await updateConfig(context, True) != 0:
                        await context.edit(f"更新配置文件异常，请确认从远程下载的配置文件格式是否正确:\n{configFileRemoteUrl}")
                    else:
                        await context.edit(f"从远程更新配置文件成功")
                else:
                    # 根据传入模版id更新模版配置，多个用"，"或者","隔开
                    splitStr = "，"
                    if "," in p2:
                        splitStr = ","
                    ids = p2.split(splitStr)
                    if len(ids) > 0:
                        configFileRemoteUrl = redis.get(configFileRemoteUrlKey)
                        if not configFileRemoteUrl:
                            await context.edit(f"你没有订阅远程配置文件，更新个🔨")
                            return None, properties
                        configFileRemoteUrl = configFileRemoteUrl.decode().replace(",", "\n")
                        if await updateConfig(context, False) != 0:
                            await context.edit(f"更新配置文件异常，请确认从远程下载的配置文件格式是否正确:\n{configFileRemoteUrl}")
                        else:
                            await downloadFileByIds(ids, context)
                return None, properties
            elif p1[0] == "！" or p1[0] == "!":
                # 加载配置
                if exists(configFilePath) and len(positions) == 6:
                    if await loadConfigFile(context) != 0:
                        await context.edit(f"加载配置文件异常，请确认从远程下载的配置文件格式是否正确")
                        return None, properties
                txt = ""
                if len(positions) > 0:
                    noShowList = []
                    for key in positions:
                        try:
                            notifyStr = f"{notifyStrArr[key]}"
                        except:
                            notifyStr = ""
                        if notifyStr != "":
                            sKey = key.ljust(9, " ")
                            txt = f"{txt}\n{sKey}{notifyStr}"
                        else:
                            txt = f"{txt}\n{key}"
                        if len(positions[key]) > 2:
                            noShowList.append(positions[key][2])
                    for key in noShowList:
                        txt = txt.replace(f"\n{key}", "")
                await context.edit(f"目前已有的模版列表如下：{txt}")
                return None, properties
        if isinstance(p2, str):
            number = p2
        elif isinstance(p2, int) and p2 > 0:
            number = int(p2)
        elif not properties.get("diuRound") and ((isinstance(p1, int) and int(p1) > 0) or isinstance(p1, str)):
            try:
                number = int(p1)
            except:
                number = p1
        elif defaultConfig:
            try:
                defaultConfig = await parameterPreprocessing(defaultConfig, defaultConfig, properties)
                defaultConfig = int(defaultConfig)
            except:
                defaultConfig = str(defaultConfig)
            number = defaultConfig
        if str(number).isnumeric() and (max_number < number or number < 0):
            # 如果同时指定了id和模版
            if len(context.parameter) >= 2:
                number = context.parameter[1]
            else:
                number = defaultConfig
            try:
                number = await parameterPreprocessing(number, number, properties)
                number = int(number)
            except:
                number = str(number)
    except Exception as e:
        await log(f'解析异常：{e}')
        raise e
    try:
        number = str(number)
    except:
        pass

    return number, properties


async def parameterPreprocessing(p1, p2, properties):
    if len(p1) > 1:
        hasAdjust = False
        if p1[0] in ".。":
            properties["diuRound"] = True
            hasAdjust = True
        elif p1[0] in ",，":
            properties["isRandomAngle"] = True
            hasAdjust = True
        elif p1[0] == "-":
            hasAdjust = True
        if hasAdjust:
            try:
                p2 = int("".join(p1[1:]))
            except:
                # 可能也有字母的参数
                p2 = "".join(p1[1:])
    return p2


async def getTargetUserId(context, from_user):
    if context.reply_to_msg_id:
        # 有回复消息的话，获取回复消息的用户信息
        reply_message = await context.get_reply_message()
        target_user, target_user_id = await getTargetUserByContextAndReply(context, reply_message)
    else:
        user_raw = ""
        if len(context.parameter) == 1 or len(context.parameter) == 2:
            # 命令后面带有数字参数，用户设置成输入的数字
            user_raw = context.parameter[0]
            user = context.parameter[0]
            if user.isnumeric():
                user = int(user)
            else:
                user = from_user.id
        else:
            # 用户设置成发送者
            user = from_user.id
        if context.message.entities is not None:
            target_user, target_user_id = await getTargetUserByContextEntities(context, user, from_user)
        elif user_raw[:1] in [".", "/", "-", "!"]:
            target_user_id = await get_full_id(from_user)
        else:
            target_user_id = await getTargetUserByClientEntity(context, user)
    return target_user_id


async def getTargetUserAvatar(context, target_user_id):
    try:
        photo = await context.client.download_profile_photo(
            target_user_id,
            "plugins/eat/" + str(target_user_id) + ".jpg",
            download_big=True
        )
    except:
        return None
    return photo


async def getTargetUserByContextEntities(context, user, user_object):
    if isinstance(context.message.entities[0], MessageEntityMentionName):
        target_user = await context.client(GetFullUserRequest(context.message.entities[0].user_id))
        target_user_id = target_user.full_user.id
    elif isinstance(context.message.entities[0], MessageEntityPhone):
        if user > 0:
            target_user = await context.client(GetFullUserRequest(user))
            target_user_id = target_user.full_user.id
        else:
            target_user = await context.client(GetFullChannelRequest(user))
            target_user_id = target_user.full_chat.id
    elif isinstance(context.message.entities[0], MessageEntityBotCommand):
        target_user = await context.client(GetFullUserRequest(user_object.id))
        target_user_id = target_user.full_user.id
    else:
        return await context.edit("出错了呜呜呜 ~ 参数错误。")
    return target_user, target_user_id


async def getTargetUserByContextAndReply(context, reply_message):
    try:
        user_id = reply_message.sender_id
    except AttributeError:
        await context.edit("出错了呜呜呜 ~ 无效的参数。")
        return
    if user_id > 0:
        target_user = await context.client(GetFullUserRequest(user_id))
        target_user_id = target_user.full_user.id
    else:
        target_user = await context.client(GetFullChannelRequest(user_id))
        target_user_id = target_user.full_chat.id
    return target_user, target_user_id


async def getTargetUserByClientEntity(context, user):
    try:
        user_object = await context.client.get_entity(user)
        target_user_id = await get_full_id(user_object)
        return target_user_id
    except (TypeError, ValueError, OverflowError, StructError) as exception:
        if str(exception).startswith("Cannot find any entity corresponding to"):
            await context.edit("出错了呜呜呜 ~ 指定的用户不存在。")
            return
        if str(exception).startswith("No user has"):
            await context.edit("出错了呜呜呜 ~ 指定的道纹不存在。")
            return
        if str(exception).startswith("Could not find the input entity for") or isinstance(exception,
                                                                                          StructError):
            await context.edit("出错了呜呜呜 ~ 无法通过此 UserID 找到对应的用户。")
            return
        if isinstance(exception, OverflowError):
            await context.edit("出错了呜呜呜 ~ 指定的 UserID 已超出长度限制，您确定输对了？")
            return
        raise exception


bot.loop.create_task(initConfig(None))
