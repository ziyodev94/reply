import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
# XATO TUZATILDI: To'g'ri nom 'DefaultBotProperties'
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = "jbzfa0ygftAGj685Y"

# =================================================================
ADMIN_IDS = [41827] # Bu yerga o'zingizning ID raqamingizni yozing
# =================================================================

# XATO TUZATILDI: Bot obyekti to'g'ri nom bilan yaratildi
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

pending_replies = {}
processed_posts_in_session = {}

class CreateReply(StatesGroup):
    waiting_for_post = State()
    waiting_for_reply = State()
    waiting_for_caption = State()

class EditReply(StatesGroup):
    waiting_for_choice = State()
    waiting_for_new_text = State()
    waiting_for_new_caption = State()
    waiting_for_new_audio = State()

class ReplyCallback(CallbackData, prefix="reply"):
    action: str
    index: int

class EditChoiceCallback(CallbackData, prefix="edit_choice"):
    action: str
    index: int

async def generate_list_message(user_id: int):
    user_replies = pending_replies.get(user_id, [])
    if not user_replies:
        return {"text": "✍️ Saqlangan javoblar hozircha yo'q.", "keyboard": None}

    text = f"<b>Saqlangan javoblar ro'yxati (Jami: {len(user_replies)} ta):</b>\n\n"
    buttons = []
    for i, reply in enumerate(user_replies):
        post_id = reply["original_post"]["message_id"]
        
        edited_marker = " <i>(tahrirlangan)</i>" if reply.get("edited", False) else ""
        
        text += f"<b>{i+1}.</b> <u>Post ID: {post_id}</u> ga javob{edited_marker}\n"
        
        button_row = []
        if reply['type'] == 'text':
            text += f"   <b>Matn:</b> <i>«{reply['content']}»</i>\n\n"
            button_row = [
                InlineKeyboardButton(text=f"Tahrirlash ✏️", callback_data=ReplyCallback(action="edit", index=i).pack()),
                InlineKeyboardButton(text=f"O'chirish 🗑️", callback_data=ReplyCallback(action="delete", index=i).pack())
            ]
        elif reply['type'] == 'audio':
            caption = reply.get('caption') or "Izoh yo'q"
            text += f"   <b>Turi:</b> Ovozli xabar 🎙️\n"
            text += f"   <b>Izoh:</b> <i>«{caption}»</i>\n\n"
            button_row = [
                InlineKeyboardButton(text=f"Tinglash 🎧", callback_data=ReplyCallback(action="listen", index=i).pack()),
                InlineKeyboardButton(text=f"Tahrirlash ✏️", callback_data=ReplyCallback(action="edit", index=i).pack()),
                InlineKeyboardButton(text=f"O'chirish 🗑️", callback_data=ReplyCallback(action="delete", index=i).pack())
            ]
        
        buttons.append(button_row)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return {"text": text, "keyboard": keyboard}

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    await message.answer(f"Salom, {message.from_user.full_name}!")

@dp.message(Command("sotildi_boshla"), F.from_user.id.in_(ADMIN_IDS))
async def start_process(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    pending_replies[user_id] = []
    processed_posts_in_session[user_id] = set()
    await state.set_state(CreateReply.waiting_for_post)
    await message.answer(
        "✅ Yangi jarayon boshlandi. Eski ro'yxatlar tozalandi.\n\n"
        "Sotilgan e'longa javob tayyorlash uchun uni menga **forward** qiling."
    )

@dp.message(CreateReply.waiting_for_post, F.forward_date, F.from_user.id.in_(ADMIN_IDS))
async def post_received(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    forward_info = message.forward_origin
    if not forward_info:
        await message.answer("Xatolik. Iltimos, faqat kanaldan post forward qiling.")
        return
    post_id_tuple = (forward_info.chat.id, forward_info.message_id)
    if post_id_tuple in processed_posts_in_session.get(user_id, set()):
        await message.answer("❗️ Bu e'lon allaqachon joriy ro'yxatga qo'shilgan.")
        return
    processed_posts_in_session.setdefault(user_id, set()).add(post_id_tuple)
    await state.update_data(original_post={"chat_id": post_id_tuple[0], "message_id": post_id_tuple[1]})
    await state.set_state(CreateReply.waiting_for_reply)
    await message.answer("E'lon qabul qilindi.\n\n👉 Endi javoban **ovozli xabar** yoki **matnli xabar** yuboring.")

@dp.message(CreateReply.waiting_for_reply, F.text, F.from_user.id.in_(ADMIN_IDS))
async def reply_is_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    fsm_data = await state.get_data()
    reply_package = {
        "type": "text", 
        "original_post": fsm_data.get("original_post"), 
        "content": message.text,
        "edited": False
    }
    pending_replies.setdefault(user_id, []).append(reply_package)
    count = len(pending_replies.get(user_id, []))
    await state.clear()
    await state.set_state(CreateReply.waiting_for_post)
    await message.answer(
        f"✅ Matnli javob saqlandi. (Jami: {count} ta)\n\n"
        "/list orqali ko'ring, yana e'lon **forward** qiling yoki /yuborish buyrug'ini bering."
    )

@dp.message(CreateReply.waiting_for_reply, F.voice | F.audio, F.from_user.id.in_(ADMIN_IDS))
async def reply_is_audio(message: types.Message, state: FSMContext):
    file_id = message.voice.file_id if message.voice else message.audio.file_id
    await state.update_data(audio_file_id=file_id)
    await state.set_state(CreateReply.waiting_for_caption)
    await message.answer("Ovozli xabar qabul qilindi.\n\n✍️ Endi uning **izohini yuboring**.\n\nIzoh kerak bo'lmasa, /kerakmas buyrug'ini bering.")

@dp.message(CreateReply.waiting_for_caption, F.text, F.from_user.id.in_(ADMIN_IDS))
@dp.message(CreateReply.waiting_for_caption, Command("kerakmas"), F.from_user.id.in_(ADMIN_IDS))
async def caption_received_or_skipped(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    fsm_data = await state.get_data()
    caption_text = message.text if F.text and not message.text.startswith('/kerakmas') else None
    reply_package = {
        "type": "audio", 
        "original_post": fsm_data.get("original_post"), 
        "audio_file_id": fsm_data.get("audio_file_id"), 
        "caption": caption_text,
        "edited": False
    }
    pending_replies.setdefault(user_id, []).append(reply_package)
    count = len(pending_replies.get(user_id, []))
    await state.clear()
    await state.set_state(CreateReply.waiting_for_post)
    await message.answer(
        f"✅ Javob saqlandi. (Jami: {count} ta)\n\n"
        "/list orqali ko'ring, yana e'lon **forward** qiling yoki /yuborish buyrug'ini bering."
    )

@dp.message(Command("list"), F.from_user.id.in_(ADMIN_IDS))
async def show_list(message: types.Message):
    user_id = message.from_user.id
    list_data = await generate_list_message(user_id)
    await message.answer(list_data["text"], reply_markup=list_data["keyboard"])

@dp.callback_query(ReplyCallback.filter(F.action == "edit"), F.from_user.id.in_(ADMIN_IDS))
async def edit_reply_start(callback: types.CallbackQuery, callback_data: ReplyCallback, state: FSMContext):
    user_id = callback.from_user.id
    item_index = callback_data.index
    try:
        reply_to_edit = pending_replies[user_id][item_index]
        await state.update_data(editing_index=item_index)
        if reply_to_edit['type'] == 'text':
            await state.set_state(EditReply.waiting_for_new_text)
            await callback.message.answer("✍️ Javob uchun yangi matnni yuboring:")
        elif reply_to_edit['type'] == 'audio':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ovozni o'zgartirish 🎤", callback_data=EditChoiceCallback(action='audio', index=item_index).pack())],
                [InlineKeyboardButton(text="Matnni o'zgartirish ✍️", callback_data=EditChoiceCallback(action='caption', index=item_index).pack())],
                [InlineKeyboardButton(text="Bekor qilish ❌", callback_data=EditChoiceCallback(action='cancel', index=item_index).pack())]
            ])
            await callback.message.edit_text("Nimani tahrirlamoqchisiz?", reply_markup=keyboard)
        await callback.answer()
    except (IndexError, KeyError):
        await callback.answer("Xatolik: Element topilmadi.", show_alert=True)

@dp.callback_query(EditChoiceCallback.filter(), F.from_user.id.in_(ADMIN_IDS))
async def process_edit_choice(callback: types.CallbackQuery, callback_data: EditChoiceCallback, state: FSMContext):
    action = callback_data.action
    item_index = callback_data.index
    await state.update_data(editing_index=item_index)
    if action == "audio":
        await state.set_state(EditReply.waiting_for_new_audio)
        await callback.message.edit_text("Yangi ovozli xabarni yozib yuboring 🎤")
    elif action == "caption":
        await state.set_state(EditReply.waiting_for_new_caption)
        await callback.message.edit_text("Yangi izohni (caption) yuboring ✍️")
    elif action == "cancel":
        await state.clear()
        # Bekor qilinganda ro'yxatni qayta ko'rsatish yaxshiroq
        list_data = await generate_list_message(callback.from_user.id)
        await callback.message.edit_text(list_data["text"], reply_markup=list_data["keyboard"])
        await callback.answer("Bekor qilindi")


@dp.message(EditReply.waiting_for_new_text, F.text, F.from_user.id.in_(ADMIN_IDS))
async def process_new_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    fsm_data = await state.get_data()
    item_index = fsm_data.get("editing_index")
    pending_replies[user_id][item_index]['content'] = message.text
    pending_replies[user_id][item_index]['edited'] = True
    await state.clear()
    await message.answer("✅ Matn muvaffaqiyatli o'zgartirildi!")
    list_data = await generate_list_message(user_id)
    await message.answer(list_data["text"], reply_markup=list_data["keyboard"])

@dp.message(EditReply.waiting_for_new_caption, F.text, F.from_user.id.in_(ADMIN_IDS))
async def process_new_caption(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    fsm_data = await state.get_data()
    item_index = fsm_data.get("editing_index")
    pending_replies[user_id][item_index]['caption'] = message.text
    pending_replies[user_id][item_index]['edited'] = True
    await state.clear()
    await message.answer("✅ Izoh muvaffaqiyatli o'zgartirildi!")
    list_data = await generate_list_message(user_id)
    await message.answer(list_data["text"], reply_markup=list_data["keyboard"])

@dp.message(EditReply.waiting_for_new_audio, F.voice | F.audio, F.from_user.id.in_(ADMIN_IDS))
async def process_new_audio(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    fsm_data = await state.get_data()
    item_index = fsm_data.get("editing_index")
    new_file_id = message.voice.file_id if message.voice else message.audio.file_id
    pending_replies[user_id][item_index]['audio_file_id'] = new_file_id
    pending_replies[user_id][item_index]['edited'] = True
    await state.clear()
    await message.answer("✅ Ovozli xabar muvaffaqiyatli o'zgartirildi!")
    list_data = await generate_list_message(user_id)
    await message.answer(list_data["text"], reply_markup=list_data["keyboard"])

@dp.callback_query(ReplyCallback.filter(F.action == "listen"), F.from_user.id.in_(ADMIN_IDS))
async def listen_to_reply(callback: types.CallbackQuery, callback_data: ReplyCallback):
    user_id = callback.from_user.id
    item_index = callback_data.index
    try:
        reply = pending_replies[user_id][item_index]
        if reply['type'] == 'audio':
            await bot.send_voice(chat_id=user_id, voice=reply['audio_file_id'], caption=f"<i>{item_index+1}-raqamli javobning ovozli xabari.</i>")
            await callback.answer()
        else:
            await callback.answer("Bu matnli javob.", show_alert=True)
    except (IndexError, KeyError):
        await callback.answer("Xatolik: Element topilmadi.", show_alert=True)

@dp.callback_query(ReplyCallback.filter(F.action == "delete"), F.from_user.id.in_(ADMIN_IDS))
async def delete_reply(callback: types.CallbackQuery, callback_data: ReplyCallback):
    user_id = callback.from_user.id
    item_index = callback_data.index
    try:
        del pending_replies[user_id][item_index]
        await callback.answer("O'chirildi!", show_alert=False)
        list_data = await generate_list_message(user_id)
        await callback.message.edit_text(list_data["text"], reply_markup=list_data["keyboard"])
    except (IndexError, KeyError):
        await callback.answer("Xatolik: Element topilmadi.", show_alert=True)

@dp.message(Command("yuborish"), F.from_user.id.in_(ADMIN_IDS))
async def send_all_replies(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if not pending_replies.get(user_id):
        await message.answer("Yuborish uchun saqlangan javob topilmadi.")
        return
    all_replies = pending_replies[user_id]
    sent_count = 0
    status_msg = await message.answer(f"Jami {len(all_replies)} ta javob yuborilmoqda...")
    for reply in all_replies:
        original_post = reply["original_post"]
        chat_id = original_post["chat_id"]
        message_id = original_post["message_id"]
        try:
            if reply["type"] == "audio":
                await bot.send_audio(chat_id=chat_id, audio=reply["audio_file_id"], caption=reply["caption"], reply_to_message_id=message_id)
            elif reply["type"] == "text":
                await bot.send_message(chat_id=chat_id, text=reply["content"], reply_to_message_id=message_id)
            sent_count += 1
            await asyncio.sleep(0.7)
        except Exception as e:
            logging.error(f"Xabar yuborishda xato: {e}")
            await message.answer(f"⚠️ ID:{message_id} postga javob yuborishda xatolik.")
    await status_msg.edit_text(f"✅ Jarayon yakunlandi. {sent_count} ta javob yuborildi.")
    pending_replies[user_id] = []
    processed_posts_in_session[user_id] = set()

@dp.message(Command("bekor_qilish"), F.from_user.id.in_(ADMIN_IDS))
async def cancel_process(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in pending_replies: pending_replies[user_id] = []
    if user_id in processed_posts_in_session: processed_posts_in_session[user_id] = set()
    await message.answer("Jarayon bekor qilindi. Barcha saqlangan javoblar o'chirildi.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())


