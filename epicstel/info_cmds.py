import re
from datetime import datetime, timedelta

import epics
import plotly.graph_objects as go
import requests
from telegram import Update
from telegram.ext import CallbackContext

from epicstel import static_text
from epicstel.common import check_ownership, has_loading, restricted_admin


class InfoCommands:
    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger

    @has_loading
    def get_is_alive(self, update: Update, _: CallbackContext) -> None:
        update.message.reply_text(
            "Monitor thread is running!" if self.bot.thread_is_alive else "Monitor thread is currently down"
        )

    @has_loading
    def get_help(self, update: Update, _: CallbackContext) -> None:
        help_reply = static_text.user_commands
        user = self.bot.users.find_one({"chat_id": update.effective_user.id})

        if "ADM" in user.get("teams"):
            help_reply += static_text.team_adm_commands
            help_reply += static_text.bot_adm_commands
        elif user.get("adminof"):
            help_reply += static_text.team_adm_commands

        update.message.reply_text(
            static_text.greeting.safe_substitute(NAME=update.effective_user.first_name)
            + "\n"
            + help_reply
            + "\n"
            + static_text.links,
            parse_mode="markdown",
        )

    @has_loading
    def get_pv_groups(self, update: Update, _: CallbackContext) -> None:
        answer = "ℹ The existing PV groups are: ```"

        for group in self.bot.pvs.distinct("group"):
            answer += "\n" + group

        update.message.reply_text(answer + "```", parse_mode="markdown")

    @has_loading
    def get_user_info(self, update: Update, _: CallbackContext) -> None:
        user = self.bot.users.find_one({"chat_id": update.effective_user.id})

        user_teams = ", ".join(user.get("teams"))
        pv_groups = ", ".join(user.get("groups"))
        pvs = ", ".join(["{} ({})".format(pv.get("name"), pv.get("group")) for pv in user.get("pvs")])
        ignored_pvs = ", ".join(
            [
                "{} ({})".format(pv.get("name"), pv.get("group"))
                for pv in self.bot.pvs.find({"_id": {"$in": user.get("ignore")}})
            ]
        )
        answer = static_text.check_me.safe_substitute(
            user=update.effective_user.full_name,
            id=update.effective_user.id,
            teams=user_teams,
            pvgroups=pv_groups,
            pvs=pvs,
            ignored=ignored_pvs,
        )

        update.message.reply_text(answer, parse_mode="markdown")

    @has_loading
    def get_team_info(self, update: Update, cont: CallbackContext) -> None:
        for team in cont.args:
            info = self.bot.teams.find_one({"team": team})
            if not info:
                update.message.reply_text("`{}` team does not exist".format(team), parse_mode="markdown")
                continue

            if not check_ownership(self, update, team):
                continue

            users, admins = "", ""
            for user in self.bot.users.find({"teams": team}):
                users += "{} ({})\n".format(user.get("fullname"), user.get("chat_id"))

            for admin in self.bot.users.find({"adminof": team}):
                admins += "{} ({})\n".format(admin.get("fullname"), admin.get("chat_id"))

            answer = static_text.check_team.safe_substitute(
                team=team,
                admins=admins,
                members=users,
                pvgroups="\n".join(info.get("groups")),
                pvs="\n".join(info.get("pvs")),
            )

            update.message.reply_text(answer, parse_mode="markdown")

    @has_loading
    def get_group_info(self, update: Update, cont: CallbackContext) -> None:
        answer = ""
        for group in cont.args:
            pv_info = ""
            for pv in self.bot.pvs.find({"group": group}):
                pv_info += "{} - Max:{} Min:{} Timeout:{} min\n\n".format(
                    pv.get("name"), pv.get("max"), pv.get("min"), pv.get("timeout")
                )

            answer += "ℹ *{}*:\n```\n{}\n```\n".format(group, pv_info) if pv_info else "Group does not exist\n"

        update.message.reply_text(answer, parse_mode="markdown")

    @has_loading
    @restricted_admin
    def get_teams(self, update: Update, _: CallbackContext) -> None:
        update.message.reply_text(
            "The existing Teams are:\n" + "\n".join(sorted(list(self.bot.teams.distinct("team"))))
        )

    @has_loading
    def get_status(self, update: Update, cont: CallbackContext) -> None:
        for pv in cont.args:
            pv_statuses = requests.get(
                "https://10.0.38.42/mgmt/bpl/getPVStatus?pv={}&reporttype=short".format(pv),
                verify=False,
            ).json()

            if not pv_statuses:
                update.message.reply_text("`{}` has not matched any PVs".format(pv), parse_mode="markdown")
                return

            for status in pv_statuses:
                status_msg = "ℹ️ *Status for {}:* {}".format(status["pvName"], status["status"])

                if status["status"] == "Being archived":
                    status_msg += static_text.get_status.safe_substitute(
                        last_event=status["lastEvent"],
                        connected=status["connectionState"],
                        appliance=status["appliance"],
                    )

                update.message.reply_text(status_msg, parse_mode="markdown")

    @has_loading
    def caget(self, update: Update, cont: CallbackContext) -> None:
        answer = ""

        for PV in cont.args:
            pv = epics.PV(PV, connection_timeout=0.2)
            if pv.value is not None and pv.units is not None:
                answer += "\n{}: {} {}".format(PV, pv.value, pv.units)
            else:
                answer += "\n{} is not available".format(PV)

        update.message.reply_text(answer)

    @has_loading
    def forward(self, update: Update, cont: CallbackContext) -> None:
        fwd = "Message forwarded by {} ({}):\n{}".format(
            update.effective_user.full_name, update.effective_user.id, " ".join(cont.args)
        )

        if "ADM" not in self.users.find_one({"chat_id": update.effective_user.id}).get("teams"):
            for adm in self.bot.users.find({"teams": {"$in", "ADM"}}):
                update.message.bot.send_message(adm.get("chat_id"), fwd)

            update.message.reply_text("Message forwarded to BOT administrators successfully")
        else:
            try:
                # Formats the message to be forwarded and extracts the forward_id
                forward_id = cont.args.pop(0)

                # Verifies if the ID is an authorized user or group
                if self.bot.users.find_one({"chat_id": forward_id}):
                    update.message.bot.send_message(forward_id, fwd)
                    answer = "Message forwarded to {} :\n{}".format(
                        "{}:{}".format(self.bot.authorized_personnel[forward_id], forward_id),
                        fwd,
                    )
                    update.message.reply_text(answer)
                # Case it's not authorized personnel
                else:
                    update.message.reply_text("The specified ChatID is not authorized to use the BOT")
                    self.logger.debug(
                        "{} tried to forward a message to an unauthorized ChatID: {}".format(
                            update.effective_user.username, forward_id
                        )
                    )
            # Case the message was formatted wrong
            except ValueError:
                update.message.reply_text(static_text.forward_mistype)
                self.logger.debug(
                    "{} tried to send an incorrectly formatted forward: {}".format(
                        update.effective_user.username, forward_id
                    )
                )

    @has_loading
    def plot(self, update: Update, cont: CallbackContext) -> None:
        try:
            if len(cont.args[-1]) > 11:
                end = datetime.strptime(cont.args[-1], static_text.input_date_long)
            else:
                end = datetime.strptime(cont.args[-1], static_text.input_date_short)

            cont.args.pop()
        except ValueError:
            update.message.reply_text(
                "Invalid/no end time selected (format example: `2021/05/24-07:00:00`). Using current time as end time.",  # noqa: E501
                parse_mode="markdown",
            )
            end = datetime.now()

        try:
            if len(cont.args[-1]) > 11:
                start = datetime.strptime(cont.args[-1], static_text.input_date_long)
            else:
                start = datetime.strptime(cont.args[-1], static_text.input_date_short)

            cont.args.pop()
        except ValueError:
            update.message.reply_text(
                "Invalid/no start time selected (format example: `2021/05/24-07:00:00`). Using end time -30 minutes as starting time.",  # noqa: E501
                parse_mode="markdown",
            )
            start = end - timedelta(minutes=30)

        if start > end:
            update.message.reply_text("The starting date must come before the end date")
            return

        min_date, max_date, valid = None, None, False
        plotted_egus = []
        side = "right"
        pos = {"left": 0, "right": 1.0}

        fig = go.Figure()

        for pv in cont.args:
            if epics.caget(pv, timeout=0.2) is None:
                if "*" in pv:
                    update.message.reply_text("GLOB filters are not supported for this command")
                else:
                    update.message.reply_text("PV `{}` does not exist".format(pv), parse_mode="markdown")
                continue

            req = requests.get(
                "http://10.0.38.42/retrieval/data/getData.json?pv={}&from={}&to={}".format(
                    pv,
                    datetime.strftime(start, static_text.output_date),
                    datetime.strftime(end, static_text.output_date),
                )
            ).json()

            if not len(req) or not req[0]["data"]:
                update.message.reply_text(
                    "There was no data for `{}` in the selected period".format(pv), parse_mode="markdown"
                )
                return

            egu = req[0]["meta"].get("EGU") or "No label"
            pv_data = [v["val"] for v in req[0]["data"]]
            pv_timestamps = [datetime.utcfromtimestamp(v["secs"]) for v in req[0]["data"]]

            if egu not in plotted_egus:
                plotted_egus.append(egu)
                if len(plotted_egus) == 1:
                    fig.update_layout({"yaxis1": {"title": egu, "position": 0}})
                else:
                    pos[side] += -0.1 if side == "right" else 0.1
                    fig.update_layout(
                        {
                            "yaxis{}".format(len(plotted_egus)): {
                                "title": egu,
                                "side": side,
                                "overlaying": "y",
                                "position": pos[side],
                            }
                        }
                    )

                    side = "left" if side == "right" else "right"

            if len(pv_data) > 10:
                if min_date is None or pv_timestamps[0] > min_date:
                    min_date = pv_timestamps[0]

                if max_date is None or pv_timestamps[-1] < max_date:
                    max_date = pv_timestamps[-1]

            fig.add_trace(
                go.Scatter(
                    x=pv_timestamps,
                    y=pv_data,
                    yaxis="y{}".format(plotted_egus.index(egu) + 1),
                    line_shape="vh",
                    name=pv,
                    mode="lines",
                )
            )

            valid = True

        if valid:
            fig.update_layout(
                {
                    "title": "{} to {}".format(
                        datetime.strftime(start, static_text.output_date),
                        datetime.strftime(end, static_text.output_date),
                    ),
                    "margin": {"l": 0, "r": 0},
                    "xaxis": {"range": [min_date, max_date], "domain": [pos["left"], pos["right"]]},
                }
            )
            update.message.reply_photo(fig.to_image(format="png", width=1600, height=900, engine="kaleido"))

    @has_loading
    def changelog(self, update: Update, _: CallbackContext) -> None:
        resp = requests.get("https://github.com/lnls-sirius/epicstel/blob/master/CHANGELOG.md").content.decode()

        # Matches and replaces [] and ### characters with Telegram markdown
        changelog = re.sub(r"[\[\]]", "*", resp).split("\n## ")[1]
        changelog = re.sub(r"^### (.*)", r"_\1_", changelog, flags=re.M)

        update.message.reply_text(changelog, parse_mode="markdown")
