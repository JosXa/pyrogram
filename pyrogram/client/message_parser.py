# Pyrogram - Telegram MTProto API Client Library for Python
# Copyright (C) 2017-2018 Dan Tès <https://github.com/delivrance>
#
# This file is part of Pyrogram.
#
# Pyrogram is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pyrogram is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

from struct import pack

import pyrogram
from pyrogram.api import types, functions
from pyrogram.api.errors import StickersetInvalid
from .utils import encode

# TODO: Organize the code better?

ENTITIES = {
    types.MessageEntityMention.ID: "mention",
    types.MessageEntityHashtag.ID: "hashtag",
    types.MessageEntityBotCommand.ID: "bot_command",
    types.MessageEntityUrl.ID: "url",
    types.MessageEntityEmail.ID: "email",
    types.MessageEntityBold.ID: "bold",
    types.MessageEntityItalic.ID: "italic",
    types.MessageEntityCode.ID: "code",
    types.MessageEntityPre.ID: "pre",
    types.MessageEntityTextUrl.ID: "text_link",
    types.MessageEntityMentionName.ID: "text_mention"
}


def parse_entities(entities: list, users: dict) -> list:
    output_entities = []

    for entity in entities:
        entity_type = ENTITIES.get(entity.ID, None)

        if entity_type:
            output_entities.append(pyrogram.MessageEntity(
                type=entity_type,
                offset=entity.offset,
                length=entity.length,
                url=getattr(entity, "url", None),
                user=parse_user(
                    users.get(
                        getattr(entity, "user_id", None),
                        None
                    )
                )
            ))

    return output_entities


def parse_chat_photo(photo):
    if not isinstance(photo, (types.UserProfilePhoto, types.ChatPhoto)):
        return None

    if not isinstance(photo.photo_small, types.FileLocation):
        return None

    if not isinstance(photo.photo_big, types.FileLocation):
        return None

    loc_small = photo.photo_small
    loc_big = photo.photo_big

    return pyrogram.ChatPhoto(
        small_file_id=encode(
            pack(
                "<iiqqqqi", 0, loc_small.dc_id, 0, 0, loc_small.volume_id,
                loc_small.secret, loc_small.local_id
            )
        ),
        big_file_id=encode(
            pack(
                "<iiqqqqi", 0, loc_big.dc_id, 0, 0, loc_big.volume_id,
                loc_big.secret, loc_big.local_id
            )
        )
    )


def parse_user(user: types.User) -> pyrogram.User or None:
    return pyrogram.User(
        id=user.id,
        is_bot=user.bot,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.lang_code,
        phone_number=user.phone,
        photo=parse_chat_photo(user.photo)
    ) if user else None


def parse_chat(message: types.Message, users: dict, chats: dict) -> pyrogram.Chat:
    if isinstance(message.to_id, types.PeerUser):
        return parse_user_chat(users[message.to_id.user_id if message.out else message.from_id])
    elif isinstance(message.to_id, types.PeerChat):
        return parse_chat_chat(chats[message.to_id.chat_id])
    else:
        return parse_channel_chat(chats[message.to_id.channel_id])


def parse_user_chat(user: types.User) -> pyrogram.Chat:
    return pyrogram.Chat(
        id=user.id,
        type="private",
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        photo=parse_chat_photo(user.photo)
    )


def parse_chat_chat(chat: types.Chat) -> pyrogram.Chat:
    return pyrogram.Chat(
        id=-chat.id,
        type="group",
        title=chat.title,
        all_members_are_administrators=not chat.admins_enabled,
        photo=parse_chat_photo(chat.photo)
    )


def parse_channel_chat(channel: types.Channel) -> pyrogram.Chat:
    return pyrogram.Chat(
        id=int("-100" + str(channel.id)),
        type="supergroup" if channel.megagroup else "channel",
        title=channel.title,
        username=channel.username,
        photo=parse_chat_photo(channel.photo)
    )


def parse_thumb(thumb: types.PhotoSize or types.PhotoCachedSize) -> pyrogram.PhotoSize or None:
    if isinstance(thumb, (types.PhotoSize, types.PhotoCachedSize)):
        loc = thumb.location

        if isinstance(thumb, types.PhotoSize):
            file_size = thumb.size
        else:
            file_size = len(thumb.bytes)

        if isinstance(loc, types.FileLocation):
            return pyrogram.PhotoSize(
                file_id=encode(
                    pack(
                        "<iiqqqqi",
                        0,
                        loc.dc_id,
                        0,
                        0,
                        loc.volume_id,
                        loc.secret,
                        loc.local_id
                    )
                ),
                width=thumb.w,
                height=thumb.h,
                file_size=file_size
            )


# TODO: Reorganize code, maybe split parts as well
def parse_message(
        client,
        message: types.Message,
        users: dict,
        chats: dict,
        replies: int = 1
) -> pyrogram.Message:
    entities = parse_entities(message.entities, users)

    forward_from = None
    forward_from_chat = None
    forward_from_message_id = None
    forward_signature = None
    forward_date = None

    forward_header = message.fwd_from  # type: types.MessageFwdHeader

    if forward_header:
        forward_date = forward_header.date

        if forward_header.from_id:
            forward_from = parse_user(users[forward_header.from_id])
        else:
            forward_from_chat = parse_channel_chat(chats[forward_header.channel_id])
            forward_from_message_id = forward_header.channel_post
            forward_signature = forward_header.post_author

    photo = None
    location = None
    contact = None
    venue = None
    audio = None
    voice = None
    video = None
    video_note = None
    sticker = None
    document = None

    media = message.media

    if media:
        if isinstance(media, types.MessageMediaPhoto):
            photo = media.photo

            if isinstance(photo, types.Photo):
                sizes = photo.sizes
                photo_sizes = []

                for size in sizes:
                    if isinstance(size, (types.PhotoSize, types.PhotoCachedSize)):
                        loc = size.location

                        if isinstance(size, types.PhotoSize):
                            file_size = size.size
                        else:
                            file_size = len(size.bytes)

                        if isinstance(loc, types.FileLocation):
                            photo_size = pyrogram.PhotoSize(
                                file_id=encode(
                                    pack(
                                        "<iiqqqqi",
                                        2,
                                        loc.dc_id,
                                        photo.id,
                                        photo.access_hash,
                                        loc.volume_id,
                                        loc.secret,
                                        loc.local_id
                                    )
                                ),
                                width=size.w,
                                height=size.h,
                                file_size=file_size,
                                date=photo.date
                            )

                            photo_sizes.append(photo_size)

                photo = photo_sizes
        elif isinstance(media, types.MessageMediaGeo):
            geo_point = media.geo

            if isinstance(geo_point, types.GeoPoint):
                location = pyrogram.Location(
                    longitude=geo_point.long,
                    latitude=geo_point.lat
                )
        elif isinstance(media, types.MessageMediaContact):
            contact = pyrogram.Contact(
                phone_number=media.phone_number,
                first_name=media.first_name,
                last_name=media.last_name or None,
                user_id=media.user_id or None
            )
        elif isinstance(media, types.MessageMediaVenue):
            venue = pyrogram.Venue(
                location=pyrogram.Location(
                    longitude=media.geo.long,
                    latitude=media.geo.lat
                ),
                title=media.title,
                address=media.address,
                foursquare_id=media.venue_id or None
            )
        elif isinstance(media, types.MessageMediaDocument):
            doc = media.document

            if isinstance(doc, types.Document):
                attributes = {type(i): i for i in doc.attributes}

                file_name = getattr(
                    attributes.get(
                        types.DocumentAttributeFilename, None
                    ), "file_name", None
                )

                if types.DocumentAttributeAudio in attributes:
                    audio_attributes = attributes[types.DocumentAttributeAudio]

                    if audio_attributes.voice:
                        voice = pyrogram.Voice(
                            file_id=encode(
                                pack(
                                    "<iiqq",
                                    3,
                                    doc.dc_id,
                                    doc.id,
                                    doc.access_hash
                                )
                            ),
                            duration=audio_attributes.duration,
                            mime_type=doc.mime_type,
                            file_size=doc.size,
                            thumb=parse_thumb(doc.thumb),
                            file_name=file_name,
                            date=doc.date
                        )
                    else:
                        audio = pyrogram.Audio(
                            file_id=encode(
                                pack(
                                    "<iiqq",
                                    9,
                                    doc.dc_id,
                                    doc.id,
                                    doc.access_hash
                                )
                            ),
                            duration=audio_attributes.duration,
                            performer=audio_attributes.performer,
                            title=audio_attributes.title,
                            mime_type=doc.mime_type,
                            file_size=doc.size,
                            thumb=parse_thumb(doc.thumb),
                            file_name=file_name,
                            date=doc.date
                        )
                elif types.DocumentAttributeAnimated in attributes:
                    document = pyrogram.Document(
                        file_id=encode(
                            pack(
                                "<iiqq",
                                10,
                                doc.dc_id,
                                doc.id,
                                doc.access_hash
                            )
                        ),
                        thumb=parse_thumb(doc.thumb),
                        file_name=file_name,
                        mime_type=doc.mime_type,
                        file_size=doc.size,
                        date=doc.date
                    )
                elif types.DocumentAttributeVideo in attributes:
                    video_attributes = attributes[types.DocumentAttributeVideo]

                    if video_attributes.round_message:
                        video_note = pyrogram.VideoNote(
                            file_id=encode(
                                pack(
                                    "<iiqq",
                                    13,
                                    doc.dc_id,
                                    doc.id,
                                    doc.access_hash
                                )
                            ),
                            length=video_attributes.w,
                            duration=video_attributes.duration,
                            thumb=parse_thumb(doc.thumb),
                            file_size=doc.size,
                            file_name=file_name,
                            mime_type=doc.mime_type,
                            date=doc.date
                        )
                    else:
                        video = pyrogram.Video(
                            file_id=encode(
                                pack(
                                    "<iiqq",
                                    4,
                                    doc.dc_id,
                                    doc.id,
                                    doc.access_hash
                                )
                            ),
                            width=video_attributes.w,
                            height=video_attributes.h,
                            duration=video_attributes.duration,
                            thumb=parse_thumb(doc.thumb),
                            mime_type=doc.mime_type,
                            file_size=doc.size,
                            file_name=file_name,
                            date=doc.date
                        )
                elif types.DocumentAttributeSticker in attributes:
                    image_size_attributes = attributes[types.DocumentAttributeImageSize]
                    sticker_attribute = attributes[types.DocumentAttributeSticker]

                    if isinstance(sticker_attribute.stickerset, types.InputStickerSetID):
                        try:
                            set_name = client.send(
                                functions.messages.GetStickerSet(sticker_attribute.stickerset)
                            ).set.short_name
                        except StickersetInvalid:
                            set_name = None
                    else:
                        set_name = None

                    sticker = pyrogram.Sticker(
                        file_id=encode(
                            pack(
                                "<iiqq",
                                8,
                                doc.dc_id,
                                doc.id,
                                doc.access_hash
                            )
                        ),
                        width=image_size_attributes.w,
                        height=image_size_attributes.h,
                        thumb=parse_thumb(doc.thumb),
                        # TODO: mask_position
                        set_name=set_name,
                        emoji=sticker_attribute.alt or None,
                        file_size=doc.size,
                        mime_type=doc.mime_type,
                        file_name=file_name,
                        date=doc.date
                    )
                else:
                    document = pyrogram.Document(
                        file_id=encode(
                            pack(
                                "<iiqq",
                                5,
                                doc.dc_id,
                                doc.id,
                                doc.access_hash
                            )
                        ),
                        thumb=parse_thumb(doc.thumb),
                        file_name=file_name,
                        mime_type=doc.mime_type,
                        file_size=doc.size,
                        date=doc.date
                    )
        else:
            media = None

    m = pyrogram.Message(
        message_id=message.id,
        date=message.date,
        chat=parse_chat(message, users, chats),
        from_user=parse_user(users.get(message.from_id, None)),
        text=message.message or None if media is None else None,
        caption=message.message or None if media is not None else None,
        entities=entities or None if media is None else None,
        caption_entities=entities or None if media is not None else None,
        author_signature=message.post_author,
        forward_from=forward_from,
        forward_from_chat=forward_from_chat,
        forward_from_message_id=forward_from_message_id,
        forward_signature=forward_signature,
        forward_date=forward_date,
        edit_date=message.edit_date,
        media_group_id=message.grouped_id,
        photo=photo,
        location=location,
        contact=contact,
        venue=venue,
        audio=audio,
        voice=voice,
        video=video,
        video_note=video_note,
        sticker=sticker,
        document=document,
        views=message.views,
        via_bot=parse_user(users.get(message.via_bot_id, None))
    )

    if message.reply_to_msg_id and replies:
        m.reply_to_message = client.get_messages(m.chat.id, message.reply_to_msg_id)
        m.reply_to_message = m.reply_to_message

    return m


def parse_message_service(
        client,
        message: types.MessageService,
        users: dict,
        chats: dict
) -> pyrogram.Message:
    action = message.action

    new_chat_members = None
    left_chat_member = None
    new_chat_title = None
    delete_chat_photo = None
    migrate_to_chat_id = None
    migrate_from_chat_id = None
    group_chat_created = None
    channel_chat_created = None
    new_chat_photo = None

    if isinstance(action, types.MessageActionChatAddUser):
        new_chat_members = [parse_user(users[i]) for i in action.users]
    elif isinstance(action, types.MessageActionChatJoinedByLink):
        new_chat_members = [parse_user(users[message.from_id])]
    elif isinstance(action, types.MessageActionChatDeleteUser):
        left_chat_member = parse_user(users[action.user_id])
    elif isinstance(action, types.MessageActionChatEditTitle):
        new_chat_title = action.title
    elif isinstance(action, types.MessageActionChatDeletePhoto):
        delete_chat_photo = True
    elif isinstance(action, types.MessageActionChatMigrateTo):
        migrate_to_chat_id = action.channel_id
    elif isinstance(action, types.MessageActionChannelMigrateFrom):
        migrate_from_chat_id = action.chat_id
    elif isinstance(action, types.MessageActionChatCreate):
        group_chat_created = True
    elif isinstance(action, types.MessageActionChannelCreate):
        channel_chat_created = True
    elif isinstance(action, types.MessageActionChatEditPhoto):
        photo = action.photo

        if isinstance(photo, types.Photo):
            sizes = photo.sizes
            photo_sizes = []

            for size in sizes:
                if isinstance(size, (types.PhotoSize, types.PhotoCachedSize)):
                    loc = size.location

                    if isinstance(size, types.PhotoSize):
                        file_size = size.size
                    else:
                        file_size = len(size.bytes)

                    if isinstance(loc, types.FileLocation):
                        photo_size = pyrogram.PhotoSize(
                            file_id=encode(
                                pack(
                                    "<iiqqqqi",
                                    2,
                                    loc.dc_id,
                                    photo.id,
                                    photo.access_hash,
                                    loc.volume_id,
                                    loc.secret,
                                    loc.local_id
                                )
                            ),
                            width=size.w,
                            height=size.h,
                            file_size=file_size,
                            date=photo.date
                        )

                        photo_sizes.append(photo_size)

            new_chat_photo = photo_sizes

    m = pyrogram.Message(
        message_id=message.id,
        date=message.date,
        chat=parse_chat(message, users, chats),
        from_user=parse_user(users.get(message.from_id, None)),
        new_chat_members=new_chat_members,
        left_chat_member=left_chat_member,
        new_chat_title=new_chat_title,
        new_chat_photo=new_chat_photo,
        delete_chat_photo=delete_chat_photo,
        migrate_to_chat_id=int("-100" + str(migrate_to_chat_id)) if migrate_to_chat_id else None,
        migrate_from_chat_id=-migrate_from_chat_id if migrate_from_chat_id else None,
        group_chat_created=group_chat_created,
        channel_chat_created=channel_chat_created
        # TODO: supergroup_chat_created
    )

    if isinstance(action, types.MessageActionPinMessage):
        m.pinned_message = client.get_messages(m.chat.id, message.reply_to_msg_id)
        m.pinned_message = m.pinned_message

    return m


def parse_message_empty(
        client,
        message: types.MessageEmpty,
        users: dict,
        chats: dict
) -> pyrogram.Message:
    return pyrogram.Message(
        message_id=message.id,
        date=None,
        chat=None
    )
