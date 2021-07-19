import logging
import os
import time
import traceback
from logging.handlers import RotatingFileHandler

import epics
from bson import ObjectId
from telegram import Update
from telegram.ext import CallbackContext, CommandHandler, Filters, MessageHandler, Updater

import epicstel.static_text as static_text
from epicstel import __version__
from epicstel.common import make_parse
from epicstel.info_cmds import InfoCommands
from epicstel.monitoring_cmds import MonCommands
from epicstel.user_cmds import UserCommands


class TelBot(Updater):
    thread_is_alive = True

    def __init__(self, token: str, client, debug: bool = False):
        super(TelBot, self).__init__(token)

        static_text.gen_strings()

        if debug:
            db = client.epicstel_hmg
        else:
            db = client.epicstel

        self.configs = db.configs
        self.teams = db.teams
        self.users = db.users
        self.pvs = db.pvs

        os.environ["EPICS_CA_ADDR_LIST"] = " ".join(self.configs.find_one({"config": "EPICS_CA_ADDR_LIST"}).get("ips"))

        self.logger = logging.getLogger("EPICSTel")

        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(levelname)s:%(asctime)s:%(name)s:%(message)s")
        file_handler = RotatingFileHandler("data/epicstel.log", maxBytes=15000000, backupCount=5)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        self.logger.info("Initiating command handler")

        info = InfoCommands(self)
        mons = MonCommands(self)
        user = UserCommands(self)

        obj_dict = {"info": info, "mons": mons, "user": user}

        for k, v in static_text.command_dict.items():
            if "syntax" in v:
                min_args = 1 if "min_args" not in v else v["min_args"]
                max_args = -1 if "max_args" not in v else v["max_args"]

                parse = make_parse(k, getattr(obj_dict[v["type"]], v["func"]), min_args=min_args, max_args=max_args)
                self.dispatcher.add_handler(CommandHandler(k, parse))

            else:
                self.dispatcher.add_handler(CommandHandler(k, getattr(obj_dict[v["type"]], v["func"])))

        self.dispatcher.add_error_handler(self.error)
        self.dispatcher.add_handler(MessageHandler(Filters.command, self.unknown))

        print("\n\nEPICSTel bot - v{}\n#############################################\nBot data:\n".format(__version__))

        me = self.bot.get_me()

        print("ID: {}".format(me.id))
        print("Username: {}".format(me.username))
        print("Display name: {}".format(me.first_name))
        print("Initialization timestamp: {}\n#############################################\n".format(time.time()))

        self.start_polling()
        return

    def error(self, update: Update, cont: CallbackContext) -> None:
        tb_list = traceback.format_exception(None, cont.error, cont.error.__traceback__)
        tb_string = "".join(tb_list)

        if update:
            err_str = "Error from user while running `{}`: ``` {} ```".format(update.message.text, tb_string)
            update.message.reply_text("Sorry! An error has occurred. Please try again later.")
        else:
            err_str = "Error: {}".format(cont.error)

        self.logger.error(err_str)
        self.bot.send_message(403822264, err_str, parse_mode="markdown")

    def unknown(self, update: Update, _: CallbackContext) -> None:
        self.logger.debug(
            "User {} ({}) attempted to run a command that is not registered.".format(
                update.effective_user.username, update.effective_user.id
            )
        )
        update.message.reply_text("Sorry, this command does not exist! Check out /help for all valid commands.")

    def update_pv_values(self):
        for pv in self.pvs.find():
            try:
                value = epics.caget(pv.get("name"))
            except epics.ca.ChannelAccessGetFailure:
                self.logger.error("CA access failed, not storing value for {}".format(pv.get("name")))
                continue

            self.pvs.update_one({"_id": ObjectId(pv["_id"])}, {"$set": {"value": value}})
