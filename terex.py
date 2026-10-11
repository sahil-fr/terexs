import asyncio
import os
import logging
import json
import sqlite3
import aiohttp
import threading
import uuid

from flask import Flask
from dotenv import load_dotenv

from datetime import datetime, timedelta
from typing import Optional, Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
    LinkPreviewOptions,
    InputRichMessage,
    # ✅ FIX: Ye dono classes yahin se import karo, alag module se nahi
    InputRichBlockButtons,
    RichMessageButton,
)

from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
    ReplyKeyboardBuilder,
)

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
)

from aiogram.methods.base import TelegramMethod

app = Flask(__name__)

@app.route('/')
def home():
    return "Escrow Bot is running live!"

@app.route('/health')
def health():
    return {"status": "online"}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing from environment variables!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

MIDDLEMEN_IDS = [
    7913633925,
    8258524753,
    967359142,
    8421166266,
    8358390340
]

SUPPORT_ADMIN_ID = 7977452329

escrow_states = {}
admin_states = {}
deal_claims = {}

NET_DISPLAY = {
    "usdtbep20": "USDT BEP20",
    "usdterc20": "USDT ERC20",
    "usdttrc20": "USDT TRC20",
    "usdtsol": "USDT SOL",
    "usdcsol": "USDC SOL",
    "usdcerc20": "USDC ERC20",
    "solana": "Solana",
    "ethereum": "Ethereum",
    "bnbsmartchain": "BNB Smart Chain",
    "tron": "Tron",
    "litecoin": "Litecoin",
    "bitcoin": "Bitcoin",
    "gram": "Gram",
}

INR_FUND_DISPLAY = {
    "safe": "Safe Funds",
    "rat": "Rat Funds",
    "gaming": "Gaming Funds",
    "mix": "Mix Funds",
}

# ✅ FIX: Helper function jo HTML string ko InputRichMessage mein convert karta hai
# Yeh function <tg-button-row> aur <tg-button> tags ko parse karke proper 
# InputRichBlockButtons object banata hai taaki aiogram error na de.
def make_rich_message(html_text: str) -> InputRichMessage:
    """
    HTML string ko InputRichMessage mein convert karta hai.
    Agar string mein <tg-button-row> ya <tg-button> tags hain, toh unhe
    InputRichBlockButtons mein convert karta hai.
    """
    import re

    # Check karo ki buttons hain ya nahi
    if "<tg-button" not in html_text:
        return InputRichMessage(html=html_text)

    # Buttons ko extract karo
    buttons = []
    # Regex se saare <tg-button> tags dhoondo
    pattern = r'<tg-button[^>]*data="([^"]*)"[^>]*>([^<]*)</tg-button>'
    matches = re.findall(pattern, html_text)

    for data, text in matches:
        # Style extract karo
        style_match = re.search(
            rf'<tg-button[^>]*data="{data}"[^>]*style="([^"]*)"',
            html_text
        )
        style = style_match.group(1) if style_match else "primary"

        # Icon extract karo
        icon_match = re.search(
            rf'<tg-button[^>]*data="{data}"[^>]*icon_custom_emoji_id="([^"]*)"',
            html_text
        )
        icon = icon_match.group(1) if icon_match else None

        buttons.append(
            RichMessageButton(
                text=text.strip(),
                style=style,
                callback_data=data,
                icon_custom_emoji_id=icon
            )
        )

    # HTML se button tags hata do (sirf text bache)
    clean_html = re.sub(r'<tg-button-row>.*?</tg-button-row>', '', html_text, flags=re.DOTALL)
    clean_html = clean_html.strip()

    if not buttons:
        return InputRichMessage(html=clean_html)

    # Button block banao
    button_block = InputRichBlockButtons(buttons=buttons)

    return InputRichMessage(
        html=clean_html,
        blocks=[button_block]
    )


def crypto_buttons_selling(back_data):
    networks = [
        ("USDT BEP20", "usdtbep20", "5771530555048857288"),
        ("USDT ERC20", "usdterc20", "5769374258127965397"),
        ("USDT TRC20", "usdttrc20", "5771583477635877860"),
        ("USDT SOL", "usdtsol", "5771480514384891109"),
        ("USDC SOL", "usdcsol", "5771480514384891109"),
        ("USDC ERC20", "usdcerc20", "5769374258127965397"),
        ("Solana", "solana", "5771480514384891109"),
        ("Ethereum", "ethereum", "5769374258127965397"),
        ("BNB Smart Chain", "bnbsmartchain", "5771530555048857288"),
        ("Tron", "tron", "5771583477635877860"),
        ("Litecoin", "litecoin", "5771379449509448765"),
        ("Bitcoin", "bitcoin", "5771849507910192329"),
        ("Gram", "gram", "5886352111955878352"),
    ]

    rows = []
    for i in range(0, len(networks), 2):
        row = [
            InlineKeyboardButton(
                text=name,
                icon_custom_emoji_id=emoji_id,
                callback_data=f"sellnet_{key}"
            )
            for name, key, emoji_id in networks[i:i + 2]
        ]
        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            text="Back",
            icon_custom_emoji_id="5210952531676504517",
            callback_data=(
                back_data.decode()
                if isinstance(back_data, bytes)
                else back_data
            )
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

class EditRichMessageText(TelegramMethod[Message]):
    __api_method__ = "editMessageText"
    __returning__ = Message

    chat_id: int
    message_id: int
    rich_message: dict


def crypto_buttons_paying(back_data):
    networks = [
        ("USDT BEP20", "usdtbep20", "5771530555048857288"),
        ("USDT ERC20", "usdterc20", "5769374258127965397"),
        ("USDT TRC20", "usdttrc20", "5771583477635877860"),
        ("USDT SOL", "usdtsol", "5771480514384891109"),
        ("USDC SOL", "usdcsol", "5771480514384891109"),
        ("USDC ERC20", "usdcerc20", "5769374258127965397"),
        ("Solana", "solana", "5771480514384891109"),
        ("Ethereum", "ethereum", "5769374258127965397"),
        ("BNB Smart Chain", "bnbsmartchain", "5771530555048857288"),
        ("Tron", "tron", "5771583477635877860"),
        ("Litecoin", "litecoin", "5771379449509448765"),
        ("Bitcoin", "bitcoin", "5771849507910192329"),
        ("Gram", "gram", "5886352111955878352"),
    ]

    rows = []
    for i in range(0, len(networks), 2):
        row = [
            InlineKeyboardButton(
                text=name,
                icon_custom_emoji_id=emoji_id,
                callback_data=f"paynet_{key}"
            )
            for name, key, emoji_id in networks[i:i + 2]
        ]
        rows.append(row)

    rows.append([
        InlineKeyboardButton(
            text="Back",
            icon_custom_emoji_id="5210952531676504517",
            callback_data=(
                back_data.decode()
                if isinstance(back_data, bytes)
                else back_data
            )
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)

async def get_usdt_inr_price():
    try:
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=USDTINR"

            async with session.get(url) as resp:
                if resp.status == 200:
                    ticker = await resp.json()
                    rate = float(ticker["price"])

                    if rate > 0:
                        return rate

                print(f"Binance API returned status: {resp.status}")

    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
        print(f"Binance price fetch error: {e}")

    return 83.0

@router.message(CommandStart())
async def escrow_start(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return

    welcome_text = (
        '<b>Welcome to @middlescrowbot</b>\n\n'
        "Your trusted platform for secure P2P and OTC transactions on Telegram.\n\n"
        '<b><tg-emoji emoji-id="5904238507555033712">⛔️</tg-emoji> Trade safely. Avoid scams.</b>\n'
        "The bot connects you with the best available middleman for your transaction, "
        "helping ensure a safe and smooth deal.\n\n"
        '<tg-emoji emoji-id="5893473283696759404">💰</tg-emoji> <b>ESCROW FEE</b>\n'
        "• P2P: 1.0%\n"
        "• OTC: 2.0% flat\n\n"
        '<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> <b>Ready to trade?</b> Use /escrow to start a new escrow.\n\n'
        '<tg-emoji emoji-id="5902449142575141204">🔗</tg-emoji> Powered by @AFFUX.'
    )

    welcome_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Support",
                    icon_custom_emoji_id="5884510167986343350",
                    callback_data="menu_support",
                    style="danger"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Updates",
                    icon_custom_emoji_id="5771695636411847302",
                    url="https://t.me/AFFUX",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text="Vouches",
                    icon_custom_emoji_id="5951665890079544884",
                    url="https://t.me/middlemaven",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Terms of Service",
                    icon_custom_emoji_id="5877597667231534929",
                    callback_data="menu_tos",
                    style="success"
                )
            ]
        ]
    )

    # Reset user's escrow state
    await state.clear()
    await state.update_data(step="main")

    await message.answer(
        welcome_text,
        reply_markup=welcome_buttons,
        parse_mode=ParseMode.HTML,
        link_preview_options={"is_disabled": True}
    )

    # Second message: Escrow type selection
    type_text = (
        "🤝 <b>Please select your escrow type below:</b>\n\n"
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Cryptocurrency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs'
        "\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" data="cat_p2p">P2P</tg-button>'
        '<tg-button type="callback_data" style="primary" data="cat_pos">POS</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=make_rich_message(type_text)
    )

@router.callback_query(F.data == "cat_p2p")
async def p2p_category(callback: CallbackQuery, state: FSMContext):
    await state.update_data(
        category="P2P",
        step="buyer_seller"
    )

    text = (
        "Are you the buyer or the seller?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" '
        'data="role_buyer">Buyer</tg-button>'
        '<tg-button type="callback_data" style="primary" '
        'data="role_seller">Seller</tg-button>'
        '</tg-button-row>\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_escrow_type">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.callback_query(F.data == "cat_pos")
async def pos_category_handler(callback: CallbackQuery, state: FSMContext):
    await state.update_data(
        category="POS",
        step="select_currency_type"
    )

    text = (
        "Do you want to deal in <b>USD</b> or <b>INR</b>?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" '
        'data="pos_curr_usd">USD</tg-button>'
        '<tg-button type="callback_data" style="primary" '
        'data="pos_curr_inr">INR</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_escrow_type">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.callback_query(F.data.in_({"pos_curr_usd", "pos_curr_inr"}))
async def pos_currency_selection(callback: CallbackQuery, state: FSMContext):
    curr = callback.data.split("_")[2].upper()

    await state.update_data(currency_type=curr)

    if curr == "INR":
        await state.update_data(step="pos_inr_q1")

        text = (
            "<b>Question 1/3</b>\n\n"
            "What is the deal about? Describe the product or service.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="cat_pos">Back</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await callback.bot(
            EditRichMessageText(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                rich_message=make_rich_message(text).model_dump(exclude_none=True)
            )
        )

    else:
        await state.update_data(step="select_usd_network")

        text = "Select USD / Crypto network for POS deal:"

        buttons = crypto_buttons_selling("cat_pos")

        await callback.message.edit_text(
            text,
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )

    await callback.answer()

@router.callback_query(F.data.in_({"role_buyer", "role_seller"}))
async def role_selection(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1].capitalize()

    await state.update_data(
        category="P2P",
        role=role,
        step="select_selling_network"
    )

    text = "What are you selling? Select network:"

    buttons = crypto_buttons_selling("back_to_role")

    await callback.message.edit_text(
        text,
        reply_markup=buttons,
        parse_mode=ParseMode.HTML
    )

    await callback.answer()

@router.message(F.text.regexp(r"^/escrow(?:@\w+)?$"))
async def escrow_command(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return

    type_text = (
        '🤝 <b>Please select your escrow type below:</b>\n\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Crypto currency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" data="cat_p2p">P2P</tg-button>'
        '<tg-button type="callback_data" style="primary" data="cat_pos">POS</tg-button>'
        '</tg-button-row>'
    )

    await state.clear()
    await state.update_data(step="main")

    # ✅ FIX: make_rich_message use karo
    await bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=make_rich_message(type_text)
    )

@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):

    welcome_text = (
        '<b>Welcome to @middlescrowbot</b>\n\n'
        "Your trusted platform for secure P2P and OTC transactions on Telegram.\n\n"
        '<tg-emoji emoji-id="5904238507555033712">⛔</tg-emoji> <b>Trade safely. Avoid scams.</b>\n'
        "The bot connects you with the best available middleman for your transaction, "
        "helping ensure a safe and smooth deal.\n\n"
        '<tg-emoji emoji-id="5893473283696759404">💰</tg-emoji> <b>ESCROW FEE</b>\n'
        "• P2P: 1.0%\n"
        "• OTC: 2.0% flat\n\n"
        '<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> <b>Ready to trade?</b> Use /escrow to start a new escrow.\n\n'
        '<tg-emoji emoji-id="5902449142575141204">🔗</tg-emoji> Powered by @AFFUX.'
    )

    welcome_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Support",
                    icon_custom_emoji_id="5884510167986343350",
                    callback_data="menu_support",
                    style="danger"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Updates",
                    icon_custom_emoji_id="5771695636411847302",
                    url="https://t.me/AFFUX",
                    style="primary"
                ),
                InlineKeyboardButton(
                    text="Vouches",
                    icon_custom_emoji_id="5951665890079544884",
                    url="https://t.me/middlemaven",
                    style="primary"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Terms of Service",
                    icon_custom_emoji_id="5877597667231534929",
                    callback_data="menu_tos",
                    style="success"
                )
            ]
        ]
    )

    await state.clear()
    await state.update_data(step="main")

    await callback.message.edit_text(
        welcome_text,
        reply_markup=welcome_buttons,
        parse_mode=ParseMode.HTML,
        link_preview_options={"is_disabled": True}
    )

    await callback.answer()

@router.callback_query(F.data == "back_to_escrow_type")
async def back_to_escrow_type(callback: CallbackQuery, state: FSMContext):
    type_text = (
        '🤝 <b>Please select your escrow type below:</b>\n\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Crypto currency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" data="cat_p2p">P2P</tg-button>'
        '<tg-button type="callback_data" style="primary" data="cat_pos">POS</tg-button>'
        '</tg-button-row>'
    )

    await state.clear()
    await state.update_data(step="main")

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(type_text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.callback_query(F.data == "back_to_role")
async def back_to_role(callback: CallbackQuery, state: FSMContext):
    text = (
        "Are you the buyer or the seller?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" '
        'data="role_buyer">Buyer</tg-button>'
        '<tg-button type="callback_data" style="primary" '
        'data="role_seller">Seller</tg-button>'
        '</tg-button-row>\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_escrow_type">Back</tg-button>'
        '</tg-button-row>'
    )

    await state.update_data(
        category="P2P",
        step="buyer_seller"
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.callback_query(F.data.startswith("sellnet_"))
async def sellnet_selection(
    callback: CallbackQuery,
    state: FSMContext
):
    net_key = callback.data.replace("sellnet_", "")

    data = await state.get_data()
    category = data.get("category")
    sender_id = callback.from_user.id

    if net_key == "back":
        if category == "P2P":
            await back_to_role(callback, state)
        elif category == "POS":
            await pos_category_handler(callback, state)
        else:
            await back_to_start(callback, state)
        return

    net_name = NET_DISPLAY.get(net_key, net_key.upper())

    # ----- POS -----
    if category == "POS":
        await state.update_data(
            paying_currency=net_name,
            step="pos_crypto_q1"
        )

        # Sync with the existing text handler
        escrow_states.setdefault(sender_id, {}).update({
            "paying_currency": net_name,
            "step": "pos_crypto_q1"
        })

        text = (
            "<b>Question 1/3</b>\n\n"
            "What is the deal about? Describe the product or service.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="cat_pos">'
            'Back'
            '</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await callback.bot(
            EditRichMessageText(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                rich_message=make_rich_message(text).model_dump(exclude_none=True)
            )
        )

        await callback.answer()
        return

    # ----- P2P -----
    await state.update_data(
        selling_currency=net_name,
        step="p2p_amount"
    )

    # Sync with the existing text handler
    escrow_states.setdefault(sender_id, {}).update({
        "selling_currency": net_name,
        "step": "p2p_amount"
    })

    text = (
        f"Amount in <b>{net_name}</b>?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_role">'
        'Back'
        '</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.callback_query(F.data.startswith("paynet_"))
async def paynet_selection(callback: CallbackQuery, state: FSMContext):
    net_key = callback.data.replace("paynet_", "")

    if net_key == "back":
        await state.update_data(step="p2p_payment_method")

        text = (
            "How are you paying?\n\n"
            '<tg-button-row align="center">'
            '<tg-button type="callback_data" style="primary" '
            'data="pay_inr">INR</tg-button>'
            '<tg-button type="callback_data" style="primary" '
            'data="pay_crypto">Crypto</tg-button>'
            '</tg-button-row>'
            '<tg-button-row align="center">'
            '<tg-button type="callback_data" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="back_to_role">Back</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await callback.bot(
            EditRichMessageText(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
                rich_message=make_rich_message(text).model_dump(exclude_none=True)
            )
        )

        await callback.answer()
        return

    net_name = NET_DISPLAY.get(net_key, net_key.upper())

    await state.update_data(
        paying_currency=net_name,
        step="p2p_crypto_amount"
    )

    text = (
        f"Amount of {net_name} are you paying?\n\n"
        '<tg-button-row align="center">'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_payment">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()

@router.message(
    F.chat.type == "private",
    F.text,
    ~F.text.startswith("/")
)
async def handle_all_text_inputs(message: Message, state: FSMContext):
    sender_id = message.from_user.id
    text_input = message.text.strip()

    # ===== 1. Admin support reply =====
    if admin_states.get(sender_id, {}).get("step") == "waiting_support_reply":
        target_user = admin_states[sender_id]["target_user"]

        try:
            await bot.send_message(
                target_user,
                f'<tg-emoji emoji-id="5253742260054409879">✉️</tg-emoji> <b>Support Reply:</b>\n\n{text_input}',
                parse_mode=ParseMode.HTML
            )
            await message.answer(
                '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> Reply sent to user!',
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            print(f"Error sending reply: {e}")
            await message.answer(
                f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Failed: {e}',
                parse_mode=ParseMode.HTML
            )

        admin_states.pop(sender_id, None)
        return

    # ===== 2. Middleman group link =====
    if admin_states.get(sender_id, {}).get("step") == "waiting_group_link":
        group_link = text_input
        target_user = admin_states[sender_id]["target_user"]

        user_msg = (
            '<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> @affux escrow group for your deal is ready.\n\n'
            f"{group_link}\n\n"
            "Please share this with the other party."
        )

        try:
            await bot.send_message(
                target_user,
                user_msg,
                parse_mode=ParseMode.HTML
            )
            await message.answer(
                '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> Group link successfully sent to the user!',
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            print(f"Error sending group link: {e}")
            await message.answer(
                f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Failed: {e}',
                parse_mode=ParseMode.HTML
            )

        admin_states.pop(sender_id, None)
        return

    # ===== 3. Escrow flow =====
    if sender_id not in escrow_states:
        return

    current_step = escrow_states[sender_id].get("step")

    print(
        f"[DEBUG] user={sender_id} "
        f"state={current_step} text={text_input!r}"
    )

    # ----- P2P CONDITION -----
    if current_step == "p2p_condition":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await p2p_summary_send(message, sender_id)
        return

    # ----- POS INR Q3 -----
    if current_step == "pos_inr_q3":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await pos_inr_summary_send(message, sender_id)
        return

    # ----- POS CRYPTO Q3 -----
    if current_step == "pos_crypto_q3":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await pos_crypto_summary_send(message, sender_id)
        return

    # ----- P2P AMOUNT -----
    if current_step == "p2p_amount":
        raw = (
            text_input.replace("$", "")
            .replace("₹", "")
            .replace(",", "")
            .strip()
        )

        try:
            amount = float(raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!',
                parse_mode=ParseMode.HTML
            )
            return

        escrow_states[sender_id]["amount"] = amount
        escrow_states[sender_id]["step"] = "p2p_payment_method"

        text = (
            "How are you paying?\n\n"
            '<tg-button-row align="center">'
            '<tg-button type="callback_data" style="primary" data="pay_inr">INR</tg-button>'
            '<tg-button type="callback_data" style="primary" data="pay_crypto">Crypto</tg-button>'
            '</tg-button-row>'
            '<tg-button-row align="center">'
            '<tg-button type="callback_data" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="back_to_role">Back</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- P2P INR AMOUNT -----
    if current_step == "p2p_inr_amount":
        raw = text_input.replace("₹", "").replace(",", "").strip()

        try:
            amount = float(raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!',
                parse_mode=ParseMode.HTML
            )
            return

        escrow_states[sender_id]["paying_amount"] = amount
        escrow_states[sender_id]["step"] = "p2p_condition"

        text = (
            "Any conditions?\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="p2p_cancel">Cancel</tg-button>'
            '<tg-button type="callback_data" style="primary" '
            'data="p2p_no_condition">No Condition</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- P2P CRYPTO AMOUNT -----
    if current_step == "p2p_crypto_amount":
        raw = text_input.replace("$", "").replace(",", "").strip()

        try:
            amount = float(raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!',
                parse_mode=ParseMode.HTML
            )
            return

        escrow_states[sender_id]["paying_amount"] = amount
        escrow_states[sender_id]["step"] = "p2p_condition"

        text = (
            "Any conditions?\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="p2p_cancel">Cancel</tg-button>'
            '<tg-button type="callback_data" style="primary" '
            'data="p2p_no_condition">No Condition</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- POS INR Q1 -----
    if current_step == "pos_inr_q1":
        escrow_states[sender_id]["deal_info"] = text_input
        escrow_states[sender_id]["step"] = "pos_inr_q2"

        text = (
            "<b>Question 2/3</b>\n\n"
            "How much, in <b>INR</b>? Just the number, "
            "e.g. <code>₹50</code>.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="pos_cancel">Cancel</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- POS INR Q2 -----
    if current_step == "pos_inr_q2":
        raw = text_input.replace("₹", "").replace(",", "").strip()

        try:
            amount = float(raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!',
                parse_mode=ParseMode.HTML
            )
            return

        escrow_states[sender_id]["pos_amount"] = amount
        escrow_states[sender_id]["step"] = "pos_inr_q3"

        text = (
            "<b>Question 3/3</b>\n\n"
            "Any conditions? Send them, or <code>skip</code>.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="pos_cancel">Cancel</tg-button>'
            '<tg-button type="callback_data" style="primary" '
            'data="pos_no_condition">No Condition</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- POS CRYPTO Q1 -----
    if current_step == "pos_crypto_q1":
        escrow_states[sender_id]["deal_info"] = text_input
        escrow_states[sender_id]["step"] = "pos_crypto_q2"

        text = (
            "<b>Question 2/3</b>\n\n"
            "How much, in <b>Crypto</b>? Just the number, "
            "e.g. <code>$50</code>.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="pos_cancel">Cancel</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- POS CRYPTO Q2 -----
    if current_step == "pos_crypto_q2":
        raw = text_input.replace("$", "").replace(",", "").strip()

        try:
            amount = float(raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.answer(
                '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!',
                parse_mode=ParseMode.HTML
            )
            return

        escrow_states[sender_id]["pos_amount"] = amount
        escrow_states[sender_id]["step"] = "pos_crypto_q3"

        text = (
            "<b>Question 3/3</b>\n\n"
            "Any conditions? Send them, or <code>skip</code>.\n\n"
            '<tg-button-row>'
            '<tg-button type="callback_data" style="danger" '
            'icon_custom_emoji_id="5210952531676504517" '
            'data="pos_cancel">Cancel</tg-button>'
            '<tg-button type="callback_data" style="primary" '
            'data="pos_no_condition">No Condition</tg-button>'
            '</tg-button-row>'
        )

        # ✅ FIX: make_rich_message use karo
        await bot.send_rich_message(
            chat_id=message.chat.id,
            rich_message=make_rich_message(text)
        )
        return

    # ----- SUPPORT QUERY -----
    if current_step == "waiting_support_query":
        escrow_states[sender_id]["support_query"] = text_input
        escrow_states[sender_id]["step"] = "waiting_support_media"

        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Skip",
                        callback_data="support_skip_media"
                    )
                ]
            ]
        )

        await message.answer(
            "Send a <b>screenshot, image or video</b> for this issue.",
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )
        return


async def p2p_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})

    role = data.get("role")

    try:
        sender = await message.bot.get_chat(sender_id)
    except Exception:
        sender = None

    seller_name = (
        f"@{sender.username}"
        if sender and sender.username
        else f'<code>{sender_id}</code>'
    )

    other_party = "Not set"

    if role == "Seller":
        seller_display = seller_name
        buyer_display = other_party
    else:
        seller_display = other_party
        buyer_display = seller_name

    pay_curr = data.get("paying_currency", "INR")
    pay_amt = data.get("paying_amount", "")
    sell_curr = data.get("selling_currency", "")
    sell_amt = data.get("amount", "")
    condition = data.get("condition", "None")

    summary_text = (
        f'<b>P2P <tg-emoji emoji-id="5357094458984769398">🔵</tg-emoji> '
        f'{sell_curr} '
        f'<tg-emoji emoji-id="5348567359764317130">↔️</tg-emoji> '
        f'{pay_curr}</b>\n\n'
        f'<b>Seller:</b> {seller_display}\n'
        f'<b>Selling:</b> {sell_curr}\n'
        f'<b>Amount:</b> {sell_amt} {sell_curr}\n\n'
        f'<b>Buyer:</b> {buyer_display}\n'
        f'<b>Paying:</b> {pay_curr}\n'
        f'<b>Amount:</b> {pay_amt} {pay_curr}\n\n'
        f'<b>Condition:</b> {condition}\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="deal_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="deal_cancel">Cancel</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=make_rich_message(summary_text)
    )

async def p2p_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    role = data.get("role")

    try:
        sender = await callback.bot.get_chat(sender_id)
    except Exception:
        sender = None

    seller_name = (
        f"@{sender.username}"
        if sender and sender.username
        else f"<code>{sender_id}</code>"
    )

    other_party = "Not set"

    if role == "Seller":
        seller_display = seller_name
        buyer_display = other_party
    else:
        seller_display = other_party
        buyer_display = seller_name

    pay_curr = data.get("paying_currency", "INR")
    pay_amt = data.get("paying_amount", "")
    sell_curr = data.get("selling_currency", "")
    sell_amt = data.get("amount", "")
    condition = data.get("condition", "None")

    summary_text = (
        f'<b>P2P <tg-emoji emoji-id="5357094458984769398">🔵</tg-emoji> '
        f'{sell_curr} '
        f'<tg-emoji emoji-id="5348567359764317130">↔️</tg-emoji> '
        f'{pay_curr}</b>\n\n'
        f'<b>Seller:</b> {seller_display}\n'
        f'<b>Selling:</b> {sell_curr}\n'
        f'<b>Amount:</b> {sell_amt} {sell_curr}\n\n'
        f'<b>Buyer:</b> {buyer_display}\n'
        f'<b>Paying:</b> {pay_curr}\n'
        f'<b>Amount:</b> {pay_amt} {pay_curr}\n\n'
        f'<b>Condition:</b> {condition}\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="deal_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="deal_cancel">Cancel</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot(
        EditRichMessageText(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            rich_message=make_rich_message(summary_text).model_dump(exclude_none=True)
        )
    )

    await callback.answer()


async def pos_inr_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})

    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 20)
    total = amount + fee

    usdt_rate = await get_usdt_inr_price()
    total_usdt = round(total / usdt_rate, 2)

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ₹{amount:g} + ₹{fee:g} fee = "
        f"₹{total:g} (${total_usdt} USDT)\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\n"
        "Submit this?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="pos_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="pos_cancel">Cancel</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="cat_pos">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=make_rich_message(summary_text)
    )


async def pos_inr_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 20)
    total = amount + fee

    usdt_rate = await get_usdt_inr_price()
    total_usdt = round(total / usdt_rate, 2)

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ₹{amount:g} + ₹{fee:g} fee = "
        f"₹{total:g} (${total_usdt} USDT)\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\n"
        "Submit this?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="pos_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="pos_cancel">Cancel</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="cat_pos">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(summary_text).model_dump(exclude_none=True)
    )

    await callback.answer()


async def pos_crypto_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 1)
    total = amount + fee

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ${amount:g} + ${fee:g} fee = ${total:g}\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\n"
        "Submit this?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="pos_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="pos_cancel">Cancel</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await bot.send_rich_message(
        chat_id=message.chat.id,
        rich_message=make_rich_message(summary_text)
    )


async def pos_crypto_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 1)
    total = amount + fee

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ${amount:g} + ${fee:g} fee = ${total:g}\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\n"
        "Submit this?\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        'data="pos_submit">Submit</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="pos_cancel">Cancel</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(summary_text).model_dump(exclude_none=True)
    )

    await callback.answer()


@router.callback_query(F.data == "pay_inr")
async def p2p_pay_inr(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["paying_currency"] = "INR"
    escrow_states[sender_id]["step"] = "p2p_inr_fund"

    text = (
        "<b>Which INR funds are you paying with?</b>\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" data="fund_safe">Safe Funds</tg-button>'
        '<tg-button type="callback_data" data="fund_rat">Rat Funds</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" data="fund_gaming">Gaming Funds</tg-button>'
        '<tg-button type="callback_data" data="fund_mix">Mix Funds</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_payment">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(text).model_dump(exclude_none=True)
    )

    await callback.answer()

@router.callback_query(F.data == "pay_crypto")
async def p2p_pay_crypto(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["step"] = "p2p_crypto_network"

    text = "<b>Select the crypto network you're paying with:</b>"

    buttons = crypto_buttons_paying("back_to_payment")

    await callback.message.edit_text(
        text,
        reply_markup=buttons,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_payment")
async def back_to_payment(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["step"] = "p2p_payment_method"

    text = (
        "<b>How are you paying?</b>\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" data="pay_inr">INR</tg-button>'
        '<tg-button type="callback_data" data="pay_crypto">Crypto</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_role">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(text).model_dump(exclude_none=True)
    )

    await callback.answer()


@router.callback_query(F.data.startswith("fund_"))
async def fund_selection(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    fund_key = callback.data.replace("fund_", "")
    fund_name = INR_FUND_DISPLAY.get(fund_key, "Safe Funds")

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["paying_currency"] = fund_name
    escrow_states[sender_id]["step"] = "p2p_inr_amount"

    text = (
        f"<b>What amount of {fund_name} are you paying?</b>\n\n"
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="pay_inr">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(text).model_dump(exclude_none=True)
    )

    await callback.answer()

@router.callback_query(F.data == "p2p_no_condition")
async def p2p_no_condition(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["condition"] = "None"

    await p2p_summary_edit(callback, sender_id)

@router.callback_query(F.data == "p2p_cancel")
async def p2p_cancel(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.pop(sender_id, None)
    await state.clear()

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Cancelled.</b> /start to open a new one.',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@router.callback_query(F.data == "deal_cancel")
async def deal_cancel(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.pop(sender_id, None)
    await state.clear()

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Cancelled.</b> /start to open a new one.',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data == "deal_submit")
async def deal_submit(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    data = escrow_states.get(sender_id, {})

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5427181942934088912">💬</tg-emoji> '
        '<b>Please wait while we connect you with the best available escrower!</b>\n\n'
        '<b>Expected time: ~10 minutes</b>',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

    user = callback.from_user
    first_name = user.first_name or "User"

    deal_claims[sender_id] = {
        "status": "pending",
        "approved_by": None,
        "approved_username": None
    }

    mm_text = (
        '<tg-emoji emoji-id="5395695537687123235">🚨</tg-emoji> '
        '<b>New Deal Request!</b>\n'
        f'From User: <a href="tg://user?id={sender_id}">{first_name}</a>\n'
        'Category: P2P\n'
        f'Selling: {data.get("amount")} {data.get("selling_currency")}\n'
        f'Paying: {data.get("paying_amount")} {data.get("paying_currency")}\n'
        f'Conditions: {data.get("condition", "None")}\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        f'data="mm_app_{sender_id}">Approve</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        f'data="mm_rej_{sender_id}">Reject</tg-button>'
        '</tg-button-row>'
    )

    for mm_id in MIDDLEMEN_IDS:
        try:
            # ✅ FIX: make_rich_message use karo
            await callback.bot.send_rich_message(
                chat_id=mm_id,
                rich_message=make_rich_message(mm_text)
            )
        except Exception as e:
            print(f"Error notifying middleman {mm_id}: {e}")

@router.callback_query(F.data == "pos_no_condition")
async def pos_no_condition(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["condition"] = "None"

    if escrow_states[sender_id].get("currency_type") == "INR":
        await pos_inr_summary_edit(callback, sender_id)
    else:
        await pos_crypto_summary_edit(callback, sender_id)

@router.callback_query(F.data == "pos_cancel")
async def pos_cancel(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states.pop(sender_id, None)
    await state.clear()

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Cancelled.</b> /start to open a new one.',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data == "pos_submit")
async def pos_submit(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    data = escrow_states.get(sender_id, {})

    deal_id = uuid.uuid4().hex[:10]

    deal_claims[deal_id] = {
        "status": "pending",
        "approved_by": None,
        "approved_username": None
    }

    data["deal_id"] = deal_id
    escrow_states[sender_id] = data

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5427181942934088912">💬</tg-emoji> '
        '<b>Please wait while we connect you with the best available escrower!</b>\n\n'
        '<b>Expected time: ~10 minutes</b>',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

    user = callback.from_user
    first_name = user.first_name or "User"

    mm_text = (
        '<tg-emoji emoji-id="5395695537687123235">🚨</tg-emoji> '
        '<b>New Deal Request!</b>\n'
        f'From User: <a href="tg://user?id={sender_id}">{first_name}</a>\n'
        'Category: POS\n'
        f'Deal Info: {data.get("deal_info", ".")}\n'
        f'Amount: {data.get("pos_amount")} {data.get("currency_type")}\n'
        f'Conditions: {data.get("condition", "None")}\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="success" '
        'icon_custom_emoji_id="5206607081334906820" '
        f'data="mm_app_{sender_id}_{deal_id}">Approve</tg-button>'
        '<tg-button type="callback_data" style="danger" '
        'icon_custom_emoji_id="5210952531676504517" '
        f'data="mm_rej_{sender_id}_{deal_id}">Reject</tg-button>'
        '</tg-button-row>'
    )

    for mm_id in MIDDLEMEN_IDS:
        try:
            # ✅ FIX: make_rich_message use karo
            await callback.bot.send_rich_message(
                chat_id=mm_id,
                rich_message=make_rich_message(mm_text)
            )
        except Exception as e:
            print(f"Error notifying middleman {mm_id}: {e}")


@router.callback_query(F.data == "support_skip_media")
async def support_skip_media(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    query_text = escrow_states.get(sender_id, {}).get(
        "support_query", "No text query"
    )

    admin_msg = (
        '<tg-emoji emoji-id="5253742260054409879">✉️</tg-emoji> '
        '<b>New Support Ticket! (Skipped Media)</b>\n'
        f'From: <code>{sender_id}</code>\n'
        f'Issue: {query_text}\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" style="primary" '
        'icon_custom_emoji_id="5395444784611480792" '
        f'data="sup_reply_{sender_id}">Reply</tg-button>'
        '</tg-button-row>'
    )

    try:
        # ✅ FIX: make_rich_message use karo
        await callback.bot.send_rich_message(
            chat_id=SUPPORT_ADMIN_ID,
            rich_message=make_rich_message(admin_msg)
        )
    except Exception as e:
        print(f"Error sending support admin: {e}")

    final_msg = (
        '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> '
        '<b>Sent to support.</b>\n\n'
        'You will get a reply here.'
    )

    await callback.message.edit_text(
        final_msg,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

    escrow_states.pop(sender_id, None)
    await state.clear()

@router.callback_query(F.data.startswith("sup_reply_"))
async def support_reply_click(callback: CallbackQuery, state: FSMContext):
    target_user = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id

    text = (
        '<tg-emoji emoji-id="5395444784611480792">✏️</tg-emoji> <b>Send your reply for user</b> '
        f'<code>{target_user}</code>.\n\n'
        'It will be delivered directly to them.'
    )

    await callback.message.answer(
        text,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

    admin_states[admin_id] = {
        "step": "waiting_support_reply",
        "target_user": target_user
    }

@router.callback_query(F.data.startswith("mm_app_"))
async def mm_approve(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    target_user_id = int(parts[2])
    deal_id = parts[3] if len(parts) > 3 else None
    admin_id = callback.from_user.id

    # Get the correct deal
    if deal_id:
        deal = deal_claims.get(deal_id)
    else:
        # Compatibility with older callback buttons
        deal = deal_claims.get(target_user_id)

    if not deal or deal["status"] != "pending":
        approved_username = (
            deal.get("approved_username", "another middleman")
            if deal else "another middleman"
        )

        await callback.answer(
            '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
            f'This deal has already been claimed by {approved_username}.',
            show_alert=True
        )
        return

    # Claim the deal immediately
    deal["status"] = "claimed"
    deal["approved_by"] = admin_id

    admin_username = callback.from_user.username

    if admin_username:
        deal["approved_username"] = f"@{admin_username}"
    else:
        deal["approved_username"] = callback.from_user.full_name

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> <b>Deal approved!</b>\n\n'
        f'<b>Middleman:</b> {deal["approved_username"]}\n\n'
        'Please send the Escrow Group Link in chat now:',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

    admin_states[admin_id] = {
        "step": "waiting_group_link",
        "target_user": target_user_id,
        "deal_id": deal_id
    }

@router.callback_query(F.data.startswith("mm_rej_"))
async def mm_reject(callback: CallbackQuery, state: FSMContext):
    target_user_id = int(callback.data.split("_")[2])

    await callback.message.edit_text(
        '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Deal rejected.</b>',
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@router.callback_query(F.data == "menu_tos")
async def show_tos(callback: CallbackQuery, state: FSMContext):
    tos_text = (
        "<b>Affux Escrow — TOS</b>\n\n"
        "Please read before using "
        "<a href='https://t.me/Middlemaven'>AFFUX Escrow</a>.\n\n"

        "<b>1. Escrow Service</b>\n"
        "Neutral third-party service for P2P and legitimate deals. "
        "Funds are held until conditions are met.\n\n"

        "<b>2. Supported Deals</b>\n"
        "• Crypto - Crypto, Crypto - INR, INR - Crypto\n"
        "• Accounts, usernames, digital products, services, gaming items, ads, other goods/services.\n\n"

        "<b>3. Prohibited Deals</b>\n"
        "Stolen/hacked accounts, fraud, scams, stolen funds, doxxing, "
        "KYC/private data, malware, drugs, weapons, or illegal transactions.\n\n"

        "<b>4. Verification & Disputes</b>\n"
        "Proof may be requested. Suspicious deals may be paused/cancelled. "
        "Disputes are reviewed using agreed conditions and evidence.\n\n"

        "<b>5. Fees</b>\n"
        "Escrow fee is non-refundable once service starts, even if cancelled. "
        "Network/payment fees are separate.\n\n"

        "<b>6. User Responsibility</b>\n"
        "Verify deal details, amount, payment info, wallet address, and buyer/seller.\n\n"

        "<b>7. Completion & Refusal</b>\n"
        "Funds released = deal complete. Affux Escrow may refuse or terminate unsafe deals.\n\n"

        "By using <a href='https://t.me/middlemaven'>Affux Escrow</a>, "
        "you agree to these TOS.\n\n"

        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_start">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(tos_text).model_dump(exclude_none=True)
    )

    await callback.answer()

@router.callback_query(F.data == "menu_support")
async def show_support(callback: CallbackQuery, state: FSMContext):
    support_text = (
        '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji> '
        '<b>Support</b>\n\n'
        'What is this about?\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'data="support_deals">Deals</tg-button>'
        '<tg-button type="callback_data" '
        'data="support_others">Others</tg-button>'
        '</tg-button-row>'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="back_to_start">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(support_text).model_dump(exclude_none=True)
    )

    await callback.answer()

@router.callback_query(F.data == "support_deals")
async def support_deals(callback: CallbackQuery, state: FSMContext):
    text = (
        '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
        '<b>You have no completed deals.</b>\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="menu_support">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(text).model_dump(exclude_none=True)
    )

    await callback.answer()

@router.callback_query(F.data == "support_others")
async def support_others(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id

    escrow_states[sender_id] = {
        "step": "waiting_support_query"
    }

    text = (
        '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji> '
        '<b>Support</b>\n\n'
        'What is the issue? Send it in one message.\n\n'
        '<tg-button-row>'
        '<tg-button type="callback_data" '
        'icon_custom_emoji_id="5210952531676504517" '
        'data="menu_support">Back</tg-button>'
        '</tg-button-row>'
    )

    # ✅ FIX: make_rich_message use karo
    await callback.bot.edit_rich_message(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        rich_message=make_rich_message(text).model_dump(exclude_none=True)
    )

    await callback.answer()

async def main():
    print("BOT STARTING...")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        # Flask web server ko background thread mein start karo
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()

        # Aiogram bot start karo
        asyncio.run(main())

    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")