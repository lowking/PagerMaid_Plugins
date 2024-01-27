from asyncio import sleep
from datetime import timedelta

from pagermaid import bot, user_id
from pagermaid.listener import listener
from telethon.errors import rpcerrorlist


@listener(is_plugin=True, outgoing=True, command="portball",
          description="回复你要临时禁言的人的消息来实现XX秒或XX天的禁言",
          parameters="<理由>(空格)<时间/秒或天>")
async def portball(context):
    if context.is_group:
        reply = await context.get_reply_message()
        if reply:
            action = context.arguments.split()
            if reply.sender:
                if reply.sender.last_name is None:
                    last_name = ''
                else:
                    last_name = reply.sender.last_name
                if reply.sender.id == user_id:
                    await context.edit('无法禁言自己。')
                    return
            else:
                await context.edit('无法获取所回复的用户。')
                return

            if len(action) < 2:
                notification = await bot.send_message(context.chat_id, '格式是\n-portball 理由 时间\n真蠢', reply_to=context.id)
                await sleep(10)
                await notification.delete()
                try:
                    await context.delete()
                except:
                    pass
                return False

            ban_time = action[1].lower()
            if ban_time.endswith('d'):
                try:
                    days = int(ban_time[:-1])
                    if days < 1:
                        raise ValueError
                    time_in_seconds = days * 86400
                except ValueError:
                    notification = await bot.send_message(context.chat_id, '天数格式错误或太小，应为正整数', reply_to=context.id)
                    await sleep(10)
                    await notification.delete()
                    try:
                        await context.delete()
                    except:
                        pass
                    return False
            else:
                try:
                    time_in_seconds = int(ban_time)
                    if time_in_seconds < 60:
                        notification = await bot.send_message(context.chat_id, '诶呀不要小于60秒啦', reply_to=context.id)
                        await sleep(10)
                        await notification.delete()
                        try:
                            await context.delete()
                        except:
                            pass
                        return False
                except ValueError:
                    notification = await bot.send_message(context.chat_id, '秒数格式错误，应为数字', reply_to=context.id)
                    await sleep(10)
                    await notification.delete()
                    try:
                        await context.delete()
                    except:
                        pass
                    return False

            try:
                await bot.edit_permissions(context.chat_id, reply.sender.id,
                                           timedelta(seconds=time_in_seconds), send_messages=False,
                                           send_media=False, send_stickers=False, send_gifs=False, send_games=False,
                                           send_inline=False, send_polls=False, invite_users=False, change_info=False,
                                           pin_messages=False)
                # 构建禁言时长的展示字符串
                if ban_time.endswith('d'):
                    ban_duration = f'{ban_time[:-1]}天'  # 如果是天数，去掉'd'并添加'天'
                else:
                    ban_duration = f'{ban_time}秒'  # 如果是秒数，直接添加'秒'

                portball_message = await bot.send_message(
                    context.chat_id,
                    f'[{reply.sender.first_name}{last_name}](tg://user?id={reply.sender.id}) 由于 {action[0]} 被塞了{ban_duration}口球.\n'
                    f'到期自动拔出,无后遗症.',
                    reply_to=reply.id
                )
                await context.delete()
                await sleep(time_in_seconds)
                await portball_message.delete()
            except rpcerrorlist.UserAdminInvalidError:
                notification = await bot.send_message(context.chat_id, '错误：我没有管理员权限或我的权限比被封禁的人要小', reply_to=context.id)
                await sleep(10)
                await notification.delete()
            except rpcerrorlist.ChatAdminRequiredError:
                notification = await bot.send_message(context.chat_id, '错误：我没有管理员权限或我的权限比被封禁的人要小', reply_to=context.id)
                await sleep(10)
                await notification.delete()
            except OverflowError:
                notification = await bot.send_message(context.chat_id, '                错误：封禁值太大了', reply_to=context.id)
                await sleep(10)
                await notification.delete()
        else:
            notification = await bot.send_message(
                context.chat_id,
                '你好蠢诶，都没有回复人，我哪知道你要搞谁的事情……',
                reply_to=context.id)
            await sleep(10)
            await notification.delete()
    else:
        notification = await bot.send_message(
            context.chat_id,
            '你好蠢诶，又不是群组，怎么禁言啦！',
            reply_to=context.id)
        await sleep(10)
        await notification.delete()

    try:
        await context.delete()
    except:
        pass