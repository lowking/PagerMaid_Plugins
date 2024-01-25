import traceback
from asyncio import sleep
from io import BytesIO
from os import remove
from os.path import exists

from pagermaid import bot
from telethon.tl.types import MessageMediaPhoto, MessageMediaWebPage


def make_reply_msg(context, sourceText, prefix):
    tag = ""
    remark = ""
    # 获取标签
    if prefix and context.text.startswith(prefix):
        msgs = context.text[len(prefix):].split("！")
    else:
        msgs = context.text[1:].split("！")
    tag = msgs[0]
    if len(msgs) > 1:
        remark = "！".join(msgs[1:])

    if tag != "":
        # 支持多个标签
        tags = tag.split(",")
        if "，" in tag and len(tags) == 1:
            tags = tag.split("，")
        tag = ""
        for t in tags:
            if tag == "":
                tag = f"#{t}"
            else:
                tag = f"{tag} #{t}"

    if remark != "":
        separator = "\n\n"
        if sourceText == "":
            separator = ""
        remark = f"{remark}{separator}"

    return f"{tag}\n{remark}{sourceText}"


async def main(context, sender_ids, forward_target, prefix):
    sender_ids = f"{sender_ids}"
    if forward_target is not None:
        # 判断发送者是否有权限
        if f"{context.sender_id}" in sender_ids or sender_ids == "999":
            reply = await context.get_reply_message()
            if not reply:
                return ""
            isShowDetail = "sdtl" in context.text
            if isShowDetail:
                await context.client.send_message(context.chat_id, f"以下是目标消息：{reply}")
            sourceCmd = context.text[1:].strip()
            isSourceCmdNotEmpty = False
            if sourceCmd != "":
                isSourceCmdNotEmpty = True
                sourceCmd = f"`{sourceCmd}`\n"
            await context.edit(f"{sourceCmd}处理中。。。")
            target = reply
            # 判断消息类型
            try:
                isNeedDeal = True
                resultMsg = make_reply_msg(context, target.text, prefix).strip()
                if target.media is not None and not isinstance(target.media, MessageMediaWebPage):
                    try:
                        mediaType = target.media.document.mime_type.split('/')
                    except:
                        mediaType = []
                    if isinstance(target.media, MessageMediaPhoto):
                        await context.edit(f"{sourceCmd}识别到是图片，正在处理。。。")
                        # 图片类型
                        isNeedDeal = True
                        if resultMsg != "" and isSourceCmdNotEmpty:
                            photo = BytesIO()
                            photo.name = f"../forward-photo.png"
                            await context.edit(f"{sourceCmd}图片下载中。。。")
                            await bot.download_media(target.photo, photo)
                            with open(photo.name, "wb") as f:
                                f.write(photo.getvalue())
                            await context.edit(f"{sourceCmd}下载图片完成")
                            await bot.send_file(forward_target, photo.name, caption=resultMsg, force_document=False)
                            await context.edit(f"转发成功")
                            remove(photo.name)
                        else:
                            isNeedDeal = False
                    elif "png" in mediaType:
                        # 图片文件
                        await context.edit(f"{sourceCmd}识别到图片文件，正在处理。。。")
                        isNeedDeal = True
                        if resultMsg != "" and isSourceCmdNotEmpty:
                            file = BytesIO()
                            # 遍历获取文件名
                            for attr in target.media.document.attributes:
                                try:
                                    file.name = f"../{attr.file_name}"
                                    break
                                except:
                                    file.name = f"picfile.png"
                            if exists(file.name):
                                file.name = f"../suffix-{file.name}"
                            await context.edit(f"{sourceCmd}图片文件下载中。。。")
                            await bot.download_file(target.media.document, file)
                            with open(file.name, "wb") as f:
                                f.write(file.getvalue())
                            await context.edit(f"{sourceCmd}下载图片文件完成")
                            await bot.send_file(forward_target, file.name, caption=resultMsg, force_document=True)
                            await context.edit(f"转发成功")
                            remove(file.name)
                        else:
                            isNeedDeal = False
                    elif "webp" in mediaType or "x-tgsticker" in mediaType:
                        # 贴纸
                        await context.edit(f"{sourceCmd}识别到贴纸，准备转发。。。")
                        isNeedDeal = False
                    elif mediaType != "":
                        # 脚本文件
                        await context.edit(f"{sourceCmd}识别到文件，正在处理。。。")
                        isNeedDeal = True
                        if resultMsg != "" and isSourceCmdNotEmpty:
                            file = BytesIO()
                            # 遍历获取文件名
                            for attr in target.media.document.attributes:
                                try:
                                    file.name = f"../{attr.file_name}"
                                    break
                                except:
                                    pass
                            if exists(file.name):
                                file.name = f"../suffix-{file.name}"
                            await context.edit(f"{sourceCmd}文件下载中。。。")
                            await bot.download_file(target.media.document, file)
                            with open(file.name, "wb") as f:
                                f.write(file.getvalue())
                            await context.edit(f"{sourceCmd}下载文件完成")
                            await bot.send_file(forward_target, file.name, caption=resultMsg)
                            await context.edit(f"转发成功")
                            remove(file.name)
                        else:
                            isNeedDeal = False
                    else:
                        await context.edit(f"{sourceCmd}未知消息类型直接转发，请到转发处查看详情")
                        await context.client.send_message(forward_target, f"未知：{target}")
                        isNeedDeal = False
                else:
                    await context.edit(f"{sourceCmd}识别到纯文本")
                    await context.client.send_message(forward_target, resultMsg)
                    await context.edit(f"转发成功")

                if not isNeedDeal:
                    await target.forward_to(forward_target)
                    await context.edit(f"转发成功")
            except:
                s = traceback.format_exc()
                await context.client.send_message(context.chat_id, f"{s}\n以下是目标消息：{target}")
            await sleep(5)
            await context.delete()

    return ""
