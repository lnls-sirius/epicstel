from typing import Callable

import telegram.error
from telegram import ChatAction, Update
from telegram.ext import CallbackContext

from epicstel import static_text


def make_parse(cmd: str, func: Callable, min_args: int = 1, max_args: int = -1) -> bool:
    def parse(update: Update, cont: CallbackContext) -> bool:
        args = cont.args
        arg_c = len(args)

        if (max_args != -1 and arg_c > max_args) or arg_c < min_args:
            v = static_text.command_dict[cmd]
            update.message.reply_text("Correct command usage:\n/{} {} - {}".format(cmd, v["syntax"], v["desc"]))
            return False

        func(update, cont)
        return True

    return parse


def check_ownership(self, update: Update, team: str) -> bool:
    user = self.bot.users.find_one({"chat_id": update.effective_user.id})

    if team not in user.get("adminof") and "ADM" not in user.get("teams"):
        update.message.reply_text(
            "You are not an admin of `{}`, request forwarded to admins".format(team), parse_mode="markdown"
        )
        forward_to_adm(self, update)
        return False

    return True


def restricted_admin(func):
    def wrap(self, update: Update, cont: CallbackContext) -> bool:
        chat_id = update.effective_user.id

        if "ADM" not in self.bot.users.find_one({"chat_id": chat_id}).get("teams"):
            self.logger.info(
                "{} wishes to {} with args {}".format(
                    update.effective_user.username, func.__name__, " ".join(cont.args)
                )
            )

            forward_to_adm(self, update)
            update.message.reply_text("Request forwarded to the bot's administrators")
            return False

        func(self, update, cont)
        return True

    return wrap


def restricted_individual(func):
    def wrap(self, update: Update, cont: CallbackContext) -> bool:
        if update.effective_chat.type != "private":
            update.message.reply_text(
                "We're sorry, but this command is only available in private chats due to Telegram's spam policies."
            )
            return False

        func(self, update, cont)
        return True

    return wrap


def forward_to_adm(self, update: Update):
    for adm in self.bot.users.find({"teams": "ADM"}):
        try:
            update.message.bot.send_message(
                adm.get("chat_id"), "{} wishes to {}".format(update.effective_user.username, update.message.text)
            )
        except (telegram.error.BadRequest, telegram.error.Unauthorized):
            self.logger.warning("ADM {} is not a valid user".format(adm.get("chat_id")))
            continue


def has_loading(func):
    def wrap(self, update: Update, cont: CallbackContext) -> Callable:
        if not self.bot.users.find_one({"chat_id": update.message.chat_id}):
            self.logger.debug(
                "User {} ({}) attempted to run a command despite not being in the authorized personnel list.".format(
                    update.effective_user.username, update.effective_user.id
                )
            )
            update.message.reply_text(
                "Sorry! You're not listed in the bot's authorized personnel list. Please contact an admin and inform your user ID: *{}*".format(  # noqa: E501
                    update.effective_user.id
                ),
                parse_mode="markdown",
            )
            return False

        update.message.reply_chat_action(action=ChatAction.TYPING)
        return func(self, update, cont)

    return wrap
