from bson import ObjectId
from telegram import Update, error
from telegram.ext import CallbackContext

from epicstel.common import check_ownership, has_loading, restricted_admin


class UserCommands:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger

    @has_loading
    @restricted_admin
    def add_team(self, update: Update, cont: CallbackContext) -> None:
        team_name = cont.args.pop(1)
        team_members = set(cont.args)
        team_adm = cont.args[0]

        parsed_users = []

        try:
            adm_id = int(team_adm.split(":")[1])
        except ValueError:
            update.message.reply_text("All members should be formatted as Name:ChatID")
            return

        if self.bot.teams.find_one({"team": team_name}):
            update.message.reply_text("`{}` team already exists".format(team_name), parse_mode="markdown")
            return

        for member in team_members:
            try:
                name, chat_id = member.split(":")
                chat_id = int(chat_id)
                parsed_users.append([chat_id, name])
                update.message.bot.get_chat(chat_id)
            except (ValueError, error.BadRequest):
                update.message.reply_text(
                    "All members should include valid names and chat IDs, formatted as Name:ChatID"
                )
                return

        for user in parsed_users:
            self.bot.users.update_one(
                {"chat_id": user[0]},
                {
                    "$setOnInsert": {"pvs": [], "groups": [], "adminof": [], "chat_id": user[0], "fullname": user[1]},
                    "$addToSet": {"teams": team_name},
                },
                upsert=True,
            )
            update.message.bot.send_message(
                user[0], "You've been added to the `{}` team".format(team_name), parse_mode="markdown"
            )

        self.bot.teams.insert_one({"team": team_name, "pvs": [], "groups": []})
        self.bot.users.update_one({"chat_id": adm_id}, {"$addToSet": {"adminof": team_name}})

        print(parsed_users)

        for adm in self.bot.users.find({"teams": "ADM"}):
            update.message.bot.send_message(
                adm.get("chat_id"),
                "ℹ️ New Team added by `{}`: *{}*\n```\n{}```".format(
                    update.effective_user.username,
                    team_name,
                    "\n".join(["{} ({})".format(u[1], u[0]) for u in parsed_users]),
                ),
                parse_mode="markdown",
            )

    @has_loading
    @restricted_admin
    def remove_team(self, update: Update, cont: CallbackContext) -> None:
        team = cont.args[0]

        if self.bot.teams.delete_one({"team": team}).deleted_count:
            self.bot.users.update_many(
                {"$or": [{"teams": team}, {"adminof": team}]}, {"$pull": {"teams": team, "adminof": team}}
            )
            update.message.reply_text("`{}` team successfully deleted".format(team), parse_mode="markdown")
        else:
            update.message.reply_text("`{}` team does not exist".format(team), parse_mode="markdown")

    @has_loading
    def add_user(self, update: Update, cont: CallbackContext) -> None:
        team = cont.args[1]

        try:
            name, chat_id = cont.args[0].split(":")
            chat_id = int(chat_id)
            update.message.bot.get_chat(chat_id)
        except (ValueError, error.BadRequest):
            update.message.reply_text("Please specify a valid user (Name:ChatID)")
            return

        if not self.bot.users.find_one({"teams": team}):
            update.message.reply_text("Please specify a valid team")
            return

        if not check_ownership(self, update, team):
            return

        self.bot.users.update_one(
            {"chat_id": chat_id},
            {
                "$setOnInsert": {"pvs": [], "groups": [], "adminof": [], "chat_id": chat_id, "fullname": name},
                "$addToSet": {"teams": team},
            },
            upsert=True,
        )
        update.message.reply_text("`{}` successfully added to `{}`".format(name, team), parse_mode="markdown")
        update.message.bot.send_message(
            chat_id, "You've been added to the `{}` team".format(team), parse_mode="markdown"
        )

    @restricted_admin
    @has_loading
    def remove_user(self, update: Update, cont: CallbackContext) -> None:
        try:
            team = cont.args.pop(-1)
            chat_id = [int(c_id) for c_id in cont.args]
            names = ",".join(
                [
                    "{} ({})".format(u.get("fullname"), u.get("chat_id"))
                    for u in self.bot.users.find({"chat_id": {"$in": chat_id}})
                ]
            )
        except ValueError:
            update.message.reply_text("Please only add valid chat IDs")
            return

        if team == "ALL":
            self.bot.users.delete_many({"chat_id": {"$in": chat_id}})
            update.message.reply_text(
                "Succesfully removed `{}` from all groups and authorized users list.".format(names),
                parse_mode="markdown",
            )
            return

        if not self.bot.users.update_many(
            {"chat_id": {"$in": chat_id}, "teams": team}, {"$pull": {"teams": team, "adminof": team}}
        ).modified_count:
            update.message.reply_text(
                "The users `{}` arent't authorized or don't belong to the `{}` team.".format(names, team),
                parse_mode="markdown",
            )
        else:
            for u in chat_id:
                update.message.bot.send_message(
                    u, "You've been removed from the `{}` team".format(team), parse_mode="markdown"
                )

            update.message.reply_text("Successfully removed `{}` from `{}`".format(names, team), parse_mode="markdown")

    @has_loading
    def subscribe_pv(self, update: Update, cont: CallbackContext) -> None:
        pv, group = cont.args[0], cont.args[1]
        existing_pv = self.bot.pvs.find_one({"name": pv, "group": group})

        if not existing_pv:
            update.message.reply_text("`{}` does not exist inside group `{}`".format(pv, group), parse_mode="markdown")
            return

        if not self.bot.users.update_one(
            {"chat_id": update.effective_user.id},
            {"$addToSet": {"pvs": {"name": pv, "group": group, "ext_id": ObjectId(existing_pv.get("_id"))}}},
        ).modified_count:
            update.message.reply_text("You're already subscribed to `{}`".format(pv), parse_mode="markdown")
        else:
            update.message.reply_text("Successfully subscribed to the `{}` PV".format(pv), parse_mode="markdown")

    @has_loading
    def unsubscribe_pv(self, update: Update, cont: CallbackContext) -> None:
        pv, group = cont.args[0], cont.args[1]

        if not self.bot.users.update_one(
            {"chat_id": update.effective_user.id}, {"$pull": {"pvs": {"name": pv, "group": group}}}
        ).modified_count:
            update.message.reply_text("You're already not subscribed to `{}`".format(pv), parse_mode="markdown")
        else:
            update.message.reply_text("Successfully unsubscribed to `{}` PV".format(pv), parse_mode="markdown")

    @has_loading
    def unsubscribe(self, update: Update, cont: CallbackContext) -> None:
        for pv in cont.args:
            if not self.bot.users.update_one(
                {"chat_id": update.effective_user.id}, {"$pull": {"groups": pv}}
            ).modified_count:
                update.message.reply_text("You're already not subscribed to `{}`".format(pv), parse_mode="markdown")
            else:
                update.message.reply_text(
                    "Successfully unsubscribed to the `{}` group".format(pv), parse_mode="markdown"
                )

    @has_loading
    def subscribe(self, update: Update, cont: CallbackContext) -> None:
        for group in cont.args:
            if self.bot.pvs.find_one({"group": group}):
                if not self.bot.users.update_one(
                    {"chat_id": update.effective_user.id}, {"$addToSet": {"groups": group}}
                ).modified_count:
                    update.message.reply_text("You're already subscribed to `{}`".format(group), parse_mode="markdown")
                else:
                    update.message.reply_text(
                        "Successfully subscribed to the `{}` group".format(group), parse_mode="markdown"
                    )
            else:
                update.message.reply_text("`{}` group doesn't exist".format(group), parse_mode="markdown")

    @has_loading
    def subscribe_team(self, update: Update, cont: CallbackContext) -> None:
        team = cont.args.pop(0)
        groups = cont.args

        if not check_ownership(self, update, team):
            return

        for group in groups:
            if self.bot.pvs.find_one({"group": group}):
                if self.bot.teams.update_one({"team": team}, {"$addToSet": {"group": group}}).modified_count:
                    for user in self.bot.users.find({"teams": team}):
                        update.message.bot.send_message(
                            user.get("chat_id"), "Successfully subscribed to `{}`".format(group), parse_mode="markdown"
                        )

                    update.message.reply_text(
                        "Successfully subscribed `{}` team to `{}`".format(team, group), parse_mode="markdown"
                    )
                else:
                    update.message.reply_text(
                        "`{}` team is already subscribed to `{}`".format(team, group), parse_mode="markdown"
                    )
            else:
                update.message.reply_text("`{}` group doesn't exist".format(group), parse_mode="markdown")

    @has_loading
    def unsubscribe_team(self, update: Update, cont: CallbackContext) -> None:
        team = cont.args.pop(0)
        groups = cont.args

        if not check_ownership(self, update, team):
            return

        for group in groups:
            if self.bot.teams.update_one({"team": team}, {"$pull": {"groups": group}}).modified_count:
                for user in self.bot.users.find({"teams": team}):
                    update.message.bot.send_message(
                        user.get("chat_id"), "Successfully unsubscribed to `{}`".format(group), parse_mode="markdown"
                    )

                update.message.reply_text("Successfully unsubscribed to the `{}`".format(group), parse_mode="markdown")
            else:
                update.message.reply_text(
                    "`{}` team is already not subscribed to `{}`".format(team, group), parse_mode="markdown"
                )
