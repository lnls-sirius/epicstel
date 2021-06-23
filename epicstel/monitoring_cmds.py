from epics import caget
from telegram import Update
from telegram.ext import CallbackContext

from epicstel import static_text
from epicstel.common import has_loading, restricted_admin


class MonCommands:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger

    @has_loading
    @restricted_admin
    def disable_disc_mon(self, update: Update, cont: CallbackContext) -> None:
        self.toggle_disconnect_mon(False, update, cont)

    @has_loading
    @restricted_admin
    def enable_disc_mon(self, update: Update, cont: CallbackContext) -> None:
        self.toggle_disconnect_mon(True, update, cont)

    def toggle_disconnect_mon(self, toggle: bool, update: Update, cont: CallbackContext) -> None:
        desired_groups = []

        return_message, errors = "", ""

        if cont.args[0] == "ALL":
            desired_groups = self.bot.pvs.find()
        else:
            for pv in cont.args:
                found_pvs = list(self.bot.pvs.find({"$or": [{"group": pv}, {"name": pv}]}))
                if not found_pvs:
                    errors += "\n`{}` PV/Group does not exist or isn't registered".format(pv)
                    self.logger.debug(
                        "{} tried to toggle monitoring for a group that does not exist: {}".format(
                            update.effective_user.username, pv
                        )
                    )
                    continue

                desired_groups += [d["name"] for d in found_pvs if "name" in d]

        if desired_groups:
            self.bot.pvs.update_many({"name": {"$in": desired_groups}}, {"$set": {"d_count": 4}})
            modified = desired_groups.join(", ")
            return_message = "You have {} monitoring to `{}`\n".format("enabled" if toggle else "disabled", modified)

        update.message.reply_text(return_message + errors, parse_mode="markdown")

    @has_loading
    @restricted_admin
    def add_pv_to_group(self, update: Update, cont: CallbackContext) -> None:
        try:
            to_add_group, to_add_pv, to_add_max, to_add_min, timeout = (
                cont.args[0],
                cont.args[1],
                float(cont.args[2]),
                float(cont.args[3]),
                float(cont.args[4]),
            )
        except ValueError:
            update.message.reply_text(
                "Formatting Error. Format the message as follows: /addpv (GroupName) (PVName) (MaxLimit) (MinLimit)"
            )
            return

        if to_add_max < to_add_min:
            update.message.reply_text("The minimum value shouldn't be greater than the maximum value")
            return

        if self.bot.pvs.find_one({"group": to_add_group}):
            if self.bot.pvs.find_one({"name": to_add_pv, "group": to_add_group}):
                answer = static_text.pv_altered.safe_substitute(
                    group=to_add_group, pv=to_add_pv, max=to_add_max, min=to_add_min
                )
            else:
                if caget(to_add_pv, timeout=0.2) is None:
                    error = "{} process variable does not exist".format(to_add_pv)
                    update.message.reply_text(error)
                    self.logger.info("While adding PV: " + error)
                    return

                answer = static_text.new_pv.safe_substitute(
                    group=to_add_group, pv=to_add_pv, max=to_add_max, min=to_add_min
                )

            self.bot.pvs.update_one(
                {"name": to_add_pv, "group": to_add_group},
                {
                    "$setOnInsert": {"value": 0, "last_alert": 0, "d_time": 0, "d_count": 0},
                    "$set": {"max": to_add_max, "min": to_add_min, "timeout": timeout},
                },
                upsert=True,
            )

            self.logger.info("PV -> {}: max = {}, min = {}".format(to_add_pv, to_add_max, to_add_min))
            update.message.reply_text(answer, parse_mode="markdown")
        else:
            update.message.reply_text("The PV group `{}` does not exist.".format(to_add_group), parse_mode="markdown")

    @has_loading
    @restricted_admin
    def set_timeout(self, update: Update, cont: CallbackContext) -> None:
        pv = cont.args[0]
        try:
            timeout = float(cont.args[1])
        except ValueError:
            self.logger.debug(
                "{} tried to adjust timeout with a malformed string.".format(update.effective_user.username)
            )
            update.message.reply_text(
                "Please check if you formatted the command properly. Example: /settimeout (PVGroup) (Timeout)"
            )

        # Verifies if PV group name is valid
        modified = self.bot.pvs.update_many({"$or": [{"group": pv}, {"name": pv}]}, {"$set": {"timeout": timeout}})
        if not modified.modified_count:
            self.logger.debug(
                "{} tried to adjust timeout for inexistant PV group {}.".format(
                    update.effective_user.username, cont.args[0]
                )
            )
            update.message.reply_text("`{}` PV/group does not exist".format(cont.args[0]), parse_mode="markdown")
            return

        update.message.reply_text(
            "Timeout of `{}` PV/group successfully adjusted to {} minutes".format(pv, timeout),
            parse_mode="markdown",
        )

    @has_loading
    @restricted_admin
    def remove_group(self, update: Update, cont: CallbackContext) -> None:
        # Strings to be returned
        errors, answer = "", ""
        # list that will contain the PVs from the removed groups

        for to_pop_group in cont.args:
            if self.bot.users.find_one({"groups": to_pop_group}):
                errors += "\nCouldn't remove; `{}` PV group has users subscribed".format(to_pop_group)
                self.logger.info(
                    "{} tried to remove group with users subscribed to it {}.".format(
                        update.effective_user.username, to_pop_group
                    )
                )
                continue

            if not self.bot.pvs.delete_many({"group": to_pop_group}).raw_result.get("n"):
                errors += "\n`{}` PV Group isn't registered".format(to_pop_group)
                self.logger.debug(
                    "{} tried to remove inexistant group {}.".format(update.effective_user.username, to_pop_group)
                )
            else:
                answer += "`{}` PV group removed succesfully".format(to_pop_group)

        update.message.reply_text(answer + errors, parse_mode="markdown")

    @has_loading
    @restricted_admin
    def remove_pv_from_group(self, update: Update, cont: CallbackContext) -> None:
        group, pv = cont.args[0], cont.args[1]

        if not self.bot.pvs.delete_one({"group": group, "name": pv}).raw_result.get("n"):
            update.message.reply_text("The selected PV doesn't belong to this group or doesn't exist.")
            return

        self.bot.users.update_many({}, {"$pull": {"pvs": {"group": group, "name": pv}}})
        self.bot.teams.update_many({}, {"$pull": {"pvs": {"group": group, "name": pv}}})

        update.message.reply_text("PV `{}` removed from group `{}`.".format(pv, group), parse_mode="markdown")

    @has_loading
    @restricted_admin
    def add_group(self, update: Update, cont: CallbackContext) -> None:
        to_add_group = cont.args[0]

        if self.bot.pvs.find_one({"group": to_add_group}):
            self.logger.debug(
                "{} tried adding a new group. Group name already exists: {}".format(
                    update.effective_user.username, to_add_group
                )
            )
            update.message.reply_text(
                "This group name already exists. You may use /addpv to update a PV or try again with a new name."
            )
            return
        try:
            to_add_list, maximum, minimum, timeout = (
                cont.args[1:-3],
                float(cont.args[-3]),
                float(cont.args[-2]),
                float(cont.args[-1]),
            )
        except ValueError:
            self.logger.debug(
                "{} used invalid values in group init: {}".format(update.effective_user.username, " ".join(cont.args))
            )
            update.message.reply_text("Please use valid minimum/maximum values")
            return

        # Verify if maximum and minimum limits are valid
        if float(minimum) > float(maximum):
            self.logger.debug(
                "{} used invalid values in group init: {}".format(update.effective_user.username, " ".join(cont.args))
            )
            update.message.reply_text("Please specify a maximum value greater than the minimum value")
            return

        # Adds the same limits to every PV in a group
        added_any = False
        for pv_name in to_add_list:
            if caget(pv_name, timeout=0.2) is not None:
                print(pv_name)
                # Will this always be an insert?
                self.bot.pvs.update_one(
                    {"name": pv_name, "group": to_add_group},
                    {
                        "$set": {
                            "name": pv_name,
                            "min": minimum,
                            "max": maximum,
                            "timeout": timeout,
                            "d_time": 0,
                            "d_count": 0,
                            "value": 0,
                            "last_alert": 0,
                        }
                    },
                    upsert=True,
                )
                added_any = True

        if not added_any:
            self.logger.debug(
                "{} provided no valid PVs: {}".format(update.effective_user.username, " ".join(cont.args))
            )
            update.message.reply_text(
                "No valid PVs were provided to create this group. Provide at least one valid PV and try again."
            )
            return

        self.logger.info("{} added new group: {}".format(update.effective_user.username, to_add_group))
        update.message.reply_text("New PV group added: `{}`".format(to_add_group), parse_mode="markdown")
